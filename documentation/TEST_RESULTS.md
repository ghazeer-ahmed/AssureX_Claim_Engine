# Test Results

**Test date:** 2026-09-28
**Command:** `.venv\Scripts\python.exe -m unittest discover -s tests -v`
**Result:** 36 tests passed.

## Automated test coverage

The suite passed decision-logic tests and application workflow tests using temporary databases and upload directories. The current 36 tests cover:

- Account registration, login, privileged-role protection, CSRF checks, login throttling, role access, and employee/customer assignment.
- Product and warranty validation, date boundaries, warranty policy snapshots, alerts, claim creation and state transitions, reviewer actions, comments, overrides, and history.
- PDF text extraction, real image OCR, the uploaded-image OCR route, and scanned-PDF OCR. The scanned-PDF test embeds a synthetic receipt image in a PDF, then checks OCR extraction of invoice number, serial number, and date.
- Upload validation, file hashes, duplicate evidence, claim duplicate checks, contradictions, private evidence authorization, report access, filters, notifications, and CSV formula escaping.
- Loading the active Python model through the application prediction route, storing three valid class probabilities and the model artifact hash.
- Serving local TensorFlow.js, Teachable Machine, Bootstrap, and all three model export files; accepting and storing a three-class image prediction with its artifact hash.
- Both model outputs and the end-to-end review workflow, including decision thresholds and human review routing.
- Reading, merging, and editing separate category-specific warranty policy JSON files.

The suite reported a Joblib/NumPy deprecation warning during model deserialization; it did not fail the test or affect the prediction. Static-file test responses are explicitly closed to avoid leaving streamed files open.

## Held-out model evaluation

The Python classifier and Teachable Machine image model were evaluated on the same 225 reserved test claims and their matching test cards. The active Python pipeline achieved **91.11% accuracy**. The Teachable Machine export ran successfully in the browser and achieved **37.33% accuracy**, below the SRS requirement of at least 85% for both models. The prediction classes matched on 85 of 225 claims (37.78%). The image model must be retrained and retested before the accuracy requirement can be claimed. See [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md) and the full per-claim comparison file in `../reports/python_model_evaluation_2026-09-28/`.

## What this run does not establish

The tests and holdout evaluation do not prove real-world OCR accuracy across varied receipts, five-second end-to-end latency under target hardware, 10,000-claim performance, concurrent-user capacity, 99% uptime, accessibility, or mobile usability. The image-model inference path runs, but its present accuracy fails the SRS target.
