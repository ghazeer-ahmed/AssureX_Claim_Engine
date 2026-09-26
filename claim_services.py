import io
import json
from pathlib import Path
import re
from datetime import date, timedelta
import os
import shutil

from flask import current_app

DOCUMENT_TYPES = ('Receipt', 'Warranty card', 'Product image', 'Serial evidence',
                  'Fault evidence', 'Repair report', 'Invoice', 'Other')
FAULT_TYPES = ('Manufacturing defect', 'Electrical failure', 'Mechanical failure',
               'Accidental damage', 'Liquid damage', 'Misuse', 'Other')
EDITABLE = ('Draft', 'Additional Information Required')
STATUSES = ('Draft', 'Submitted', 'Under Evaluation', 'Additional Information Required',
            'Manual Review', 'Approved', 'Rejected', 'Closed')


def read_policies():
    path = Path(current_app.config['POLICY_FILE'])
    if path.is_dir():
        policies = {}
        for file in sorted(path.glob('*.json')):
            policies.update(json.loads(file.read_text(encoding='utf-8')))
        return policies
    return json.loads(path.read_text(encoding='utf-8'))


def save_policy(category, policy):
    import secrets
    path = Path(current_app.config['POLICY_FILE'])
    if path.is_dir():
        # Category names are data, never filesystem paths.
        import hashlib
        existing = next((f for f in path.glob('*.json') if category in json.loads(f.read_text(encoding='utf-8'))), None)
        path = existing or path / (hashlib.sha256(category.encode()).hexdigest()[:16] + '.json')
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data[category] = policy
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def validate_upload(name, content):
    suffix = Path(name).suffix.lower()
    if not content or len(content) > 10 * 1024 * 1024:
        raise ValueError('Choose a non-empty file up to 10 MB.')
    if suffix in ('.jpg', '.jpeg', '.png'):
        from PIL import Image
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError('Image is too large. Use at most 25 megapixels.')
                if image.format != ( 'PNG' if suffix == '.png' else 'JPEG'):
                    raise ValueError('The file contents do not match the extension.')
                image.verify()
        except (OSError, SyntaxError, Image.DecompressionBombError) as error:
            raise ValueError('This image is damaged or unsupported.') from error
    elif suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError('This is not a valid PDF document.')
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or not reader.pages:
                raise ValueError('Use an unencrypted PDF containing at least one page.')
            if len(reader.pages) > 30:
                raise ValueError('PDFs may contain at most 30 pages.')
        except ImportError as error:
            raise ValueError('PDF support needs the dependencies in requirements.txt.') from error
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('The PDF could not be read.') from error
    elif suffix == '.mp4':
        if len(content) < 16 or content[4:8] != b'ftyp':
            raise ValueError('This is not an MP4 video.')
    else:
        raise ValueError('Supported files: PDF, JPG, JPEG, PNG and MP4.')
    return suffix


def extract_document(path):
    path = Path(path)
    if path.suffix == '.mp4':
        return '', {}, 'Video evidence does not support text extraction.'
    try:
        if path.suffix == '.pdf':
            from pypdf import PdfReader
            text = '\n'.join((page.extract_text() or '') for page in PdfReader(path).pages[:30])
            if not text.strip():
                return '', {}, 'Scanned PDF: upload its receipt page as a JPG or PNG for OCR, or enter the fields manually.'
        else:
            import pytesseract
            from PIL import Image
            command = os.environ.get('TESSERACT_CMD') or current_app.config.get('TESSERACT_CMD')
            if not command:
                command = shutil.which('tesseract')
            if command:
                pytesseract.pytesseract.tesseract_cmd = command
            else:
                raise FileNotFoundError('Tesseract is not installed.')
            with Image.open(path) as image:
                text = pytesseract.image_to_string(image, timeout=20)
    except (ImportError, FileNotFoundError):
        return '', {}, 'OCR is unavailable. Install the documented OCR dependencies or enter the fields manually.'
    except Exception:
        print('document extraction failed')
        return '', {}, 'Text extraction could not finish. Enter and verify the fields manually.'
    fields = {}
    patterns = {
        'invoice_number': r'(?:invoice|receipt)\s*(?:no\.?|number|#)?\s*[:#-]\s*([^\n]+)',
        'serial_number': r'(?:serial|s/n)\s*(?:number|no\.?)?\s*[:#-]\s*([^\n]+)',
        'model_number': r'model\s*(?:number|no\.?)?\s*[:#-]\s*([^\n]+)',
        'product_name': r'product\s*(?:name)?\s*:\s*([^\n]+)',
        'retailer': r'(?:retailer|seller|store)\s*:\s*([^\n]+)',
        'purchase_amount': r'(?:total|amount)\s*:\s*(?:[A-Z]{3}\s*)?([\d,.]+)',
        'warranty_duration': r'warranty\s*:\s*(\d+)\s*months?',
        'purchase_date': r'(?:purchase\s*date|date)\s*:\s*(\d{4}-\d{2}-\d{2})',
    }
    for key, pattern in patterns.items():
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            fields[key] = found.group(1).strip()[:200]
    return text[:50000], fields, 'Extracted. Review every field before saving.'


