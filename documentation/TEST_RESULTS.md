# Test results

Command run on 2026-09-26:

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py workflow.py claim_services.py decision_service.py app_features.py ml_service.py src\train.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: 32 tests passed in 27.888 seconds. Python compilation completed without errors.

The checks cover account roles, CSRF, claim and warranty dates, products, documents, PDF text extraction, real local Tesseract image OCR, image upload and extraction through the verification route, document verification, product-document ownership, document copies attached to a claim, uploads, duplicate documents, duplicate claims, contradiction checks, repair records, notification deduplication, expiry and reporting alerts, policy snapshots, search filters, CSV formula escaping, reviewer transitions, decision overrides, evaluation history, confidence consistency states and final result logic.

The test stores are temporary. They do not add accounts, claims or documents to the working database.

Not established by these tests: OCR accuracy for varied real-world receipts, scanned PDF OCR, original training-data quality, model accuracy, the second classifier integration, live performance at 10,000 claims, uptime, public deployment and browser interaction behavior.
