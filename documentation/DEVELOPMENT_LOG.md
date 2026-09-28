# Development Log

## 2026-09-26 application work

The earlier development work added claim drafts, intake validation, linked warranty selection, evidence uploads, PDF and image handling, extraction and user verification, repair history, policy checks, duplicate detection, reviewer transitions, comments, dashboards, filters, CSV exports, HTML reports, access controls, CSRF checks, login throttling, audit events, and OCR setup.

The original log recorded 13 initial integration tests. The final test record later recorded 32 passing tests. See [`TEST_RESULTS.md`](TEST_RESULTS.md) for the recorded command and coverage. This work included AI assistance and must not be represented as student testing without independent team verification.

## 2026-09-28 documentation and model review

### Work completed

- Reviewed the current project report and technical blog draft in the Documentation folder against the supplied SRS.
- Replaced the previous blog outline with a Medium-ready technical article in Markdown and prepared a Word version with the same evidence and figures.
- Prepared a corrected SRS project report in Markdown and Word format.
- Rewrote the module review as an SRS traceability matrix, including functional requirements, non-functional targets, deliverables, and open work.
- Updated the test record and this development log to distinguish the last recorded application test run from the new model evaluation.
- Generated architecture, claim workflow, dataset split, validation comparison, test confusion matrix, and class metric figures in `documentation/figures/`.
- Reran `src/train.py` on the repository train/validation/test split and saved a separate evaluation run under `reports/python_model_evaluation_2026-09-28/`.

### Model result and issue found

At the time of the earlier entry, the Python and Teachable Machine evaluations were pending. Both evaluations were completed on 2026-09-28; the final results and follow-up changes are recorded in the system verification section below. That later evaluation supersedes the provisional statements in this entry.
## Student verification

This log does not claim student understanding, review, testing, or contribution that is not supported by team records. Each team member should review their assigned code and independently document the tests and modifications they perform.

## 2026-09-28 system verification and fixes

### Work completed

- Reran the original suite, then expanded it to 36 tests covering model routes, local runtime assets, scanned-PDF OCR, and separate category policies. The complete expanded suite passed.
- Replaced the version-mismatched active Python classifier with a fresh validation-selected scikit-learn 1.8.0 pipeline. Updated its preprocessing artifact and model metadata together. The active Python model achieved 91.11% on the reserved 225-claim test set.
- Bundled the project's pinned Bootstrap 5.3.3, TensorFlow.js 1.7.4, and Teachable Machine Image 0.8.5 browser scripts under `static/vendor/` with license notices. The UI and model inference no longer require those CDN scripts at runtime.
- Implemented scanned-PDF OCR by rendering up to five pages with PyMuPDF and sending those pages to Tesseract. Added portable Tesseract discovery through configuration, PATH, and common Windows install directories.
- Split the Laptop, Smartphone, and Appliance warranty definitions into three JSON policy files. The policy loader merges these files, and the admin policy editor can update category files.
- Ran browser inference on all 225 held-out Claim Summary Cards. The Teachable Machine model achieved 37.33% accuracy and agreed with Python on 85/225 claims. Saved class metrics, confusion matrices, consistency categories, artifact hashes, and a per-claim report under `reports/python_model_evaluation_2026-09-28/`.
- Updated README.md, model evaluation, the SRS module matrix, project report, technical blog, and test results.

### Known failures and open SRS targets

- The Teachable Machine inference integration works, but the exported model's 37.33% accuracy fails the 85% SRS threshold. The repository does not include the original Teachable Machine training project/settings. Retraining needs to be done using the train split, validation selection, and a final reserved test run.
- The 10,000-claim scale, five-second representative latency, 99% business-hours availability, and mobile accessibility/usability targets have not been measured.
- Dataset label and scenario provenance, demonstration video, and deployment evidence remain incomplete.
- `AI_USAGE.md` is empty as requested, so the SRS AI tool disclosure requirement is not met until the team adds the required declaration.

The local evaluation confirmed actual software behavior; it is not a student verification record. Team members should review and understand changes they explain or submit.
