import hashlib
import json
from datetime import date
from pathlib import Path

from flask import current_app
from claim_services import read_policies


MODEL_CLASSES = ('Valid Claim', 'Invalid Claim', 'Manual Review')


def latest_predictions(db, claim_id):
    rows = db.execute(
        'SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id '
        'WHERE p.claim_id=? ORDER BY p.id DESC', (claim_id,)).fetchall()
    res = {}
    for row in rows:
        res.setdefault(row['model_type'], row)
    return res


def _days_between(start, end):
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (TypeError, ValueError):
        return 0


def claim_features(db, claim, findings):
    """Map the live claim record to the saved training schema in its documented order."""
    product = db.execute('SELECT * FROM products WHERE id=?', (claim['product_id'],)).fetchone()
    warranty = db.execute('SELECT * FROM warranties WHERE id=?', (claim['warranty_id'],)).fetchone()
    policy_data = read_policies()
    policy = next((value for key, value in policy_data.items() if key.casefold() == product['category'].casefold()), {})
    docs = db.execute('SELECT d.document_type,e.verified_json,e.verified_at FROM documents d '
                      'LEFT JOIN extracted_documents e ON e.document_id=d.id WHERE d.claim_id=?', (claim['id'],)).fetchall()
    repairs = db.execute('SELECT * FROM repairs WHERE product_id=? ORDER BY repair_date,id', (product['id'],)).fetchall()
    evidence_types = {row['document_type'] for row in docs}
    if 'Invoice' in evidence_types:
        evidence_types.add('Receipt')
    missing = [kind for kind in policy.get('mandatory_documents', []) if kind not in evidence_types]
    verified = [json.loads(row['verified_json'] or '{}') for row in docs if row['verified_at']]
    normalize = lambda value: ''.join(str(value or '').split()).casefold()
    serials = [item['serial_number'] for item in verified if item.get('serial_number')]
    serial_match = bool(serials) and all(normalize(value) == normalize(product['serial_number']) for value in serials)
    contradictions = []
    for item in verified:
        for key in ('purchase_date', 'model_number', 'product_name', 'retailer'):
            if item.get(key) and product[key] and normalize(item[key]) != normalize(product[key]):
                contradictions.append(key)
        try:
            if item.get('purchase_amount') and abs(float(item['purchase_amount']) - (product['purchase_price'] or 0)) > .01:
                contradictions.append('purchase_amount')
        except (TypeError, ValueError):
            contradictions.append('purchase_amount')
    fault_before_purchase = int(bool(product['purchase_date'] and claim['fault_occurrence_date'] and claim['fault_occurrence_date'] < product['purchase_date']))
    repair_before_purchase = int(any(r['repair_date'] < product['purchase_date'] for r in repairs if r['repair_date'] and product['purchase_date']))
    fault_after_claim = int(bool(claim['submission_date'] and claim['fault_occurrence_date'] and claim['fault_occurrence_date'] > claim['submission_date']))
    model_mismatch = int('model_number' in contradictions)
    start = (warranty['start_date'] if warranty else product['purchase_date']) or ''
    expiry = warranty['expiry_date'] if warranty else ''
    fault_date = claim['fault_occurrence_date'] or ''
    submission_date = claim['submission_date'] or date.today().isoformat()
    covered_fault = claim['fault_category'] in policy.get('covered_faults', [])
    fault_covered = int(covered_fault and claim['damage_type'] not in policy.get('exclusions', []))
    remaining = _days_between(fault_date, expiry) if expiry else 0
    warranty_status = 'Unknown'
    if expiry:
        warranty_status = 'Active' if remaining >= 0 else 'Expired'
    if start and fault_date and fault_date < start:
        warranty_status = 'Not Started'
    duplicate = db.execute('SELECT 1 FROM claims c JOIN products p ON p.id=c.product_id '
                           'WHERE c.id!=? AND c.status!=? AND (c.product_id=? OR lower(p.serial_number)=lower(?)) LIMIT 1',
                           (claim['id'], 'Draft', product['id'], product['serial_number'])).fetchone()
    price = float(product['purchase_price'] or 0)
    age_days = _days_between(product['purchase_date'], fault_date)
    report_delay = max(0, _days_between(fault_date, submission_date))
    values = {
        'product_category': product['category'], 'brand': product['brand'], 'retailer': product['retailer'] or 'Unknown',
        'purchase_price': price, 'warranty_months': int(product['warranty_duration'] or 0),
        'extended_warranty': int(bool(warranty and warranty['warranty_type'].casefold() not in ('standard', 'manufacturer'))),
        'extended_months': max(0, int(product['warranty_duration'] or 0) - int(policy.get('coverage_months', product['warranty_duration'] or 0))) if warranty and warranty['warranty_type'].casefold() not in ('standard', 'manufacturer') else 0,
        'fault_category': claim['fault_category'] or 'Unknown', 'fault_covered': fault_covered,
        'damage_type': claim['damage_type'] or 'Unknown', 'claim_amount': float(claim['claim_amount'] or 0),
        'previous_repairs': len(repairs), 'last_repair_centre': (repairs[-1]['repair_center'] or 'Unknown') if repairs else 'None',
        'unauthorised_repair': int(any(not row['authorized'] for row in repairs)),
        'product_replaced_before': int(bool(claim['previous_replacement_details'])),
        'receipt_uploaded': int(bool(evidence_types & {'Receipt', 'Invoice'})),
        'warranty_card_uploaded': int('Warranty card' in evidence_types),
        'product_image_uploaded': int(bool(evidence_types & {'Product image', 'Product photo'})),
        'serial_evidence_uploaded': int('Serial evidence' in evidence_types),
        'fault_evidence_uploaded': int('Fault evidence' in evidence_types),
        'repair_report_uploaded': int('Repair report' in evidence_types), 'missing_documents': len(missing),
        'serial_match': int(serial_match), 'duplicate_claim_flag': int(bool(duplicate)),
        'contradiction_claim_before_purchase': fault_before_purchase,
        'contradiction_repair_before_purchase': repair_before_purchase,
        'contradiction_fault_after_claim': fault_after_claim, 'contradiction_model_mismatch': model_mismatch,
        'contradiction_count': int(bool(fault_before_purchase)) + int(bool(repair_before_purchase)) + int(bool(fault_after_claim)) + len(set(contradictions)),
        'product_age_days': age_days, 'remaining_warranty_days': remaining,
        'warranty_status': warranty_status, 'reporting_delay_days': report_delay,
        'reported_within_window': int(report_delay <= int(policy.get('reporting_days', 0))),
        'claim_to_price_ratio': float(claim['claim_amount'] or 0) / price if price else 0,
    }
    metrics = json.loads((Path(current_app.root_path) / 'models' / 'model_metrics.json').read_text(encoding='utf-8'))
    return {name: values[name] for name in metrics['features']}


