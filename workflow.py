from contextlib import closing
import csv
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import secrets
import sqlite3

import click
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from database.db import get_db
from claim_services import DOCUMENT_TYPES, EDITABLE, FAULT_TYPES, STATUSES, evaluate_claim, extract_document, read_policies, save_policy, validate_upload, claim_summary
from security import security_event
from decision_service import latest_evaluation, store_evaluation
from ml_service import claim_features, latest_predictions, predict_and_store, store_image_prediction

bp = Blueprint('workflow', __name__)


def now():
    return datetime.now().isoformat(timespec='seconds')


def audit(db, action, details, claim_id=None):
    db.execute('INSERT INTO audit(user_id,claim_id,action,details,created_at) VALUES(?,?,?,?,?)',
               (session.get('user_id'), claim_id, action, details, now()))


def notify(db, user_id, message, claim_id=None):
    db.execute('INSERT INTO notifications(user_id,claim_id,notification_type,message,is_read,created_at) VALUES(?,?,?,?,0,?)',
               (user_id, claim_id, 'claim update', message, now()))


@bp.before_request
def authenticated():
    if not session.get('user_id'):
        return redirect(url_for('login'))


def permitted_owner(db, owner_id):
    role = session.get('role')
    if role in ('admin', 'reviewer'):
        return True
    if role == 'customer':
        return owner_id == session['user_id']
    return bool(db.execute('SELECT 1 FROM employee_customers WHERE employee_id=? AND customer_id=?',
                           (session['user_id'], owner_id)).fetchone())


def claim_record(db, claim_id, edit=False):
    row = db.execute('SELECT c.*,p.product_name,p.category,p.serial_number,p.model_number,p.purchase_date,p.product_id AS public_product_id,u.name AS customer_name FROM claims c JOIN products p ON p.id=c.product_id JOIN users u ON u.id=c.user_id WHERE c.id=?', (claim_id,)).fetchone()
    if not row or not permitted_owner(db, row['user_id']):
        abort(404)
    if edit and (row['status'] not in EDITABLE or session.get('role') == 'reviewer'):
        abort(409, 'Evidence and claim details can only change in Draft or Additional Information Required status.')
    return row


def text_field(name, required=False, limit=4000):
    value = request.form.get(name, '').strip()
    if (required and not value) or len(value) > limit:
        abort(400, f"Enter {name.replace('_', ' ')} (maximum {limit} characters).")
    return value


def date_field(name):
    try:
        result = date.fromisoformat(text_field(name, True, 10))
    except ValueError:
        abort(400, 'Enter a valid date in YYYY-MM-DD format.')
    if result > date.today():
        abort(400, 'Dates in the future are not allowed here.')
    return result


def claim_fields(product):
    fault_date = date_field('fault_occurrence_date')
    try:
        purchase = date.fromisoformat(product['purchase_date'])
    except (ValueError, TypeError):
        abort(400, 'Correct the registered product purchase date before creating a claim.')
    if fault_date < purchase:
        abort(400, 'Fault date cannot be before purchase.')
    damage = text_field('damage_type', True, 100)
    if damage not in FAULT_TYPES:
        abort(400, 'Select a listed fault type.')
    category = text_field('fault_category', limit=100) or damage
    if category not in FAULT_TYPES:
        abort(400, 'Select a listed fault category.')
    amount = request.form.get('claim_amount', '').strip()
    try:
        amount = float(amount) if amount else None
        if amount is not None and (not math.isfinite(amount) or amount < 0):
            raise ValueError
    except ValueError:
        abort(400, 'Claim amount must be a finite non-negative number.')
    return (fault_date.isoformat(), text_field('fault_description', True), damage,
            text_field('service_history'), text_field('previous_replacement_details'),
            round((date.today() - purchase).days / 365.25, 3), category, amount)


