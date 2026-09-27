# AssureX Claim Engine

Flask, Jinja, Bootstrap and SQLite warranty claim application. The project uses raw `sqlite3` consistently.

The application includes a structured Python claim classifier and a Teachable Machine image classifier. On claim submission, the server maps the claim into the saved Python feature schema and the browser runs the image classifier against a generated claim summary card. Both probability sets are stored with model versions and compared with the configured decision limits. A missing model or browser runtime still routes the claim to human review.

See [MODULE_REVIEW.md](documentation/MODULE_REVIEW.md) for the status of all SRS modules.

## Setup

Use PowerShell with Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app create-admin
.\.venv\Scripts\python.exe app.py
```

Open `http://127.0.0.1:5000`. The administrator command asks for a name, email and password. It does not create shared credentials. Database initialization adds fields and tables without deleting records.

## Application use

1. Register a customer account and update the profile.
2. Add a product and a standard or extended warranty.
3. Save a receipt, warranty card or other document from the product's Documents page. Verify extracted fields before use.
4. Create a claim, enter fault category, damage type, amount and description, then attach saved or new evidence.
5. Add repair history and read the policy, missing-document, duplicate and contradiction checks.
6. Submit the claim. It becomes read-only until a reviewer requests more information.
7. Reviewers request information, approve or reject with a recorded reason. They cannot approve their own claims.
8. Use Notifications, Dashboards and CSV exports to follow claim activity. The report downloads as HTML and can be printed to PDF from a browser.

Public registration creates customers only. Administrators assign staff roles and customer access. Service-centre employees see only their assigned customers.

## Configuration

- `config/settings.json` stores the application name, database location, upload location and warranty reminder period.
- `config/decision.json` stores the confidence and comparison limits used by the evaluation code.
- `policies/warranties.json` contains the existing sample terms. Unknown categories are routed to manual review without assumed terms.

Environment variables:

| Name | Meaning |
| --- | --- |
| `ASSUREX_SECRET_KEY` | Stable session secret. |
| `ASSUREX_DATABASE` | Alternative SQLite database path. |
| `ASSUREX_UPLOADS` | Private upload directory. |
| `ASSUREX_PORT` | Local port, default 5000. |
| `ASSUREX_DEBUG` | Set to 1 only for local debugging. |
| `ASSUREX_HTTPS` | Set to 1 when serving through HTTPS. |
| `TESSERACT_CMD` | Full path to a local Tesseract installation. |

OCR uses `pytesseract` for images and `pypdf` for text-based PDFs. Tesseract 5.4.0 with English data is installed at the configured path and a receipt-image extraction test passes. Scanned PDF OCR and broad real-world receipt accuracy still need evaluation. Notifications are in-app only. To refresh warranty and deadline alerts through a scheduler:

```powershell
.\.venv\Scripts\python.exe -m flask --app app refresh-alerts
```

## Training preparation

`src/train.py` expects existing train, validation and test CSV files. It requires the actual identifier and label column names and rejects shared records across splits. It compares logistic regression, random forest and extra trees, then saves the selected classifier, preprocessing object, class order, source hashes, metrics and test predictions to a new empty version folder.

```powershell
.\.venv\Scripts\python.exe src\train.py --help
```

The supplied feature schema is recorded in `models/model_metrics.json`. The application maps live records to that ordered schema and uses the supplied claim-card renderer for image inference.

The active Python export is `models/python_claim_classifier.joblib`; the Teachable Machine TensorFlow.js export is `models/model.json`, `models/metadata.json` and `models/weights.bin`. Model files are served from authenticated routes. TensorFlow.js and the Teachable Machine image library are loaded from jsDelivr in the browser.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite uses isolated temporary databases and uploads. It covers access boundaries, claim validation, document handling, OCR review, policy snapshots, duplicate detection, reviewer workflow, evaluations, confidence boundaries and immutable history. See [TEST_RESULTS.md](documentation/TEST_RESULTS.md).

## Model inputs

The claim feature mapper uses the database records, verified evidence fields, repair history and active category policy. The image model receives a generated claim summary card using the same renderer and field layout as the training cards. Both predictions are recorded as immutable rows and compared during submission; missing predictions leave the decision at manual review.
