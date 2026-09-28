# SRS Module Review

This review compares the repository with the supplied *AssureX Claim Engine Software Requirements Specification, Version 1.0*. Status describes evidence in source and saved project outputs, not an assumption that every requirement has passed production testing.

**Status key:** Implemented means the relevant code or data is present. Partial means a related feature exists but its coverage or evidence is incomplete. Unverified means the SRS target cannot be claimed from current test evidence. Open means a required submission item is absent or blocked.

## Functional requirements

| SRS item | Status | Repository evidence and remaining work |
| --- | --- | --- |
| i. Registration, authentication, role access | Implemented | Customer registration, login, role checks, admin role assignment, employee/customer scoping. |
| ii. User profiles and unique user ID | Implemented | Profile pages and database user IDs. |
| iii. Product registration and product ID | Implemented | Product form stores category, brand, model, serial, purchase details, retailer, and warranty length. |
| iv. Standard/extended warranty records and status | Implemented | Warranty records, status pages, and expiry information. Policy coverage conditions are separately configured. |
| v. Receipt, invoice, and evidence uploads | Implemented | PDF/image/video validation, private storage, size/type checks, product and claim attachments. |
| vi. Receipt scanning and data extraction | Partial | Text PDFs, image OCR, and scanned-PDF OCR are implemented. Scanned PDFs are rendered through PyMuPDF and the first five pages are passed to Tesseract. Extracted values still require verification, and broad real-receipt accuracy is not established. |
| vii. Extracted-data verification | Implemented | Extracted values can be reviewed and corrected before verification. |
| viii. Warranty tracking | Implemented | Start/expiry, active/expired/approaching status and remaining period are calculated/displayed. |
| ix. Warranty expiry alerts | Partial | Alert refresh command and configurable days exist. A production scheduler and delivery-channel coverage are not evidenced. |
| x. Claim registration and unique claim ID | Implemented | Draft and submitted claim records have claim references and product/warranty links. |
| xi. Claim information collection | Implemented | Fault date, description, category, damage type, amount, history, and replacements are collected. |
| xii. Fault and damage evidence | Implemented | Supported upload workflow includes image, video, serial, fault, repair, receipt, and warranty evidence types. |
| xiii. Repair history | Implemented | Repair date, centre, parts, outcome, cost, and authorization fields are stored. |
| xiv. Document organization and access | Implemented | Product/claim document organization, access checks, view/download/replace/remove operations. |
| xv. Field, date, number, file, duplicate validation | Implemented | Input validation, file signature/type and size checks, duplicate claim and document checks. |
| xvi. Data preprocessing and derived fields | Implemented | `ml_service.py` maps data into the ordered feature schema, including derived dates, evidence counts, and ratios. |
| xvii. Common structured/image dataset | Partial | 1,500 CSV records, split map, and matching card manifest are present. Original scenario/label provenance is not fully documented. |
| xviii. Python classifier and algorithm comparison | Implemented | Training script compares logistic regression, random forest, and extra trees; fresh training compares three algorithms, selects by validation macro F1, and stores the scikit-learn 1.8 pipeline and aligned metadata in the active model paths. |
| xix. Python probabilities for three classes | Implemented | Inference code validates and stores scores for Valid Claim, Invalid Claim, and Manual Review. |
| xx. Claim Summary Card generation without model answer | Implemented | Shared renderer creates cards; Python output is not included in the card. |
| xxi. Teachable Machine image classifier | Partial | TensorFlow.js and Teachable Machine scripts are bundled locally. The exported model returned three-class scores for all 225 test cards; measured accuracy was 37.33%, below the SRS 85% target. |
| xxii. Predicted-class comparison | Partial | Comparison logic exists; end-to-end results on corresponding holdout cards are not verified. |
| xxiii. Top-confidence difference | Partial | Absolute confidence differences are calculated for all 225 matched holdout pairs and saved with consistency labels. |
| xxiv. Configurable consistency states | Implemented | Strong Match, Acceptable Match, Weak Match, Model Disagreement, and Uncertain Result logic uses configured thresholds. |
| xxv. Warranty-rule validation | Implemented | Policy checks cover dates, coverage, fault/exclusions, required evidence, repairs, serials, duplicates, and contradictions. Coverage of every SRS condition should be reviewed against each real policy. |
| xxvi. Configurable category policies | Partial | Three separate configurable category policy files are shipped: `laptop.json`, `smartphone.json`, and `appliance.json`. |
| xxvii. Serial-number verification | Partial | Verified extracted serial values are compared with the product record. Evidence sources and all serial conflict cases are not covered by OCR/vision. |
| xxviii. Contradiction detection | Partial | Date and verified-document/product conflicts are checked. Full cross-document conflict coverage described in the SRS is not evidenced. |
| xxix. Missing mandatory documents | Implemented | Category policy defines required document types and the workflow flags missing evidence. |
| xxx. Duplicate claim detection | Partial | Product/serial associations are checked. Invoice number, fault-description, claimant, and broad similarity comparisons are not all implemented. |
| xxxi. Duplicate file detection with hash | Implemented | Content hashes are stored and checked for exact duplicate files. |
| xxxii. Claim summary | Partial | Deterministic application summaries exist. They are rule/data summaries, not output from a generative AI service. |
| xxxiii. Claim preparation assistance | Implemented | Preparation and rule findings expose missing items and issues before submission. Deadline and corrective guidance need scenario-level verification. |
| xxxiv. Three-class final recommendation | Partial | Both model output routes record validated class scores and content hashes. Offline comparison covers 225 test claims; disagreement and uncertainty are routed to human review. The image model accuracy remains below target. |
| xxxv. Decision explanation | Implemented | Evaluation stores reasons and passed checks; reports/history expose review context. |
| xxxvi. Manual review queue and actions | Implemented | Review status transitions, information requests, and outcomes are present. |
| xxxvii. Reviewer comments and overrides | Implemented | Reviewer actions and explanations are stored in review/audit history. |
| xxxviii. Claim status tracking | Implemented | Draft, manual review, additional information, approved, rejected, and closed workflow states are represented. |
| xxxix. Notifications and alerts | Partial | In-app notifications and alert refresh operations exist. The full SRS event list and external delivery are not evidenced. |
| xl. Customer dashboard | Implemented | Product, warranty, claim, and pending-action views are present. |
| xli. Administrator dashboard | Partial | Administrative metrics and security events exist. Verify every requested total, confidence, disagreement, duplicate, and trend measure against populated data. |
| xlii. Search and filtering | Implemented | Claim, product, status, category, serial, date, reviewer, confidence/risk filters are present. |
| xliii. Analytics and reporting | Partial | Claim and rule analytics, CSV exports, and dashboards exist. Trained-model performance analytics and full rejection-reason coverage need further evidence. |
| xliv. Downloadable claim report | Implemented | HTML report includes claim, evidence, rules, model/evaluation history where available, and reviewer information. Browser printing can produce a PDF. |
| xlv. Data export | Implemented | CSV exports are available and escape formula-like values. CSV is Excel-compatible; native `.xlsx` export is not evidenced. |
| xlvi. Database storage | Implemented | SQLite stores accounts, claims, records, predictions, rules, notifications, and audit data. Encryption at rest is not implemented/evidenced. |
| xlvii. Audit trail | Implemented | Important account, document, workflow, review, and decision actions create audit events. |
| xlviii. Model version tracking | Implemented | Prediction records link to model versions and content hashes. Active model hashes and matching metrics are recorded in metadata; prediction versions use artifact content hashes. |
| xlix. Understandable error handling | Partial | Validation errors and error pages exist; unavailable models fall back to manual review. Database and prediction failure messages need broader browser verification. |
| l. Monitoring and anomaly alerts | Partial | Login/security events and some duplicate/model review flags exist. Complete monitoring for uploads, low confidence, and model disagreement is not evidenced. |
| Responsive browser interface | Partial | Responsive templates and styles are present. Desktop/tablet/mobile usability has not been systematically verified. |