def scoped_claims(db, limit=None, offset=0, count=False):
    conditions, params = [], []
    role = session['role']
    if role == 'customer':
        conditions.append('c.user_id=?'); params.append(session['user_id'])
    elif role == 'service_centre_employee':
        conditions.append('c.user_id IN (SELECT customer_id FROM employee_customers WHERE employee_id=?)'); params.append(session['user_id'])
    query = request.args.get('q', '').strip()[:200]
    if query:
        conditions.append('(c.claim_id LIKE ? OR p.product_id LIKE ? OR p.serial_number LIKE ? OR p.product_name LIKE ?)')
        params.extend(['%' + query + '%'] * 4)
    status = request.args.get('status', '')
    if status in STATUSES:
        conditions.append('c.status=?'); params.append(status)
    for field, column in [('category','p.category'), ('reviewer', 'r.reviewer_id')]:
        value = request.args.get(field, '').strip()
        if value:
            if field == 'reviewer':
                conditions.append('EXISTS(SELECT 1 FROM claim_reviews r WHERE r.claim_id=c.id AND r.reviewer_id=?)')
            else:
                conditions.append(column + '=?')
            params.append(value)
    for field, operator in [('from_date', '>='), ('to_date', '<=')]:
        value = request.args.get(field, '')
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                abort(400, 'Invalid date filter.')
            conditions.append('substr(c.created_at,1,10)' + operator + '?'); params.append(value)
    risk = request.args.get('risk', '')
    if risk == 'flagged':
        conditions.append("EXISTS(SELECT 1 FROM rule_results rr WHERE rr.claim_id=c.id AND rr.result!='Pass')")
    elif risk in ('Fail', 'Review', 'Warning'):
        conditions.append('EXISTS(SELECT 1 FROM rule_results rr WHERE rr.claim_id=c.id AND rr.result=?)')
        params.append(risk)
    warranty_status = request.args.get('warranty_status', '')
    if warranty_status:
        today = date.today().isoformat()
        cutoff = (date.today() + timedelta(days=current_app.config['WARRANTY_ALERT_DAYS'])).isoformat()
        choices = {'Active': ('w.start_date<=? AND w.expiry_date>=?', [today, today]), 'Expired': ('w.expiry_date<?', [today]), 'Upcoming': ('w.start_date>?', [today]), 'Approaching Expiry': ('w.start_date<=? AND w.expiry_date BETWEEN ? AND ?', [today, today, cutoff]), 'Extended': ("w.warranty_type='extended'", [])}
        if warranty_status not in choices:
            abort(400, 'Unknown warranty status.')
        clause, values = choices[warranty_status]
        conditions.append('EXISTS(SELECT 1 FROM warranties w WHERE w.id=c.warranty_id AND ' + clause + ')')
        params.extend(values)
    for field, operator in [('min_conf', '>='), ('max_conf', '<=')]:
        value = request.args.get(field, '')
        if value:
            try:
                value = float(value)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError
            except ValueError:
                abort(400, 'Confidence filters must be between zero and one.')
            conditions.append('(SELECT MIN(p.top_conf) FROM predictions p WHERE p.claim_id=c.id AND p.id IN (SELECT MAX(id) FROM predictions WHERE claim_id=c.id GROUP BY model_type))' + operator + '?')
            params.append(value)
    sql = 'SELECT c.*, p.product_name,p.category,p.serial_number,p.product_id AS public_product_id,u.name AS customer_name FROM claims c JOIN products p ON p.id=c.product_id JOIN users u ON u.id=c.user_id'
    if conditions:
        sql += ' WHERE ' + ' AND '.join(conditions)
    if count:
        return db.execute('SELECT COUNT(*) FROM (' + sql + ')', params).fetchone()[0]
    sql += ' ORDER BY c.id DESC'
    if limit is not None:
        sql += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
    return db.execute(sql, params).fetchall()


