import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

BOOT = tempfile.TemporaryDirectory()
os.environ['ASSUREX_DATABASE'] = str(Path(BOOT.name) / 'bootstrap.db')
os.environ['ASSUREX_SECRET_KEY'] = 'integration-test-only-secret'
import app as module
from database.db import get_db
from workflow import initialize_database
from claim_services import extract_document, validate_upload
from PIL import Image


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        module.app.config.update(TESTING=True, DATABASE_FILE=str(folder/'test.db'), UPLOAD_FOLDER=str(folder/'uploads'), POLICY_FILE=str(folder/'policies.json'))
        policies = {}
        for policy_file in Path('policies').glob('*.json'):
            policies.update(json.loads(policy_file.read_text(encoding='utf-8')))
        (folder/'policies.json').write_text(json.dumps(policies), encoding='utf-8')
        self.original_config = module.config_file
        module.config_file = str(folder/'settings.json')
        Path(module.config_file).write_text(json.dumps(module.config))
        self.addCleanup(setattr, module, 'config_file', self.original_config)
        initialize_database(module.app)
        self.client = module.app.test_client()
        self.register('owner@example.test')
        self.login('owner@example.test')
        self.product()
        self.warranty()

    def db(self):
        with module.app.app_context():
            return get_db()

    def post(self, path, data=None, client=None, **kwargs):
        client = client or self.client
        with client.session_transaction() as session:
            token = session.setdefault('_csrf', 'integration-csrf')
        return client.post(path, data={**(data or {}), '_csrf': token}, **kwargs)

    def register(self, email, role='customer'):
        return self.post('/register', dict(name='Test User',email=email,password='StrongPassword123!',role=role))

    def login(self, email):
        return self.post('/login', dict(email=email,password='StrongPassword123!'))

    def product(self, **changes):
        values = dict(product_name='Laptop', category='Laptop', brand='Brand', model_number='M1', serial_number='SERIAL-1', purchase_date='2026-01-01', purchase_price='1000', retailer='Store', warranty_duration='12')
        return self.post('/products/add', {**values, **changes})

    def warranty(self):
        return self.post('/warranties/add/1', dict(warranty_type='standard',provider='Provider',start_date='2026-01-01',duration='12',coverage_conditions='Manufacturing faults',exclusions='Liquid damage'))

    def claim(self):
        r = self.post('/claims/new', dict(product_id='1',warranty_id='1',fault_occurrence_date='2026-02-01',fault_description='Screen fails to turn on.',damage_type='Electrical failure'))
        self.assertEqual(r.status_code, 302, r.data.decode())
        return int(r.location.rsplit('/',1)[-1])

    def image(self, color='white'):
        image = Image.new('RGB',(80,80),color)
        buffer = io.BytesIO(); image.save(buffer,format='PNG'); buffer.seek(0)
        return buffer

    def upload(self, claim_id, kind='Receipt'):
        r=self.post(f'/claims/{claim_id}/documents',dict(document_type=kind,document=(self.image(),'receipt.png')))
        self.assertEqual(r.status_code,302)
        db=self.db(); row=db.execute('SELECT id FROM documents ORDER BY id DESC LIMIT 1').fetchone(); db.close()
        return row['id']

    def as_reviewer(self):
        self.post('/logout')
        self.register('reviewer@example.test')
        db=self.db(); db.execute("UPDATE users SET role='reviewer' WHERE email='reviewer@example.test'"); db.commit(); db.close()
        self.login('reviewer@example.test')

    def as_admin(self):
        db=self.db(); db.execute("UPDATE users SET role='admin' WHERE email='owner@example.test'"); db.commit(); db.close()

    def test_csrf_and_privileged_signup(self):
        self.assertEqual(self.client.post('/products/add', data={}).status_code,400)
        self.post('/logout')
        self.register('bad@example.test',role='reviewer')
        db=self.db(); self.assertIsNone(db.execute("SELECT id FROM users WHERE email='bad@example.test'").fetchone()); db.close()

    def test_existing_product_validation(self):
        for change in [dict(purchase_date='not-a-date'), dict(purchase_date='2999-01-01'), dict(purchase_price='nan'),dict(purchase_price='inf'),dict(warranty_duration='99999')]:
            self.product(**change)
        db=self.db(); self.assertEqual(db.execute('SELECT COUNT(*) FROM products').fetchone()[0],1); db.close()

    def test_claim_dates_and_warranty_ownership(self):
        data=dict(product_id='1',warranty_id='999',fault_occurrence_date='2026-02-01',fault_description='Fault',damage_type='Electrical failure')
        self.assertEqual(self.post('/claims/new',data).status_code,400)
        data.update(warranty_id='1',fault_occurrence_date='2025-12-31')
        self.assertEqual(self.post('/claims/new',data).status_code,400)

    def test_end_to_end_review_and_locking(self):
        claim=self.claim(); doc=self.upload(claim)
        self.assertEqual(self.post(f'/documents/{doc}/verify', dict(action='verify',serial_number='SERIAL-1',invoice_number='INV-1',purchase_date='2026-01-01',purchase_amount='1000')).status_code,302)
        self.assertEqual(self.post(f'/claims/{claim}/submit').status_code,302)
        self.assertEqual(self.post(f'/claims/{claim}/submit').status_code,409)
        self.assertEqual(self.post(f'/documents/{doc}/delete').status_code,409)
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Approved',comment='OK')).status_code,403)
        self.as_reviewer()
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Additional Information Required',comment='Please add a warranty card.')).status_code,302)
        self.post('/logout'); self.login('owner@example.test')
        self.upload(claim,'Warranty card')
        self.post(f'/claims/{claim}/submit')
        self.post('/logout'); self.login('reviewer@example.test')
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Approved',comment='Evidence checked; reporting delay accepted.')).status_code,302)
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Rejected',comment='Bad transition')).status_code,409)
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Manual Review',comment='Reopen for correction.')).status_code,302)
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Rejected',comment='Coverage exclusion confirmed.')).status_code,302)
        db=self.db()
        self.assertEqual(db.execute('SELECT status FROM claims WHERE id=?',(claim,)).fetchone()[0],'Rejected')
        self.assertEqual(db.execute('SELECT COUNT(*) FROM claim_reviews WHERE claim_id=?',(claim,)).fetchone()[0],4)
        self.assertGreater(db.execute('SELECT COUNT(*) FROM audit WHERE claim_id=?',(claim,)).fetchone()[0],6)
        db.close()

    def test_owner_isolation_documents_reports_and_editing(self):
        claim=self.claim(); doc=self.upload(claim)
        self.post('/logout'); self.register('other@example.test'); self.login('other@example.test')
        for path in [f'/claims/{claim}',f'/claims/{claim}/report',f'/documents/{doc}/download',f'/documents/{doc}/verify']:
            self.assertEqual(self.client.get(path).status_code,404,path)
        self.assertEqual(self.post(f'/documents/{doc}/delete').status_code,404)
        self.assertNotIn(b'CLM-',self.client.get('/claims').data)

    def test_upload_validation_and_duplicate(self):
        claim=self.claim()
        for filename, content in [('evil.html',b'<script>alert(1)</script>'),('fake.png',b'not an image'),('fake.pdf',b'invalid')]:
            self.post(f'/claims/{claim}/documents',dict(document_type='Receipt',document=(io.BytesIO(content),filename)))
        db=self.db(); self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],0); db.close()
        self.upload(claim); self.upload(claim)
        db=self.db(); self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],1); db.close()

    def test_rule_snapshots_and_duplicate_evidence(self):
        one=self.claim(); doc=self.upload(one)
        self.post(f'/documents/{doc}/verify', dict(action='verify',serial_number='WRONG',invoice_number='INV-ONE'))
        self.post(f'/claims/{one}/submit')
        two=self.claim(); self.upload(two); self.post(f'/claims/{two}/submit')
        db=self.db()
        findings={r['rule_name']:r['result'] for r in db.execute('SELECT * FROM rule_results WHERE claim_id=?',(two,))}
        self.assertEqual(findings['duplicate_claim'],'Review'); self.assertEqual(findings['duplicate_document'],'Review')
        self.assertEqual(db.execute("SELECT result FROM rule_results WHERE claim_id=? AND rule_name='serial'",(one,)).fetchone()[0],'Review')
        snapshot=json.loads(db.execute("SELECT details FROM audit WHERE claim_id=? AND action='claim submitted'",(one,)).fetchone()[0])
        self.assertIn('policies',snapshot); db.close()

    def test_repair_date_and_cost(self):
        claim=self.claim()
        data=dict(repair_date='2025-01-01',repair_center='Centre',repair_cost='5',repair_outcome='Fixed')
        self.assertEqual(self.post(f'/claims/{claim}/repairs',data).status_code,400)
        data.update(repair_date='2026-01-15',repair_cost='nan')
        self.assertEqual(self.post(f'/claims/{claim}/repairs',data).status_code,400)
        data.update(repair_cost='10')
        self.assertEqual(self.post(f'/claims/{claim}/repairs',data).status_code,302)
        self.assertIn(b'unauthorized',self.client.get(f'/claims/{claim}').data.lower())

    def test_document_extraction_and_verification(self):
        claim=self.claim(); doc=self.upload(claim)
        with patch('workflow.extract_document',return_value=('Serial: SERIAL-1',{'serial_number':'SERIAL-1'},'Extracted')):
            self.assertEqual(self.post(f'/documents/{doc}/verify',dict(action='extract')).status_code,302)
        self.assertIn(b'SERIAL-1',self.client.get(f'/documents/{doc}/verify').data)
        self.assertEqual(self.post(f'/documents/{doc}/verify',dict(action='verify',purchase_amount='inf')).status_code,400)
        self.assertEqual(self.post(f'/documents/{doc}/verify',dict(action='verify',warranty_duration='1.5')).status_code,400)

    def test_pages_render_and_assets(self):
        claim=self.claim(); doc=self.upload(claim)
        for path in ['/dashboard','/claims','/claims/new','/notifications','/products','/warranties','/profile',f'/claims/{claim}',f'/documents/{doc}/verify','/static/js/app.js']:
            r=self.client.get(path); self.assertEqual(r.status_code,200,path); r.close()
        response=self.client.get(f'/claims/{claim}/report')
        self.assertEqual(response.status_code,200); self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertNotIn(b'js/main.js',self.client.get('/').data)
        self.as_admin()
        for path in ['/admin/users','/admin/policies','/admin/export/products','/admin/export/warranties','/admin/export/claims','/admin/export/analytics','/admin/warranty-settings']:
            self.assertEqual(self.client.get(path).status_code,200,path)

    def test_notifications_only_owner(self):
        claim=self.claim(); self.post(f'/claims/{claim}/submit')
        self.assertIn(b'submitted for manual review',self.client.get('/notifications').data)
        self.post('/notifications')
        db=self.db(); self.assertEqual(db.execute('SELECT COUNT(*) FROM notifications WHERE is_read=0').fetchone()[0],0); db.close()

    def test_login_throttle(self):
        self.post('/logout')
        for _ in range(8):
            self.post('/login',dict(email='owner@example.test',password='wrong'))
        self.assertEqual(self.login('owner@example.test').status_code,429)

    def test_employee_assignment(self):
        claim=self.claim()
        self.post('/logout'); self.register('employee@example.test')
        db=self.db(); db.execute("UPDATE users SET role='service_centre_employee' WHERE email='employee@example.test'"); db.commit(); db.close()
        self.login('employee@example.test')
        self.assertEqual(self.client.get(f'/claims/{claim}').status_code,404)
        db=self.db(); db.execute('INSERT INTO employee_customers VALUES(2,1)'); db.commit(); db.close()
        self.assertEqual(self.client.get(f'/claims/{claim}').status_code,200)
        self.assertEqual(self.client.get('/admin/users').status_code,403)

    def test_real_pdf_text_extraction(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        writer=PdfWriter(); page=writer.add_blank_page(width=400,height=300)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 20 260 Td (Invoice: INV-123) Tj 0 -20 Td (Serial: SERIAL-1) Tj 0 -20 Td (Date: 2026-01-01) Tj 0 -20 Td (Total: 1000) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        content=io.BytesIO(); writer.write(content)
        self.assertEqual(validate_upload('receipt.pdf',content.getvalue()),'.pdf')
        path=Path(self.temp.name)/'receipt.pdf'; path.write_bytes(content.getvalue())
        raw,fields,status=extract_document(path)
        self.assertEqual(fields['serial_number'],'SERIAL-1')
        self.assertEqual(fields['invoice_number'],'INV-123')
        self.assertEqual(fields['purchase_date'],'2026-01-01')

    def test_scanned_pdf_ocr(self):
        import pymupdf
        image = Image.new('RGB', (900, 380), 'white')
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('arial.ttf', 34)
        for index, line in enumerate(['Invoice: INV-SCAN-8', 'Serial: SERIAL-1', 'Date: 2026-01-01', 'Total: 1000']):
            draw.text((50, 40 + index * 75), line, fill='black', font=font)
        png = io.BytesIO(); image.save(png, format='PNG')
        pdf = pymupdf.open(); page = pdf.new_page(width=720, height=310)
        page.insert_image(page.rect, stream=png.getvalue())
        path = Path(self.temp.name) / 'scanned-receipt.pdf'
        pdf.save(path); pdf.close()
        with module.app.app_context():
            raw, fields, status = extract_document(path)
        self.assertIn('INV-SCAN-8', raw)
        self.assertEqual(fields['invoice_number'], 'INV-SCAN-8')
        self.assertEqual(fields['serial_number'], 'SERIAL-1')
        self.assertIn('Extracted', status)

    def test_mixed_pdf_ocr_scans_textless_pages(self):
        import pymupdf
        image = Image.new('RGB', (900, 380), 'white')
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('arial.ttf', 34)
        for index, line in enumerate(['Invoice: INV-MIXED-9', 'Serial: SERIAL-MIXED', 'Date: 2026-02-03', 'Total: 1250']):
            draw.text((50, 40 + index * 75), line, fill='black', font=font)
        png = io.BytesIO(); image.save(png, format='PNG')
        pdf = pymupdf.open()
        page = pdf.new_page(width=720, height=310)
        page.insert_text((40, 60), 'Typed cover page: supporting receipt follows.')
        scan = pdf.new_page(width=720, height=310)
        scan.insert_image(scan.rect, stream=png.getvalue())
        path = Path(self.temp.name) / 'mixed-receipt.pdf'
        pdf.save(path); pdf.close()
        with module.app.app_context():
            raw, fields, status = extract_document(path)
        self.assertIn('Typed cover page', raw)
        self.assertIn('INV-MIXED-9', raw)
        self.assertEqual(fields['invoice_number'], 'INV-MIXED-9')
        self.assertEqual(fields['serial_number'], 'SERIAL-MIXED')
        self.assertIn('Extracted', status)

    def test_separate_category_policy_files(self):
        from claim_services import read_policies, save_policy
        folder = Path(self.temp.name) / 'policy_files'; folder.mkdir()
        for name, category in [('laptop', 'Laptop'), ('smartphone', 'Smartphone'), ('appliance', 'Appliance')]:
            (folder / f'{name}.json').write_text(json.dumps({category: {'coverage_months': 12}}))
        previous = module.app.config['POLICY_FILE']
        module.app.config['POLICY_FILE'] = str(folder)
        self.addCleanup(module.app.config.__setitem__, 'POLICY_FILE', previous)
        with module.app.app_context():
            self.assertEqual(set(read_policies()), {'Laptop', 'Smartphone', 'Appliance'})
            save_policy('Laptop', {'coverage_months': 24})
            self.assertEqual(read_policies()['Laptop']['coverage_months'], 24)

    def test_python_model_prediction_route(self):
        claim_id = self.claim()
        response = self.post(f'/claims/{claim_id}/predict/python')
        self.assertEqual(response.status_code, 200, response.data.decode())
        result = response.get_json()
        self.assertIn(result['class'], ('Valid Claim', 'Invalid Claim', 'Manual Review'))
        db = self.db()
        prediction = db.execute('SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id WHERE p.claim_id=?', (claim_id,)).fetchone()
        db.close()
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction['model_type'], 'Python')
        self.assertEqual(len(prediction['version']), 64)
        self.assertAlmostEqual(prediction['valid_conf'] + prediction['invalid_conf'] + prediction['manual_conf'], 1.0, places=5)

    def test_teachable_machine_assets_and_prediction_route(self):
        claim_id = self.claim()
        for asset in ('vendor/tf.min.js', 'vendor/teachablemachine-image.min.js', 'vendor/bootstrap.min.css', 'vendor/bootstrap.bundle.min.js'):
            response = self.client.get(f'/static/{asset}')
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.data), 1000)
            response.close()
        for asset in ('model.json', 'metadata.json', 'weights.bin'):
            response = self.client.get(f'/model-assets/{asset}')
            self.assertEqual(response.status_code, 200)
            self.assertGreater(len(response.data), 100)
            response.close()
        scores = {'valid_claim': 0.1, 'invalid_claim': 0.8, 'manual_review': 0.1}
        response = self.post(f'/claims/{claim_id}/predict/keras', {'scores': json.dumps(scores)})
        self.assertEqual(response.status_code, 200, response.data.decode())
        self.assertEqual(response.get_json()['class'], 'Invalid Claim')
        db = self.db()
        prediction = db.execute('SELECT p.*,m.version FROM predictions p JOIN model_versions m ON m.id=p.model_version_id WHERE p.claim_id=?', (claim_id,)).fetchone()
        db.close()
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction['model_type'], 'Keras')
        self.assertEqual(len(prediction['version']), 64)

    def test_real_image_ocr(self):
        image = Image.new('RGB', (1000, 700), 'white')
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('arial.ttf', 32)
        lines = ['Invoice: INV-456', 'Product: Laptop Pro', 'Model: MOD-42', 'Serial: SERIAL-1', 'Retailer: Northwind Store', 'Purchase Date: 2026-01-01', 'Total: 1000', 'Warranty: 12 months']
        for index, line in enumerate(lines):
            draw.text((50, 20 + index * 78), line, fill='black', font=font)
        path = Path(self.temp.name) / 'receipt.png'
        image.save(path)
        with module.app.app_context():
            raw, fields, status = extract_document(path)
        self.assertIn('INV-456', raw)
        self.assertEqual(fields['invoice_number'], 'INV-456')
        self.assertEqual(fields['serial_number'], 'SERIAL-1')
        self.assertEqual(fields['purchase_date'], '2026-01-01')
        self.assertEqual(fields['product_name'], 'Laptop Pro')
        self.assertEqual(fields['model_number'], 'MOD-42')
        self.assertEqual(fields['retailer'], 'Northwind Store')
        self.assertEqual(fields['purchase_amount'], '1000')
        self.assertEqual(fields['warranty_duration'], '12')
        self.assertIn('Extracted', status)

    def test_uploaded_image_ocr_route(self):
        claim = self.claim()
        image = Image.new('RGB', (900, 380), 'white')
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('arial.ttf', 34)
        for index, line in enumerate(['Invoice: INV-789', 'Serial: SERIAL-1', 'Date: 2026-01-01', 'Total: 1000']):
            draw.text((50, 40 + index * 75), line, fill='black', font=font)
        content = io.BytesIO()
        image.save(content, format='PNG')
        content.seek(0)
        response = self.post(f'/claims/{claim}/documents', dict(document_type='Receipt', document=(content, 'receipt.png')))
        self.assertEqual(response.status_code, 302)
        db = self.db()
        document_id = db.execute('SELECT id FROM documents ORDER BY id DESC LIMIT 1').fetchone()[0]
        db.close()
        self.assertEqual(self.post(f'/documents/{document_id}/verify', dict(action='extract')).status_code, 302)
        response = self.client.get(f'/documents/{document_id}/verify')
        self.assertIn(b'INV-789', response.data)
        self.assertIn(b'SERIAL-1', response.data)
        self.assertIn(b'Extract text', response.data)
        self.assertIn(b'local Tesseract OCR', response.data)

    def test_policy_edits_and_immutable_submission(self):
        claim=self.claim(); self.post(f'/claims/{claim}/submit'); self.as_admin()
        data=dict(category='Laptop',coverage_months='24',reporting_days='60',grace_days='10',covered_faults=['Electrical failure'],exclusions=['Liquid damage'],mandatory_documents=['Receipt'],authorized_repairs_only='yes')
        self.assertEqual(self.post('/admin/policies',data).status_code,302)
        db=self.db(); snapshot=json.loads(db.execute("SELECT details FROM audit WHERE action='claim submitted'").fetchone()[0]); db.close()
        self.assertEqual(snapshot['policies']['Laptop']['reporting_days'],30)
        self.assertEqual(json.loads(Path(module.app.config['POLICY_FILE']).read_text())['Laptop']['reporting_days'],60)
        data['exclusions']=['Electrical failure']
        self.assertEqual(self.post('/admin/policies',data).status_code,400)

    def test_no_self_approval_and_empty_review_reason(self):
        claim=self.claim(); self.post(f'/claims/{claim}/submit'); self.as_admin()
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Approved',comment='Approve own claim')).status_code,403)
        self.as_reviewer()
        self.assertEqual(self.post(f'/claims/{claim}/review',dict(action='Approved',comment='')).status_code,400)

    def test_search_and_csv_formula_escape(self):
        self.product(product_name='=HYPERLINK("bad")',serial_number='SERIAL-2')
        self.assertNotIn(b'SERIAL-2',self.client.get('/products?q=SERIAL-1').data)
        self.assertNotIn(b'Provider',self.client.get('/warranties?status=Expired').data)
        self.as_admin()
        response=self.client.get('/admin/export/products')
        self.assertIn(b"'=HYPERLINK",response.data)

    def test_expiry_alert_deduplication(self):
        from datetime import date,timedelta
        expiry=(date.today()+timedelta(days=5)).isoformat()
        db=self.db(); db.execute('UPDATE warranties SET expiry_date=?',(expiry,)); db.commit(); db.close()
        self.client.get('/warranties'); self.client.get('/dashboard'); self.client.get('/notifications')
        db=self.db(); self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE notification_type='warranty expiry'").fetchone()[0],1); db.close()

    def test_boundary_dates(self):
        from datetime import date,timedelta
        self.assertEqual(module.add_months(date(2024,1,31),1),date(2024,2,29))
        self.assertEqual(module.add_months(date(2025,1,31),1),date(2025,2,28))
        self.assertEqual(module.get_warranty_status(date.today(),30)[0],'Approaching Expiry')
        self.assertEqual(module.get_warranty_status(date.today()-timedelta(days=1),30)[0],'Expired')
        self.assertEqual(module.get_warranty_status(date.today()+timedelta(days=90),30,date.today()+timedelta(days=2))[0],'Upcoming')


    def test_product_library_copy_and_ownership(self):
        res = self.post('/products/1/documents', dict(document_type='Receipt', document=(self.image(), 'receipt.png')))
        self.assertEqual(res.status_code, 302)
        db = self.db()
        doc = db.execute('SELECT id FROM documents').fetchone()[0]
        db.close()
        self.assertEqual(self.client.get(f'/documents/{doc}/verify').status_code, 200)
        self.post(f'/documents/{doc}/verify', dict(action='verify', serial_number='SERIAL-1'))
        claim = self.claim()
        self.assertEqual(self.post(f'/claims/{claim}/attach/{doc}').status_code, 302)
        self.assertEqual(self.post(f'/claims/{claim}/attach/{doc}').status_code, 409)
        self.post(f'/documents/{doc}/delete')
        db = self.db()
        attached = db.execute('SELECT * FROM documents WHERE claim_id=?', (claim,)).fetchone()
        self.assertIsNotNone(attached)
        self.assertTrue((Path(module.app.config['UPLOAD_FOLDER']) / attached['stored_name']).exists())
        db.close()
        self.post('/logout')
        self.register('other@example.test')
        self.login('other@example.test')
        self.assertEqual(self.client.get('/products/1/documents').status_code, 404)

    def test_missing_policy_has_no_invented_rules(self):
        claim = self.claim()
        Path(module.app.config['POLICY_FILE']).write_text('{}')
        self.post(f'/claims/{claim}/submit')
        db = self.db()
        checks = db.execute('SELECT rule_name,result FROM rule_results WHERE claim_id=?', (claim,)).fetchall()
        checks = dict(checks)
        self.assertEqual(checks['policy'], 'Review')
        self.assertEqual(checks['documents'], 'Review')
        self.assertNotIn('reporting_period', checks)
        self.assertIn('duplicate_document', checks)
        self.assertEqual(db.execute('SELECT final_result FROM claims WHERE id=?', (claim,)).fetchone()[0], 'Manual Review Required')
        db.close()

    def test_saved_evaluation_survives_override(self):
        import sqlite3
        claim = self.claim()
        self.post(f'/claims/{claim}/submit')
        db = self.db()
        original = db.execute('SELECT details FROM evaluations WHERE claim_id=?', (claim,)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE evaluations SET result='Likely Valid'")
        db.rollback()
        db.close()
        self.as_reviewer()
        self.post(f'/claims/{claim}/review', dict(action='Approved', comment='Evidence checked.'))
        db = self.db()
        self.assertEqual(db.execute('SELECT final_result FROM claims WHERE id=?', (claim,)).fetchone()[0], 'Likely Valid')
        self.assertEqual(db.execute('SELECT details FROM evaluations WHERE claim_id=?', (claim,)).fetchone()[0], original)
        db.close()
        self.assertIn(b'Manual Review Required', self.client.get(f'/claims/{claim}/report').data)

    def test_claim_fields_and_filter_validation(self):
        values = dict(product_id='1', warranty_id='1', fault_occurrence_date='2026-02-01', fault_description='Fault', damage_type='Electrical failure', fault_category='Mechanical failure', claim_amount='123.45')
        response = self.post('/claims/new', values)
        self.assertEqual(response.status_code, 302)
        db = self.db()
        row = db.execute('SELECT fault_category,claim_amount FROM claims').fetchone()
        self.assertEqual(tuple(row), ('Mechanical failure', 123.45))
        db.close()
        for amount in ['nan', 'inf', '-1']:
            self.assertEqual(self.post('/claims/new', {**values, 'claim_amount': amount}).status_code, 400)
        self.assertEqual(self.client.get('/claims?min_conf=nan').status_code, 400)
        self.assertEqual(self.client.get('/claims?warranty_status=bad').status_code, 400)
        self.assertEqual(self.client.get('/claims?warranty_status=Active').status_code, 200)

    def test_card_unavailable_without_original_renderer(self):
        claim = self.claim()
        response = self.client.get(f'/claims/{claim}/card')
        self.assertEqual(response.status_code, 409)
        self.assertIn(b'original training card renderer', response.data)

    def test_deadline_alert_deduplication(self):
        from datetime import date, timedelta
        claim = self.claim()
        db = self.db()
        db.execute('UPDATE claims SET fault_occurrence_date=? WHERE id=?', ((date.today()-timedelta(days=28)).isoformat(), claim))
        db.commit()
        db.close()
        self.client.get('/notifications')
        self.client.get('/notifications')
        db = self.db()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications WHERE message LIKE '%reporting deadline%'").fetchone()[0], 1)
        db.close()


if __name__ == '__main__':
    unittest.main()
