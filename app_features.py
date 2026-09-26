from collections import Counter
from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import secrets

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from database.db import get_db
from claim_services import DOCUMENT_TYPES, read_policies, validate_upload
from decision_service import load_limits


def dashboard_data(db):
    from workflow import scoped_claims, permitted_owner
    rows = scoped_claims(db)
    ids = {row['id'] for row in rows}
    products = [row for row in db.execute('SELECT * FROM products') if permitted_owner(db, row['user_id'])]
    product_ids = {row['id'] for row in products}
    warranties = [row for row in db.execute('SELECT * FROM warranties') if row['product_id'] in product_ids]
    today = date.today().isoformat()
    checks = Counter(row['rule_name'] for row in db.execute("SELECT * FROM rule_results WHERE result!='Pass'") if row['claim_id'] in ids)
    evaluations = [row for row in db.execute('SELECT * FROM evaluations WHERE id IN (SELECT MAX(id) FROM evaluations GROUP BY claim_id)') if row['claim_id'] in ids]
    scores = [row['top_conf'] for row in db.execute('SELECT * FROM predictions WHERE id IN (SELECT MAX(id) FROM predictions GROUP BY claim_id,model_type)') if row['claim_id'] in ids]
    alerts = []
    if session['role'] == 'admin':
        alerts = db.execute('SELECT event,COUNT(*) AS count FROM security_events WHERE substr(created_at,1,10)=? GROUP BY event', (today,)).fetchall()
    return dict(claims=rows[:10], total=len(rows), counts=Counter(row['status'] for row in rows),
                product_count=len(products), active=sum(w['start_date'] <= today <= w['expiry_date'] for w in warranties),
                expired=sum(w['expiry_date'] < today for w in warranties),
                expiring=sum(today <= w['expiry_date'] <= (date.today() + timedelta(days=current_app.config['WARRANTY_ALERT_DAYS'])).isoformat() for w in warranties),
                receipts=sum(row['document_type'] in ('Receipt', 'Invoice') and row['product_id'] in product_ids for row in db.execute('SELECT * FROM documents')),
                categories=Counter(row['category'] for row in rows), faults=Counter(row['damage_type'] for row in rows),
                flags=[dict(rule_name=key, count=value) for key, value in checks.items()], alerts=alerts,
                outcomes=Counter(row['result'] for row in evaluations),
                consistency=Counter(row['consistency'] for row in evaluations),
                average_conf=sum(scores)/len(scores) if scores else None,
                trends=Counter(row['created_at'][:7] for row in rows),
                repairs=Counter('Authorized' if row['authorized'] else 'Unauthorized' for row in db.execute('SELECT * FROM repairs') if row['product_id'] in product_ids),
                rejections=Counter(row['comment'] for row in db.execute("SELECT * FROM claim_reviews WHERE action='Rejected'") if row['claim_id'] in ids))


def refresh_claim_alerts(db):
    from workflow import notify
    policies = read_policies()
    limits = load_limits()
    rows = db.execute("SELECT c.*,p.category FROM claims c JOIN products p ON p.id=c.product_id WHERE c.status IN ('Draft','Additional Information Required')").fetchall()
    for claim in rows:
        policy = next((v for key, v in policies.items() if key.casefold() == claim['category'].casefold()), None)
        if not policy or not claim['fault_occurrence_date']:
            continue
        deadline = date.fromisoformat(claim['fault_occurrence_date']) + timedelta(days=policy['reporting_days'])
        if 0 <= (deadline - date.today()).days <= limits['deadline_alert_days']:
            message = claim['claim_id'] + ': reporting deadline ' + deadline.isoformat()
            if not db.execute('SELECT 1 FROM notifications WHERE user_id=? AND claim_id=? AND message=?', (claim['user_id'], claim['id'], message)).fetchone():
                notify(db, claim['user_id'], message, claim['id'])