## Non-functional requirements

| SRS target | Status | Evidence and gap |
| --- | --- | --- |
| Model inference within five seconds | Unverified | Not measured under representative deployment hardware and load. The browser holdout batch is not a single-claim latency test. |
| At least 10,000 claims and concurrent users | Unverified | No load, concurrency, or database scale test is recorded. |
| Usable interface across user roles/devices | Partial | Role-oriented screens exist; no completed accessibility or device-width evaluation is recorded. |
| At least 85% accuracy for both models | Partial | Python is 91.11% on 225 prepared test records. Teachable Machine is 37.33% on the same 225 cards, so the dual-model accuracy requirement fails. |
| 99% business-hours availability | Unverified | No deployment monitoring or uptime record is present. |

## Dataset and model evidence

The checked-in split metadata reports 1,500 records, balanced across the three classes, split 70/15/15. The card manifest contains 2,550 images: 2,100 training images and 225 each for validation and test. The Python evaluation was freshly rerun on 2026-09-28 and is documented in [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md).

The active logistic regression pipeline was freshly trained with scikit-learn 1.8.0, selected by validation macro F1, and evaluated on the reserved test split at 91.11% accuracy. `models/model_metrics.json` and `models/python_claim_classifier.joblib` now identify the same artifact version. The Teachable Machine export ran on all 225 corresponding test cards and achieved 37.33% accuracy. The detailed per-claim comparisons are in `reports/python_model_evaluation_2026-09-28/model_comparison_2026-09-28.csv`. The SRS 85% target is met by Python but not by the image model.