@bp.route('/claims')
def claims():
    with closing(get_db()) as db, db:
        page = max(1, request.args.get('page', 1, type=int))
        total = scoped_claims(db, count=True)
        page = min(page, max(1, (total + 24) // 25))
        rows = scoped_claims(db, limit=25, offset=(page-1)*25)
        reviewers = db.execute("SELECT id,name FROM users WHERE role IN ('admin','reviewer')").fetchall()
        return render_template('claims.html', claims=rows, statuses=STATUSES, reviewers=reviewers, page=page, pages=max(1,(total+24)//25), total=total)


@bp.route('/claims/new', methods=['GET', 'POST'])
def new_claim():
    if session.get('role') not in ('customer', 'service_centre_employee', 'admin',):
        abort(403)
    with closing(get_db()) as db, db:
        products = [p for p in db.execute('SELECT * FROM products ORDER BY id DESC').fetchall() if permitted_owner(db, p['user_id'])]
        warranties = [dict(w) for w in db.execute('SELECT * FROM warranties').fetchall() if w['product_id'] in {p['id'] for p in products}]
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
            product = next((p for p in products if str(p['id']) == request.form.get('product_id')), None)
            if not product:
                abort(400, 'Select one of your registered products.')
            warranty = next((w for w in warranties if str(w['id']) == request.form.get('warranty_id') and w['product_id'] == product['id']), None)
            if not warranty:
                abort(400, 'Select a warranty belonging to this product.')
            fields = claim_fields(product)
            public_id = 'CLM-' + secrets.token_hex(6).upper()
            cur = db.execute('INSERT INTO claims(claim_id,user_id,product_id,warranty_id,fault_occurrence_date,fault_description,damage_type,service_history,previous_replacement_details,product_age,fault_category,claim_amount,warranty_conditions,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (public_id, product['user_id'], product['id'], warranty['id'], *fields, warranty['coverage_conditions'], 'Draft', now()))
            audit(db, 'claim created', public_id, cur.lastrowid)
            flash('Draft saved. Attach and verify evidence before submitting.', 'success')
            return redirect(url_for('workflow.claim_detail', claim_id=cur.lastrowid))
        return render_template('claim_form.html', products=products, warranties=warranties, faults=FAULT_TYPES, fault_categories=FAULT_TYPES, damage_types=FAULT_TYPES, claim=None)


@bp.route('/claims/<int:claim_id>')
def claim_detail(claim_id):
    with closing(get_db()) as db, db:
        claim = claim_record(db, claim_id)
        documents = db.execute('SELECT d.*, e.extraction_status,e.verified_at FROM documents d LEFT JOIN extracted_documents e ON e.document_id=d.id WHERE claim_id=? ORDER BY d.id DESC', (claim_id,)).fetchall()
        findings = evaluate_claim(db, claim)
        reviews = db.execute('SELECT r.*,u.name FROM claim_reviews r JOIN users u ON u.id=r.reviewer_id WHERE claim_id=? ORDER BY r.id DESC', (claim_id,)).fetchall()
        history = db.execute('SELECT action,details,created_at FROM audit WHERE claim_id=? ORDER BY id DESC', (claim_id,)).fetchall()
        repairs = db.execute('SELECT * FROM repairs WHERE product_id=? ORDER BY repair_date DESC', (claim['product_id'],)).fetchall()
        library = db.execute('SELECT * FROM documents WHERE product_id=? AND claim_id IS NULL', (claim['product_id'],)).fetchall()
        return render_template('claim_detail.html', claim=claim, documents=documents, findings=findings, reviews=reviews, history=history, repairs=repairs, document_types=DOCUMENT_TYPES, faults=FAULT_TYPES, fault_categories=FAULT_TYPES, damage_types=FAULT_TYPES, predictions=latest_predictions(db, claim_id), evaluation=latest_evaluation(db, claim_id), library=library, summary=claim_summary(db, claim, findings),
                               editable=claim['status'] in EDITABLE and session['role'] != 'reviewer')


@bp.post('/claims/<int:claim_id>/edit')
def edit_claim(claim_id):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        claim = claim_record(db, claim_id, edit=True)
        product = db.execute('SELECT * FROM products WHERE id=?', (claim['product_id'],)).fetchone()
        fields = claim_fields(product)
        db.execute('UPDATE claims SET fault_occurrence_date=?,fault_description=?,damage_type=?,service_history=?,previous_replacement_details=?,product_age=?,fault_category=?,claim_amount=? WHERE id=?', (*fields, claim_id))
        audit(db, 'claim edited', 'Draft information updated.', claim_id)
    flash('Claim details saved.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim_id))


@bp.post('/claims/<int:claim_id>/submit')
def submit_claim(claim_id):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        claim = claim_record(db, claim_id, edit=True)
        snapshot = dict(claim)
        snapshot['submission_date'] = date.today().isoformat()
        findings = evaluate_claim(db, snapshot)
        db.execute('DELETE FROM rule_results WHERE claim_id=?', (claim_id,))
        for finding in findings:
            db.execute('INSERT INTO rule_results(claim_id,rule_name,result,details,created_at) VALUES(?,?,?,?,?)',
                       (claim_id, finding['rule_name'], finding['result'], finding['details'], now()))
        for finding in findings:
            if finding['rule_name'].startswith('duplicate_') and finding['result'] != 'Pass':
                db.execute('INSERT INTO security_events(event,subject,created_at) VALUES(?,?,?)', (finding['rule_name'], claim['claim_id'], now()))
        prediction_ids = session.pop('model_prediction_ids', {}).get(str(claim_id), {})
        first = db.execute("SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id WHERE p.id=? AND p.claim_id=? AND p.model_type='Python'",
                           (prediction_ids.get('Python'), claim_id)).fetchone() if prediction_ids.get('Python') else None
        second = db.execute("SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id WHERE p.id=? AND p.claim_id=? AND p.model_type='Keras'",
                            (prediction_ids.get('Keras'), claim_id)).fetchone() if prediction_ids.get('Keras') else None
        res = store_evaluation(db, claim_id, findings, first, second)
        db.execute("UPDATE claims SET status='Manual Review',submission_date=?,final_result=? WHERE id=?", (snapshot['submission_date'], res['result'], claim_id))
        audit(db, 'evaluation recorded', json.dumps(res), claim_id)
        if not first or not second:
            db.execute("INSERT INTO security_events(event,subject,created_at) VALUES('classification unavailable',?,?)", (claim['claim_id'], now()))
            for admin in db.execute("SELECT id FROM users WHERE role='admin'").fetchall():
                notify(db, admin['id'], claim['claim_id'] + ': one or more model predictions are unavailable; manual review required.', claim_id)
        evidence = [dict(row) for row in db.execute('SELECT d.id,d.document_type,d.original_name,d.file_hash,e.verified_json,e.verified_at FROM documents d LEFT JOIN extracted_documents e ON e.document_id=d.id WHERE d.claim_id=?', (claim_id,))]
        repair_history = [dict(row) for row in db.execute('SELECT * FROM repairs WHERE product_id=?', (claim['product_id'],))]
        audit(db, 'claim submitted', json.dumps({'claim': snapshot, 'checks': findings, 'policies': read_policies(), 'evidence': evidence, 'repairs': repair_history}, ensure_ascii=False), claim_id)
        notify(db, claim['user_id'], claim['claim_id'] + ' submitted for manual review.', claim_id)
    flash('Submitted for human review. Your evidence is locked until a reviewer requests changes.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim_id))


@bp.get('/claims/<int:claim_id>/model-card.png')
def claim_model_card(claim_id):
    from io import BytesIO
    from dataset_generator.render_cards import draw_card
    with closing(get_db()) as db:
        claim = claim_record(db, claim_id)
        findings = evaluate_claim(db, dict(claim))
        features = claim_features(db, claim, findings)
    card = BytesIO()
    draw_card({key: str(value) for key, value in dict(features, claim_id=claim['claim_id']).items()}, card, 1)
    card.seek(0)
    return send_file(card, mimetype='image/png', download_name='claim-summary.png', max_age=0)


@bp.get('/model-assets/<path:filename>')
def model_asset(filename):
    if filename not in {'model.json', 'metadata.json', 'weights.bin'}:
        abort(404)
    return send_file(Path(current_app.root_path) / 'models' / filename, conditional=True)


@bp.post('/claims/<int:claim_id>/predict/python')
def predict_python(claim_id):
    with closing(get_db()) as db, db:
        claim = claim_record(db, claim_id, edit=True)
        prediction_ids = session.get('model_prediction_ids', {})
        prediction_ids.pop(str(claim_id), None)
        session['model_prediction_ids'] = prediction_ids
        findings = evaluate_claim(db, dict(claim))
        prediction = predict_and_store(db, claim, claim_features(db, claim, findings))
        session['model_prediction_ids'] = {str(claim_id): {'Python': prediction['id']}}
        audit(db, 'Python model prediction recorded', prediction['predicted_class'], claim_id)
        return {'model': 'Python', 'class': prediction['predicted_class'], 'confidence': prediction['top_conf']}


@bp.post('/claims/<int:claim_id>/predict/keras')
def predict_keras(claim_id):
    try:
        scores = json.loads(request.form.get('scores', '{}'))
        with closing(get_db()) as db, db:
            claim_record(db, claim_id, edit=True)
            prediction = store_image_prediction(db, claim_id, scores)
            prediction_ids = session.get('model_prediction_ids', {})
            prediction_ids.setdefault(str(claim_id), {})['Keras'] = prediction['id']
            session['model_prediction_ids'] = prediction_ids
            audit(db, 'Keras image model prediction recorded', prediction['predicted_class'], claim_id)
            return {'model': 'Keras', 'class': prediction['predicted_class'], 'confidence': prediction['top_conf']}
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        abort(400, str(error))


@bp.post('/claims/<int:claim_id>/review')
def review_claim(claim_id):
    if session.get('role') not in ('reviewer', 'admin',):
        abort(403)
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        claim = claim_record(db, claim_id)
        action = text_field('action', True, 50)
        comment = text_field('comment', True)
        transitions = {
            'Manual Review': {'Under Evaluation', 'Additional Information Required', 'Approved', 'Rejected'},
            'Under Evaluation': {'Additional Information Required', 'Approved', 'Rejected'},
            'Approved': {'Closed', 'Manual Review'}, 'Rejected': {'Closed', 'Manual Review'},
        }
        if action not in transitions.get(claim['status'], set()):
            abort(409, 'This transition is unavailable. Refresh the claim to see its current status.')
        if claim['user_id'] == session['user_id']:
            abort(403, 'You cannot review your own claim.')
        db.execute('INSERT INTO claim_reviews(claim_id,reviewer_id,action,comment,previous_status,created_at) VALUES(?,?,?,?,?,?)',
                   (claim_id, session['user_id'], action, comment, claim['status'], now()))
        result = {'Approved': 'Likely Valid', 'Rejected': 'Likely Invalid'}.get(action, claim['final_result'] if action == 'Closed' else 'Manual Review Required')
        db.execute('UPDATE claims SET status=?,final_result=? WHERE id=?', (action, result, claim_id))
        audit(db, 'reviewer action', json.dumps({'from': claim['status'], 'to': action, 'previous_result': claim['final_result'], 'reason': comment}), claim_id)
        notify(db, claim['user_id'], claim['claim_id'] + ': ' + action + '. ' + comment, claim_id)
    flash('Review saved with its reason in the audit history.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim_id))


@bp.post('/claims/<int:claim_id>/documents')
def upload_document(claim_id):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        claim = claim_record(db, claim_id, edit=True)
        upload = request.files.get('document')
        kind = text_field('document_type', True, 100)
        if kind not in DOCUMENT_TYPES or not upload or not upload.filename:
            abort(400, 'Select an evidence type and a file.')
        content = upload.read(10 * 1024 * 1024 + 1)
        try:
            suffix = validate_upload(upload.filename, content)
        except ValueError as error:
            # Record after releasing this transaction to avoid a second writer lock.
            audit(db, 'upload rejected', str(error), claim_id)
            db.execute('INSERT INTO security_events(event,subject,created_at) VALUES(?,?,?)', ('upload rejected', claim['claim_id'], now()))
            flash(str(error), 'danger')
            return redirect(url_for('workflow.claim_detail', claim_id=claim_id))
        digest = hashlib.sha256(content).hexdigest()
        if db.execute('SELECT 1 FROM documents WHERE claim_id=? AND file_hash=? AND document_type=?', (claim_id, digest, kind)).fetchone():
            flash('This file is already attached with the same evidence type.', 'warning')
            return redirect(url_for('workflow.claim_detail', claim_id=claim_id))
        name = secrets.token_hex(24) + suffix
        folder = Path(current_app.config['UPLOAD_FOLDER'])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        try:
            path.write_bytes(content)
            cur = db.execute('INSERT INTO documents(user_id,product_id,claim_id,document_type,original_name,stored_name,file_path,file_type,file_size,file_hash,uploaded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (claim['user_id'], claim['product_id'], claim_id, kind, secure_filename(upload.filename)[:200] or ('evidence' + suffix), name, name, suffix, len(content), digest, now()))
            db.execute('INSERT INTO extracted_documents(document_id) VALUES(?)', (cur.lastrowid,))
            audit(db, 'document uploaded', f'{kind}: {name}', claim_id)
            db.commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise
    flash('Document attached. Use Verify to review the receipt or serial details.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim_id))


def document_record(db, document_id, edit=False):
    doc = db.execute('SELECT * FROM documents WHERE id=?', (document_id,)).fetchone()
    if not doc:
        abort(404)
    if not doc['claim_id']:
        if not permitted_owner(db, doc['user_id']):
            abort(404)
        if edit and session['role'] == 'reviewer':
            abort(403)
        return doc, dict(id=None, product_id=doc['product_id'], status='Draft', claim_id='Product documents')
    claim = claim_record(db, doc['claim_id'], edit=edit)
    return doc, claim


def document_path(doc):
    folder = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    path = (folder / doc['stored_name']).resolve()
    if path.parent != folder or not path.is_file():
        abort(404, 'Document file is unavailable.')
    return path


@bp.get('/documents/<int:document_id>/download')
def download_document(document_id):
    with closing(get_db()) as db, db:
        doc, _ = document_record(db, document_id)
        return send_file(document_path(doc), as_attachment=True, download_name=doc['original_name'])


@bp.post('/documents/<int:document_id>/delete')
def delete_document(document_id):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        doc, claim = document_record(db, document_id, edit=True)
        path = document_path(doc)
        audit(db, 'document removed', doc['document_type'] + ': ' + doc['original_name'], claim['id'])
        db.execute('DELETE FROM documents WHERE id=?', (document_id,))
    path.unlink(missing_ok=True)
    flash('Document removed. You can upload its replacement.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim['id']) if claim['id'] else url_for('workflow.product_documents', product_id=claim['product_id']))


@bp.route('/documents/<int:document_id>/verify', methods=['GET', 'POST'])
def verify_document(document_id):
    with closing(get_db()) as db, db:
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
        doc, claim = document_record(db, document_id, edit=request.method == 'POST')
        extraction = db.execute('SELECT * FROM extracted_documents WHERE document_id=?', (document_id,)).fetchone()
        if request.method == 'POST':
            if request.form.get('action') == 'extract':
                raw, fields, status = extract_document(document_path(doc))
                db.execute('UPDATE extracted_documents SET raw_text=?,extracted_json=?,extraction_status=? WHERE document_id=?', (raw, json.dumps(fields), status, document_id))
                audit(db, 'document scanned', status, claim['id'])
            else:
                names = ('purchase_date', 'invoice_number', 'product_name', 'model_number', 'serial_number', 'retailer', 'purchase_amount', 'warranty_duration')
                fields = {key: text_field(key, limit=200) for key in names}
                if fields['purchase_date']:
                    date_field('purchase_date')
                for key in ('purchase_amount', 'warranty_duration'):
                    if fields[key]:
                        try:
                            number = float(fields[key].replace(',', ''))
                            if not math.isfinite(number) or number < 0 or (key == 'warranty_duration' and (not number.is_integer() or number < 1)):
                                raise ValueError
                        except ValueError:
                            abort(400, 'Enter a valid amount and a positive whole warranty duration.')
                        fields[key] = str(number)
                db.execute('UPDATE extracted_documents SET verified_json=?,verified_by=?,verified_at=? WHERE document_id=?', (json.dumps(fields), session['user_id'], now(), document_id))
                audit(db, 'extracted data verified', json.dumps({'document_id': document_id, 'previous': extraction['verified_json'], 'verified': fields}), claim['id'])
                flash('Verified fields saved. They will be compared with the product details.', 'success')
            return redirect(url_for('workflow.verify_document', document_id=document_id))
        fields = json.loads(extraction['verified_json'] if extraction['verified_at'] else extraction['extracted_json'])
        return render_template('verify_document.html', doc=doc, claim=claim, extraction=extraction, fields=fields, return_url=url_for('workflow.claim_detail', claim_id=claim['id']) if claim['id'] else url_for('workflow.product_documents', product_id=claim['product_id']),
                               editable=claim['status'] in EDITABLE and session['role'] != 'reviewer')


@bp.post('/claims/<int:claim_id>/repairs')
def add_repair(claim_id):
    with closing(get_db()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        claim = claim_record(db, claim_id, edit=True)
        repair_date = date_field('repair_date')
        if repair_date.isoformat() < claim['purchase_date']:
            abort(400, 'Repair date cannot be before purchase.')
        try:
            cost = float(text_field('repair_cost', True, 20))
            if not math.isfinite(cost) or cost < 0:
                raise ValueError
        except ValueError:
            abort(400, 'Repair cost must be a finite non-negative amount.')
        db.execute('INSERT INTO repairs(product_id,claim_id,repair_date,repair_center,replaced_parts,repair_outcome,repair_cost,authorized,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                   (claim['product_id'], claim_id, repair_date.isoformat(), text_field('repair_center', True), text_field('replaced_parts'), text_field('repair_outcome', True), cost, int(request.form.get('authorized') == 'yes'), now()))
        audit(db, 'repair recorded', repair_date.isoformat(), claim_id)
    flash('Repair history added.', 'success')
    return redirect(url_for('workflow.claim_detail', claim_id=claim_id))


@bp.get('/dashboard')
def dashboard():
    from app_features import dashboard_data
    with closing(get_db()) as db, db:
        return render_template('dashboard.html', **dashboard_data(db))


@bp.route('/notifications', methods=['GET', 'POST'])
def notifications():
    with closing(get_db()) as db, db:
        from app_features import refresh_claim_alerts
        refresh_claim_alerts(db)
        if request.method == 'POST':
            db.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (session['user_id'],))
            return redirect(url_for('workflow.notifications'))
        rows = db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 200', (session['user_id'],)).fetchall()
        return render_template('notifications.html', notifications=rows)


@bp.get('/claims/<int:claim_id>/report')
def claim_report(claim_id):
    with closing(get_db()) as db, db:
        claim = claim_record(db, claim_id)
        docs = db.execute('SELECT original_name,document_type,file_hash,uploaded_at FROM documents WHERE claim_id=?', (claim_id,)).fetchall()
        reviews = db.execute('SELECT r.*,u.name FROM claim_reviews r JOIN users u ON u.id=r.reviewer_id WHERE claim_id=?', (claim_id,)).fetchall()
        saved = db.execute('SELECT * FROM rule_results WHERE claim_id=?', (claim_id,)).fetchall()
        history = db.execute('SELECT action,created_at FROM audit WHERE claim_id=? ORDER BY id', (claim_id,)).fetchall()
        snapshots = db.execute("SELECT details,created_at FROM audit WHERE claim_id=? AND action='claim submitted' ORDER BY id", (claim_id,)).fetchall()
        html = render_template('claim_report.html', claim=claim, docs=docs, reviews=reviews, findings=saved, history=history, summary=claim_summary(db,claim,saved), predictions=latest_predictions(db, claim_id), evaluation=latest_evaluation(db, claim_id), snapshots=[dict(created_at=s['created_at'],data=json.loads(s['details'])) for s in snapshots])
        return send_file(io.BytesIO(html.encode()), as_attachment=True, download_name=claim['claim_id'] + '-report.html', mimetype='text/html')


def csv_response(name, headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        # Spreadsheet programs interpret these prefixes as formulas, even inside quoted cells.
        writer.writerow(["'" + str(v) if str(v or '').lstrip().startswith(('=', '+', '-', '@')) else v for v in row])
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), as_attachment=True, download_name=name + '.csv', mimetype='text/csv')


@bp.get('/admin/export/<kind>')
def export_records(kind):
    if session.get('role') not in ('admin',):
        abort(403)
    with closing(get_db()) as db, db:
        if kind == 'claims':
            rows = scoped_claims(db)
            keys = ['claim_id', 'product_name', 'category', 'serial_number', 'status', 'damage_type', 'submission_date', 'final_result']
        elif kind == 'products':
            rows = db.execute('SELECT * FROM products ORDER BY id').fetchall()
            keys = ['product_id', 'product_name', 'category', 'brand', 'serial_number', 'purchase_date', 'purchase_price']
        elif kind == 'warranties':
            rows = db.execute('SELECT * FROM warranties ORDER BY id').fetchall()
            keys = ['id', 'product_id', 'warranty_type', 'provider', 'start_date', 'expiry_date']
        elif kind == 'analytics':
            from app_features import dashboard_data
            data = dashboard_data(db)
            rows = []
            for group in ('counts', 'categories', 'faults', 'outcomes', 'consistency', 'trends', 'repairs', 'rejections'):
                rows.extend(dict(metric=group, label=label, value=value) for label, value in data[group].items())
            rows.append(dict(metric='confidence', label='Average top confidence', value=data['average_conf']))
            keys = ['metric', 'label', 'value']
        else:
            abort(404)
        return csv_response(kind, keys, [[row[k] for k in keys] for row in rows])


@bp.route('/admin/users', methods=['GET', 'POST'])
def users():
    if session.get('role') not in ('admin',):
        abort(403)
    with closing(get_db()) as db, db:
        if request.method == 'POST':
            action = request.form.get('action')
            db.execute('BEGIN IMMEDIATE')
            if action == 'role':
                role = text_field('role', True, 40)
                target = db.execute('SELECT * FROM users WHERE id=?', (request.form.get('user_id'),)).fetchone()
                if not target or role not in ('customer', 'service_centre_employee', 'reviewer', 'admin'):
                    abort(400, 'Select a valid user and role.')
                if target['id'] == session['user_id']:
                    abort(400, 'You cannot change your own administrator role.')
                db.execute('UPDATE users SET role=? WHERE id=?', (role, target['id']))
                db.execute('DELETE FROM employee_customers WHERE employee_id=? OR customer_id=?', (target['id'], target['id']))
                audit(db, 'role changed', f"{target['user_id']}: {target['role']} -> {role}")
            elif action in ('assign', 'unassign'):
                employee = db.execute("SELECT id FROM users WHERE id=? AND role='service_centre_employee'", (request.form.get('employee_id'),)).fetchone()
                customer = db.execute("SELECT id FROM users WHERE id=? AND role='customer'", (request.form.get('customer_id'),)).fetchone()
                if not employee or not customer:
                    abort(400, 'Select an employee and a customer.')
                if action == 'assign':
                    db.execute('INSERT OR IGNORE INTO employee_customers VALUES(?,?)', (employee['id'], customer['id']))
                else:
                    db.execute('DELETE FROM employee_customers WHERE employee_id=? AND customer_id=?', (employee['id'], customer['id']))
                audit(db, 'service assignment', f"{action}: employee {employee['id']} / customer {customer['id']}")
            else:
                abort(400)
            flash('Access settings saved.', 'success')
            return redirect(url_for('workflow.users'))
        rows = db.execute('SELECT id,user_id,name,email,role FROM users ORDER BY id DESC').fetchall()
        assignments = db.execute('SELECT e.name AS employee,c.name AS customer,ec.* FROM employee_customers ec JOIN users e ON e.id=ec.employee_id JOIN users c ON c.id=ec.customer_id').fetchall()
        return render_template('users.html', users=rows, assignments=assignments)


@bp.route('/admin/policies', methods=['GET', 'POST'])
def policies():
    if session.get('role') not in ('admin',):
        abort(403)
    current = read_policies()
    if request.method == 'POST':
        category = text_field('category', True, 100)
        if category not in current:
            abort(400, 'Select a configured product category.')
        policy = current[category]
        for key in ('coverage_months', 'reporting_days', 'grace_days'):
            try:
                value = int(request.form.get(key, ''))
                if value < (1 if key == 'coverage_months' else 0) or value > 3650:
                    raise ValueError
            except ValueError:
                abort(400, 'Policy durations must be whole numbers within 0–3650; coverage must be positive.')
            policy[key] = value
        for key in ('covered_faults', 'exclusions', 'mandatory_documents'):
            values = request.form.getlist(key)
            allowed = DOCUMENT_TYPES if key == 'mandatory_documents' else FAULT_TYPES
            if not values or any(v not in allowed for v in values):
                abort(400, 'Choose valid policy options for each list.')
            policy[key] = values
        if set(policy['covered_faults']) & set(policy['exclusions']):
            abort(400, 'A fault cannot be both covered and excluded.')
        policy['authorized_repairs_only'] = request.form.get('authorized_repairs_only') == 'yes'
        for key, allowed in [('start_condition', ('purchase_date', 'recorded_start')), ('replacement_condition', ('Reviewer approval required', 'Allowed', 'Not covered'))]:
            value = request.form.get(key, policy.get(key, allowed[0]))
            if value not in allowed:
                abort(400, 'Select a valid policy condition.')
            policy[key] = value
        if request.form.get('edit_severity') == 'yes':
            allowed_rules = {'coverage','exclusions','reporting_period','documents','serial','duplicates','contradictions','repairs','replacement','start_condition','document_consistency','verification','repair_document','fault_coverage','reporting_deadline','duplicate_claim','duplicate_document','duplicate_invoice','duplicate_details'}
            used = set()
            for key in ('hard_fail_rules', 'warning_rules', 'manual_review_rules'):
                values = [v.strip() for v in request.form.get(key, '').split(',') if v.strip()]
                if not set(values) <= allowed_rules or used & set(values):
                    abort(400, 'Use listed rule names, each in only one severity group.')
                policy[key] = values
                used.update(values)
        save_policy(category, policy)
        with closing(get_db()) as db, db:
            audit(db, 'policy updated', json.dumps({category: policy}))
        flash('Policy saved. Existing submission snapshots remain in the audit history.', 'success')
        return redirect(url_for('workflow.policies'))
    return render_template('policies.html', policies=current, faults=FAULT_TYPES, document_types=DOCUMENT_TYPES)


def install_workflow(app):
    app.config.setdefault('POLICY_FILE', str(Path(app.root_path) / 'policies' / 'warranties.json'))
    from app_features import install_features
    install_features(app)
    app.register_blueprint(bp)

    @app.cli.command('init-db')
    def init_command():
        initialize_database(app)
        click.echo('Database initialized; existing records preserved.')

    @app.cli.command('create-admin')
    @click.option('--email', prompt=True)
    @click.option('--name', prompt=True)
    @click.password_option()
    def create_admin(email, name, password):
        if len(password) < 12 or '@' not in email or not name.strip():
            raise click.ClickException('Use a name, email and password of at least 12 characters.')
        try:
            with closing(get_db()) as db, db:
                db.execute('INSERT INTO users(user_id,name,email,password,role,created_at) VALUES(?,?,?,?,?,?)',
                           ('USR-' + secrets.token_hex(6).upper(), name.strip(), email.strip().lower(), generate_password_hash(password), 'admin', now()))
        except sqlite3.IntegrityError:
            raise click.ClickException('That email is already registered. Use an existing administrator to change its role.')
        click.echo('Administrator created.')

    @app.cli.command('refresh-alerts')
    def refresh_alerts():
        from app import update_warranties
        with closing(get_db()) as db, db:
            ids = [row[0] for row in db.execute('SELECT id FROM users')]
        for user_id in ids:
            update_warranties(user_id)
        from app_features import refresh_claim_alerts
        with closing(get_db()) as db, db:
            refresh_claim_alerts(db)
        click.echo('Warranty alerts refreshed.')

    for status in (400, 403, 404, 409, 413, 429, 500):
        def error_page(error, status=status):
            message = str(getattr(error, 'description', 'The request could not be completed.'))
            if status == 500:
                message = 'The request could not be completed. Please try again.'
            if status == 413:
                message = 'Upload one file at a time, up to 10 MB.'
            return render_template('error.html', code=status, message=message), status
        app.register_error_handler(status, error_page)


def initialize_database(app):
    with app.app_context():
        with closing(get_db()) as db, db:
            db.executescript((Path(app.root_path) / 'database' / 'schema.sql').read_text())
            columns = {row['name'] for row in db.execute('PRAGMA table_info(claims)')}
            if 'fault_category' not in columns:
                db.execute('ALTER TABLE claims ADD COLUMN fault_category TEXT')
            if 'claim_amount' not in columns:
                db.execute('ALTER TABLE claims ADD COLUMN claim_amount REAL')
            db.executescript((Path(app.root_path) / 'database' / 'workflow.sql').read_text())