def evaluate_claim(db, claim):
    findings = []
    def add(key, result, details):
        if result != 'Pass':
            group = 'duplicates' if key.startswith('duplicate_') else key
            if key in policy.get('hard_fail_rules', []) or group in policy.get('hard_fail_rules', []):
                result = 'Fail'
            elif key in policy.get('manual_review_rules', []) or group in policy.get('manual_review_rules', []):
                result = 'Review'
            elif key in policy.get('warning_rules', []) or group in policy.get('warning_rules', []):
                result = 'Warning'
        findings.append(dict(rule_name=key, result=result, details=details))
    product = db.execute('SELECT * FROM products WHERE id=?', (claim['product_id'],)).fetchone()
    warranty = db.execute('SELECT * FROM warranties WHERE id=?', (claim['warranty_id'],)).fetchone()
    policies = read_policies()
    policy = next((v for k, v in policies.items() if k.casefold() == product['category'].casefold()), None)
    configured = bool(policy)
    policy = policy or {}
    add('policy', 'Pass' if configured else 'Review', 'Category policy found.' if configured else 'No policy is configured for this product category. Reviewer must verify coverage.')
    def parsed(value):
        try:
            return date.fromisoformat(value or '')
        except ValueError:
            return None
    purchase = parsed(product['purchase_date'])
    fault = parsed(claim['fault_occurrence_date'])
    submitted = parsed(claim['submission_date']) or date.today()
    if not purchase or not fault or fault < purchase or fault > submitted:
        add('contradictions', 'Review', 'Check purchase, fault and submission dates. Fault must be between purchase and submission.')
    else:
        add('contradictions', 'Pass', 'Purchase, fault and submission dates are consistent.')
    if configured and warranty and fault:
        start, expiry = parsed(warranty['start_date']), parsed(warranty['expiry_date'])
        start_issue = warranty['warranty_type'] == 'standard' and policy.get('start_condition') == 'purchase_date' and start != purchase
        add('start_condition', 'Review' if start_issue else 'Pass', 'Standard warranty must start on purchase date.' if start_issue else 'Recorded warranty start satisfies the start condition.')
        covered = start and expiry and start <= fault <= expiry + timedelta(days=policy['grace_days'])
        add('coverage', 'Pass' if covered else 'Fail', 'Fault date is within warranty coverage and grace period.' if covered else 'Fault date falls outside the recorded coverage period.')
    else:
        add('coverage', 'Review', 'A linked warranty and valid fault date are required.')
    if configured:
        late = fault and (submitted - fault).days > policy['reporting_days']
        add('reporting_period', 'Warning' if late else 'Pass', f"Report within {policy['reporting_days']} days of the fault. " + ('Reporting deadline exceeded.' if late else 'No reporting delay detected.'))
        if fault:
            from decision_service import load_limits
            deadline = fault + timedelta(days=policy['reporting_days'])
            add('reporting_deadline', 'Warning' if 0 <= (deadline - submitted).days <= load_limits()['deadline_alert_days'] else 'Pass', f'Reporting deadline: {deadline.isoformat()}. Submit your evidence before this date.')
        excluded = claim['damage_type'] in policy['exclusions']
        add('exclusions', 'Fail' if excluded else 'Pass', 'Damage type is excluded by the policy.' if excluded else 'Damage type is not listed as an exclusion.')
        fault_type = dict(claim).get('fault_category') or claim['damage_type']
        if fault_type not in policy['covered_faults'] and not excluded:
            add('fault_coverage', 'Review', 'Fault type requires individual coverage verification.')
    docs = db.execute('SELECT d.*, e.verified_json, e.verified_at FROM documents d LEFT JOIN extracted_documents e ON e.document_id=d.id WHERE d.claim_id=?', (claim['id'],)).fetchall()
    present = {d['document_type'] for d in docs}
    if 'Invoice' in present:
        present.add('Receipt')
    missing = [item for item in policy.get('mandatory_documents', []) if item not in present]
    if configured:
        add('documents', 'Review' if missing else 'Pass', 'Missing: ' + ', '.join(missing) if missing else 'All required document types are attached.')
    else:
        add('documents', 'Review', 'Required documents cannot be checked without the category policy.')
    evidence = [json.loads(d['verified_json'] or '{}') for d in docs if d['verified_at']]
    def norm(value):
        return re.sub(r'\s+', '', str(value)).casefold()
    serials = [v['serial_number'] for v in evidence if v.get('serial_number')]
    mismatch = any(norm(v) != norm(product['serial_number']) for v in serials)
    add('serial', 'Review' if mismatch or not serials else 'Pass', 'Serial numbers do not match the registered product.' if mismatch else ('No verified serial evidence yet.' if not serials else 'Verified serial values match.'))
    contradictions = []
    for record in evidence:
        for key in ('purchase_date', 'model_number', 'product_name', 'retailer'):
            if record.get(key) and product[key] and norm(record[key]) != norm(product[key]):
                contradictions.append(key.replace('_', ' '))
        if record.get('purchase_amount') and abs(float(record['purchase_amount']) - (product['purchase_price'] or 0)) > .01:
            contradictions.append('purchase amount')
    add('document_consistency', 'Review' if contradictions else 'Pass', 'Evidence differs from product: ' + ', '.join(sorted(set(contradictions))) if contradictions else 'No contradictions in verified document fields.')
    unverified = any(not d['verified_at'] for d in docs if d['document_type'] in ('Receipt', 'Invoice', 'Warranty card', 'Serial evidence'))
    if unverified:
        add('verification', 'Review', 'Review and verify receipt, warranty and serial evidence fields.')
    duplicate = db.execute('SELECT 1 FROM claims c JOIN products p ON p.id=c.product_id WHERE c.id!=? AND c.status!=? AND (c.product_id=? OR lower(p.serial_number)=lower(?)) LIMIT 1', (claim['id'], 'Draft', product['id'], product['serial_number'])).fetchone()
    add('duplicate_claim', 'Review' if duplicate else 'Pass', 'Another submitted claim uses this product or serial number. Reviewer must inspect the history.' if duplicate else 'No other submitted claim for this product or serial number.')
    repeated = db.execute("SELECT 1 FROM claims WHERE id!=? AND user_id=? AND status!='Draft' AND lower(trim(fault_description))=lower(trim(?)) LIMIT 1", (claim['id'], claim['user_id'], claim['fault_description'])).fetchone()
    add('duplicate_details', 'Review' if repeated else 'Pass', 'Another submitted claim from this customer has the same fault description.' if repeated else 'No repeated claimant and fault description found.')
    duplicate_doc = db.execute('SELECT 1 FROM documents a JOIN documents b ON a.file_hash=b.file_hash AND a.id!=b.id WHERE a.claim_id=? AND b.claim_id!=? LIMIT 1', (claim['id'], claim['id'])).fetchone()
    add('duplicate_document', 'Review' if duplicate_doc else 'Pass', 'Evidence content is also attached to another claim.' if duplicate_doc else 'No reused document content detected.')
    invoice_duplicate = False
    invoices = {norm(v['invoice_number']) for v in evidence if v.get('invoice_number')}
    if invoices:
        others = db.execute('SELECT e.verified_json FROM extracted_documents e JOIN documents d ON d.id=e.document_id WHERE d.claim_id!=? AND e.verified_at IS NOT NULL', (claim['id'],)).fetchall()
        invoice_duplicate = any(norm(json.loads(r['verified_json']).get('invoice_number', '')) in invoices for r in others)
    add('duplicate_invoice', 'Review' if invoice_duplicate else 'Pass', 'A verified invoice number is used in another claim.' if invoice_duplicate else 'No repeated verified invoice number.')
    repairs = db.execute('SELECT * FROM repairs WHERE product_id=?', (product['id'],)).fetchall()
    repair_problem = any((policy.get('authorized_repairs_only') and not r['authorized']) or not parsed(r['repair_date']) or (purchase and parsed(r['repair_date']) < purchase) for r in repairs)
    add('repairs', 'Review' if repair_problem else 'Pass', 'Repair history includes unauthorized service or inconsistent dates.' if repair_problem else 'No repair authorization/date issues found.')
    repair_docs = [name for name in policy.get('repair_documents', []) if name not in present]
    if repairs and repair_docs:
        add('repair_document', 'Review', 'Missing repair evidence: ' + ', '.join(repair_docs))
    replacement = claim['previous_replacement_details']
    condition = policy.get('replacement_condition')
    if replacement and configured:
        result = 'Pass' if condition == 'Allowed' else ('Fail' if condition == 'Not covered' else 'Review')
        add('replacement', result, 'Previous replacement reported. Policy: ' + condition)
    return findings


def claim_summary(db, claim, findings):
    warranty = db.execute('SELECT * FROM warranties WHERE id=?', (claim['warranty_id'],)).fetchone()
    repairs = db.execute('SELECT COUNT(*) FROM repairs WHERE product_id=?', (claim['product_id'],)).fetchone()[0]
    evidence = db.execute('SELECT COUNT(*) FROM documents WHERE claim_id=?', (claim['id'],)).fetchone()[0]
    issues = [f['details'] for f in findings if f['result'] != 'Pass']
    return dict(text=f"{claim['product_name']} ({claim['serial_number']}): {claim['fault_description']} "
                f"Fault reported on {claim['fault_occurrence_date']}. {repairs} repair record(s), {evidence} evidence file(s). "
                f"Current status: {claim['status']}.", issues=issues, warranty=dict(warranty) if warranty else None,
                remaining_days=max(0, (date.fromisoformat(warranty['expiry_date']) - date.today()).days) if warranty else 0)