def install_features(app):
    from workflow import bp, audit, claim_record, permitted_owner, text_field

    @bp.route('/products/<int:product_id>/documents', methods=['GET', 'POST'])
    def product_documents(product_id):
        with closing(get_db()) as db, db:
            product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if not product or not permitted_owner(db, product['user_id']):
                abort(404)
            if request.method == 'POST':
                if session['role'] == 'reviewer':
                    abort(403)
                upload = request.files.get('document')
                kind = text_field('document_type', True, 100)
                if not upload or not upload.filename or kind not in DOCUMENT_TYPES:
                    abort(400, 'Choose a document and its type.')
                content = upload.read(10 * 1024 * 1024 + 1)
                try:
                    suffix = validate_upload(upload.filename, content)
                except ValueError as e:
                    flash(str(e), 'danger')
                    return redirect(url_for('workflow.product_documents', product_id=product_id))
                name = secrets.token_hex(24) + suffix
                folder = Path(current_app.config['UPLOAD_FOLDER'])
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / name
                try:
                    path.write_bytes(content)
                    cur = db.execute('INSERT INTO documents(user_id,product_id,document_type,original_name,stored_name,file_path,file_type,file_size,file_hash,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,datetime(\'now\'))',
                                     (product['user_id'], product_id, kind, secure_filename(upload.filename)[:200] or 'document' + suffix, name, name, suffix, len(content), hashlib.sha256(content).hexdigest()))
                    db.execute('INSERT INTO extracted_documents(document_id) VALUES(?)', (cur.lastrowid,))
                    audit(db, 'product document uploaded', str(product_id))
                    db.commit()
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                return redirect(url_for('workflow.product_documents', product_id=product_id))
            rows = db.execute('SELECT * FROM documents WHERE product_id=? AND claim_id IS NULL', (product_id,)).fetchall()
            return render_template('product_documents.html', product=product, documents=rows, document_types=DOCUMENT_TYPES)

    @bp.post('/claims/<int:claim_id>/attach/<int:document_id>')
    def attach_document(claim_id, document_id):
        from workflow import document_path
        with closing(get_db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            claim = claim_record(db, claim_id, edit=True)
            doc = db.execute('SELECT * FROM documents WHERE id=? AND product_id=? AND claim_id IS NULL', (document_id, claim['product_id'])).fetchone()
            if not doc:
                abort(404)
            if db.execute('SELECT 1 FROM documents WHERE claim_id=? AND file_hash=? AND document_type=?', (claim_id, doc['file_hash'], doc['document_type'])).fetchone():
                abort(409, 'This document is already attached.')
            name = secrets.token_hex(24) + doc['file_type']
            path = Path(current_app.config['UPLOAD_FOLDER']) / name
            try:
                path.write_bytes(document_path(doc).read_bytes())
                cur = db.execute('INSERT INTO documents(user_id,product_id,claim_id,document_type,original_name,stored_name,file_path,file_type,file_size,file_hash,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?,datetime(\'now\'))',
                                 (claim['user_id'], claim['product_id'], claim_id, doc['document_type'], doc['original_name'], name, name, doc['file_type'], doc['file_size'], doc['file_hash']))
                db.execute('INSERT INTO extracted_documents(document_id,raw_text,extracted_json,verified_json,verified_by,verified_at,extraction_status) SELECT ?,raw_text,extracted_json,verified_json,verified_by,verified_at,extraction_status FROM extracted_documents WHERE document_id=?', (cur.lastrowid, document_id))
                audit(db, 'saved document attached', doc['original_name'], claim_id)
                db.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return redirect(url_for('workflow.claim_detail', claim_id=claim_id))

    @bp.get('/claims/<int:claim_id>/card')
    def claim_summary_card(claim_id):
        with closing(get_db()) as db:
            claim_record(db, claim_id)
        abort(409, 'The original training card renderer is missing. Card download is unavailable until it is connected.')
