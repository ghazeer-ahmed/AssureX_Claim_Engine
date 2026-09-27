# SRS module review

| Module | Current status |
| --- | --- |
| 1. Project setup | Flask app, settings, templates, static files and requested folders are present. |
| 2. Database schema | SQLite tables cover users, products, warranties, claims, documents, repairs, predictions, rules, notifications, audit, versions and evaluations. |
| 3. Authentication and roles | Registration, login, logout, CSRF protection and customer, employee, reviewer and admin access are implemented. |
| 4. Profiles | Profile update pages are present. |
| 5. Products | Registration and product search are implemented. |
| 6. Warranties | Standard and extended records, status and expiry alerts are implemented. |
| 7. Documents | Product and claim document storage, download, replacement and removal are implemented. |
| 8. OCR verification | Text extraction and user verification are implemented. Local Tesseract 5.4.0 with English data is configured and a receipt-image extraction test passes. |
| 9. Claim registration | Draft claims collect product, warranty, fault, amount and evidence. |
| 10. Repair history | Repair dates, centres, parts, outcomes, cost and authorization are stored. |
| 11. Validation | Field, date, number, upload, ownership and duplicate validation are implemented. |
| 12. Preprocessing | Live claim/product/evidence/repair records map into the saved Python feature schema. |
| 13. Python training | `src/train.py` and the train/validation/test splits are supplied; the selected export is in `models/python_v1/`. |
| 14. Python prediction | The saved classifier runs at submission and its probabilities and model version are recorded immutably. |
| 15. Claim Summary Card | The supplied training renderer generates a current claim card for image inference. |
| 16. Image classifier | Teachable Machine TensorFlow.js assets are loaded in the browser to classify the generated card. |
| 17. Comparison | Configurable comparison and confidence difference logic are implemented and tested. |
| 18. Rule engine | JSON policy reading and recorded rule results are implemented. |
| 19. Integrity checks | Serial, contradictions, required documents, claim duplicates and document-hash duplicates are implemented. |
| 20. Claim summary | Deterministic claim summary and preparation checks are shown. |
| 21. Final decision | `Likely Valid`, `Likely Invalid` and `Manual Review Required` logic is saved with reasons; missing classifier output routes to review. |
| 22. Manual review | Queue transitions, comments, override history and self-review blocking are implemented. |
| 23. Tracking and alerts | Statuses, in-app notifications, warranty alerts and reporting deadline alerts are implemented. |
| 24. User dashboard | Products, warranties, claims, actions, receipts and recent outcomes are shown. |
| 25. Administrator dashboard | Claim metrics, flags, confidence summary, trends and security events are shown. |
| 26. Search and filtering | Claim, product, serial, status, category, warranty, date, reviewer, risk and confidence filters are implemented. |
| 27. Analysis and reporting | Outcomes, categories, faults, repairs, manual review, confidence and rejection data are shown and exported. |
| 28. Reports and export | Downloadable HTML claim report and CSV exports are implemented. |
| 29. Audit, versions and alerts | Audit events, model-version records, immutable evaluation records and alerts are implemented. |
| 30. Tests | 32 automated tests pass. Real model accuracy tests need the supplied dataset and image-model files. |
| 31. Documentation | README, development log, test results and this module review are present. |

## Required inputs before saying every SRS requirement is complete

The active workflow runs both available classifiers on claim submission. TensorFlow.js and Teachable Machine are loaded from jsDelivr; image inference requires browser access to that CDN. If either classifier cannot run, the claim remains routed to human review.
