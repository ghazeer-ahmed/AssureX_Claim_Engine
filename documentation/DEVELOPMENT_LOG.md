# Development log — 2026-09-26

## Scope

Frontend/backend continuation based on the supplied SRS. The dataset is not in this folder, so training was not run.

## Work

- Added claim drafts, intake validation, linked warranty selection and human-review submission.
- Added private evidence uploads, download/removal, content hashes, PDF/image checks and MP4 signature validation.
- Added optional text extraction and verified fields, comparison with registered product data, and immutable submission snapshots.
- Added repair history, category policy editing, rule explanations and duplicate checks.
- Added review requests, comments, decisions, reopen/close transitions, customer notifications, dashboards, filters, CSV exports and downloadable HTML reports.
- Restricted staff role assignment; added employee/customer assignments, CSRF checks, login throttling, stable session secret and finite-number/date validation.
- Fixed the broken JavaScript URL and replaced placeholder role landing pages with a live dashboard.
- Installed and configured local Tesseract 5.4.0 with English language data for image OCR.
- Added direct and upload-route OCR checks using locally created receipt images.

## Problems and limitations encountered

- Original project had tables but no claim/document workflows.
- Original public signup could create reviewers; original custom script URL returned 404.
- Windows default text encoding required correction to UTF-8 after an edit.
- Network sandbox initially blocked dependency installation; project virtual-environment installation then completed with escalation.
- OCR accuracy may vary with real receipts, blur, rotation, handwriting and unusual layouts. Scanned PDFs still require image conversion before OCR.
- Model helper files are ready, but training and image classification are waiting for the real project files. Claims without both results stay in manual review.

## Verification

Initial 13 integration tests passed using isolated temporary stores. Test suite and manual/browser verification are expanded during implementation; see `tests/` and `TEST_RESULTS.md` for the final run.

Student understanding, independent review/testing, team attribution and competition-day commit evidence have not been fabricated. Record those separately when actually performed.
