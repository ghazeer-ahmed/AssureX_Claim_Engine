# Test Results

**Test date:** 2026-09-28
**Command:** `.venv\Scripts\python.exe -m unittest discover -s tests -v`
**Result:** 37 tests passed.

## Automated test coverage

The suite passed decision-logic tests and application workflow tests using temporary databases and upload directories. The current 37 tests cover:

- Account registration, login, privileged-role protection, CSRF checks, login throttling, role access, and employee/customer assignment.
- Product and warranty validation, date boundaries, warranty policy snapshots, alerts, claim creation and state transitions, reviewer actions, comments, overrides, and history.
- PDF text extraction, real image OCR, the uploaded-image OCR route, and scanned-PDF OCR. The PDF tests cover text PDFs, scanned receipts, and mixed PDFs containing selectable text and scanned pages. A real Tesseract image test verifies all eight SRS receipt fields: purchase date, invoice number, product name, model number, serial number, retailer, purchase amount, and warranty duration.
- Upload validation, file hashes, duplicate evidence, claim duplicate checks, contradictions, private evidence authorization, report access, filters, notifications, and CSV formula escaping.
- Loading the active Python model through the application prediction route, storing three valid class probabilities and the model artifact hash.
- Serving the local TensorFlow.js graph-model assets; accepting and storing a three-class image prediction with its artifact hash.
- Both model outputs and the end-to-end review workflow, including decision thresholds and human review routing.
- Reading, merging, and editing separate category-specific warranty policy JSON files.

The suite reported a Joblib/NumPy deprecation warning during model deserialization; it did not fail the test or affect the prediction. Static-file test responses are explicitly closed to avoid leaving streamed files open.

## Held-out model evaluation

A separate evaluation dated 2026-09-29 ran the GTM SavedModel against the same 225 reserved test claims and matching cards. The Python classifier achieved **91.11% accuracy**. GTM achieved **34.67% accuracy** (78/225), with macro precision of 37.00%, macro recall of 34.67%, and macro F1 of 31.06%. Its result is below the SRS requirement of at least 85% for both models. Python and GTM agreed on 78 claims (34.67%) and disagreed on 147. GTM is not accurate enough to decide claims by itself. See [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md), [`metrics.json`](../reports/gtm_model_evaluation_2026-09-29/metrics.json), and [`test_predictions.csv`](../reports/gtm_model_evaluation_2026-09-29/test_predictions.csv).

## What this run does not establish

The tests and holdout evaluation do not prove real-world OCR accuracy across varied receipts, five-second end-to-end latency under target hardware, 10,000-claim performance, concurrent-user capacity, 99% uptime, accessibility, or mobile usability. The GTM inference path runs, but its measured accuracy fails the SRS target.