The test suite was rerun on 2026-09-28: 36 tests passed. Coverage now includes the active Python inference endpoint, local model asset delivery and image-score persistence endpoint, image OCR, text PDF extraction, scanned-PDF OCR, separate category policy files, and end-to-end claim/reviewer transitions. Browser inference was run against the complete isolated test-card set using the exact vendored JavaScript runtime.

## SRS deliverables

| Deliverable | Status |
| --- | --- |
| Project report | Updated in `PROJECT_REPORT.md` and the accompanying Word file. |
| Complete source code and installation guide | Present; see root `README.md`. |
| Structured dataset and card dataset | Present with split and claim mapping files. Dataset creation/label provenance needs documentation. |
| Python model training evidence | Fresh metrics, model, preprocessing artifact, and test predictions under `reports/python_model_evaluation_2026-09-28/`. |
| Teachable Machine evidence | Export and 225 holdout scores are present. Accuracy is 37.33%, below the SRS target; retraining is required. |
| Model comparison report for 30+ unseen claims | Complete for 225 claims in `reports/python_model_evaluation_2026-09-28/`; model-quality target remains open. |
| Warranty policies | Three separate JSON policy files are present under `policies/`. |
| Automated test cases/results | 36 tests passed on 2026-09-28. Specialized Google TM training/test and load targets remain as noted. |
| Installation and execution instructions | Present in root `README.md`. |
| Public deployment and evaluator credentials | No verified public deployment or safe evaluator credential package in this checkout. |
| Demonstration video | Not found in the reviewed Documentation folder. |
| Technical blog | Medium-ready draft in `AssureX_Claim_Engine_Technical_Blog.md` and Word format. |
| AI tool usage declaration | `AI_USAGE.md` is empty as directed; this does not satisfy the SRS AI disclosure requirement. |
| Team understanding and contribution evidence | Must be completed by the team truthfully; automated assistance does not establish student verification. |

## Competition integrity and team verification

The SRS asks each team member to understand and explain assigned modules, maintain accurate development evidence, and perform changes during evaluation. This report does not claim student actions or verification that are not recorded. Team members should independently review the model run, confirm the dataset labels and source, run the application and tests, and complete the remaining demonstration and contribution evidence.

## References

- *AssureX Claim Engine Software Requirements Specification, Version 1.0, Aptech Limited.*
- [`PROJECT_REPORT.md`](PROJECT_REPORT.md)
- [`MODEL_EVALUATION.md`](MODEL_EVALUATION.md)
- [`TEST_RESULTS.md`](TEST_RESULTS.md)