def _record(db, claim_id, model_type, result, content, model_file):
    from decision_service import valid_scores
    if not valid_scores(result):
        raise ValueError('The classifier returned invalid probabilities.')
    version = hashlib.sha256(content).hexdigest()
    db.execute('INSERT OR IGNORE INTO model_versions(model_type,version,model_file,created_at,active) VALUES(?,?,?,datetime(\'now\'),1)',
               (model_type, version, model_file))
    version_id = db.execute('SELECT id FROM model_versions WHERE model_type=? AND version=?', (model_type, version)).fetchone()[0]
    cur = db.execute('INSERT INTO predictions(claim_id,model_version_id,model_type,predicted_class,valid_conf,invalid_conf,manual_conf,top_conf,created_at) '
                     'VALUES(?,?,?,?,?,?,?,?,datetime(\'now\'))',
                     (claim_id, version_id, model_type, result['predicted_class'], result['valid_conf'], result['invalid_conf'], result['manual_conf'], result['top_conf']))
    return db.execute('SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id WHERE p.id=?', (cur.lastrowid,)).fetchone()


def predict_and_store(db, claim, row):
    import joblib
    import pandas as pd
    root = Path(current_app.root_path)
    path = root / 'models' / 'python_claim_classifier.joblib'
    metrics_path = root / 'models' / 'model_metrics.json'
    metadata = json.loads(metrics_path.read_text(encoding='utf-8'))
    if list(row) != metadata['features']:
        raise ValueError('Feature names and order must match the saved training metadata.')
    content = path.read_bytes()
    model = joblib.load(path)
    scores = dict(zip(model.classes_, map(float, model.predict_proba(pd.DataFrame([row]))[0])))
    result = dict(predicted_class=max(scores, key=scores.get), valid_conf=scores['Valid Claim'],
                  invalid_conf=scores['Invalid Claim'], manual_conf=scores['Manual Review'], top_conf=max(scores.values()))
    return _record(db, claim['id'], 'Python', result, content, str(path.relative_to(root)))


def store_image_prediction(db, claim_id, scores):
    root = Path(current_app.root_path)
    directory = root / 'models'
    metadata = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    labels = {'valid_claim': 'Valid Claim', 'invalid_claim': 'Invalid Claim', 'manual_review': 'Manual Review'}
    if set(metadata.get('labels', [])) != set(labels) or not isinstance(scores, dict):
        raise ValueError('The image model labels do not match the claim classes.')
    normalized = {labels[key]: float(scores[key]) for key in labels if key in scores}
    if set(normalized) != set(MODEL_CLASSES):
        raise ValueError('The image model returned an incomplete class score set.')
    result = dict(predicted_class=max(normalized, key=normalized.get), valid_conf=normalized['Valid Claim'],
                  invalid_conf=normalized['Invalid Claim'], manual_conf=normalized['Manual Review'], top_conf=max(normalized.values()))
    content = b''.join((directory / name).read_bytes() for name in ('model.json', 'metadata.json', 'weights.bin'))
    return _record(db, claim_id, 'Keras', result, content, 'model.json + weights.bin')
