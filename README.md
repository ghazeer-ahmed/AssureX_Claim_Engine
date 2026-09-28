# AssureX Claim Engine

AssureX is a local web application for recording product warranties, submitting warranty claims, collecting evidence, and reviewing claim decisions. It is built with Python, Flask, server-rendered HTML templates, Bootstrap styling, and SQLite. The project also includes a saved Python claim classifier and a Teachable Machine image classifier.

This guide is written for someone opening this project for the first time. It explains what the application does, how to install and start it on Windows, how to create the first administrator, how each user role can use the site, where its files and data live, and how to run the automated checks.

## What the application does

A customer can register products and warranties, create a claim for a product, add a description and repair history, attach evidence, and submit the claim. The application checks configured warranty terms, required information, duplicate or conflicting details, and model predictions. A reviewer or administrator then handles the claim and records a decision or asks the customer for more information.

The models assist the workflow; they do not replace the human review. The Python model runs on the server. The image model runs in the browser using a generated claim summary image. The application records available predictions and model versions. When predictions are missing or uncertainty is high, the claim remains for human review.

## Requirements

- Windows 10 or 11, or another operating system capable of running Python and Flask. The commands below are for Windows Command Prompt (CMD).
- Python 3.11 or newer. During installation on Windows, enable the option to add Python to PATH, or use the Python Launcher command `py`.
- Internet access during installation to download Python packages. The TensorFlow.js and Teachable Machine browser libraries are included under `static/vendor/`, so model inference does not need a third-party CDN at runtime.
- Tesseract OCR installed locally for OCR on receipt images and scanned PDF pages. Install the Windows Tesseract program separately from the Python packages, then open a new CMD window and run `tesseract --version` to confirm it is on PATH. Text-based PDFs are read with `pypdf`; scanned PDFs are rendered with PyMuPDF and OCR is applied to the first five pages. If Tesseract is installed outside a common Windows location, set `TESSERACT_CMD` as described under Configuration. Without Tesseract, evidence can still be uploaded and details entered or verified manually.

## Install and run the website from Windows CMD

Open **Command Prompt**. Do not type these commands into a browser address bar. The examples assume the repository is in your Documents\GitHub folder. If you saved it somewhere else, replace the first path with the folder that contains `app.py`.

### First-time setup

Run each command separately, waiting for it to finish before entering the next one:

```bat
cd /d "%USERPROFILE%\Documents\GitHub\AssureX_Claim_Engine"
py -3 --version
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m flask --app app init-db
.venv\Scripts\python.exe -m flask --app app create-admin
.venv\Scripts\python.exe app.py
```

What these commands do:

1. `cd /d` changes CMD to the project directory, including changing drives if necessary. The project directory is the one containing `app.py` and `requirements.txt`.
2. `py -3 --version` checks that Python is installed and that the launcher can find it.
3. `py -3 -m venv .venv` creates a private Python environment inside the project. This avoids installing the project's packages globally on your computer.
4. The two `pip` commands update pip in that environment and install the dependencies listed in `requirements.txt`.
5. `init-db` creates or updates the SQLite database schema. It is safe to run against an existing database: it initializes the schema without deleting existing records.
6. `create-admin` interactively asks for an administrator's name, email address, and password. The password must be at least 12 characters. The password is not printed as you type. Choose a unique email address.
7. `app.py` starts the local development web server.

When the server starts, open this address in your web browser:

[http://127.0.0.1:5000](http://127.0.0.1:5000)

Keep the Command Prompt window open while you use the site. To stop the server, return to that window and press **Ctrl+C**.

### Start it after the first setup

You do not need to recreate `.venv`, reinstall packages, or create the administrator every time. Open a new CMD window and run:

```bat
cd /d "%USERPROFILE%\Documents\GitHub\AssureX_Claim_Engine"
.venv\Scripts\python.exe app.py
```

Then visit [http://127.0.0.1:5000](http://127.0.0.1:5000). The project-local interpreter path is `.venv\Scripts\python.exe`; `..\.venv\Scripts\python.exe` points to a different folder and will fail if there is no virtual environment in the parent directory.

If your project folder is, for example, `C:\Users\HP\Documents\AssureX_Claim_Engine`, use that exact folder in the `cd /d` command instead. You can check that you are in the right place with:

```bat
dir app.py requirements.txt
```

### Log in

Go to the website's **Login** page and enter the administrator email and password created by `create-admin`. The administrator can then add or manage accounts and assign roles. Public registration creates customer accounts; it does not let a visitor grant themselves an administrator or staff role.

If the administrator already exists, do not run `create-admin` with the same email again. Log in with that account instead. If you have access to an existing administrator account, that administrator can change another user's role under **Admin → Users**.

## First-use walkthrough

The exact navigation labels can vary slightly by page, but the workflow below follows the application's intended sequence.

### 1. Create or prepare user accounts

- Use **Register** to create a customer account, or have an administrator create/manage users from the admin area.
- Sign in at **Login**.
- An administrator opens **Admin → Users** to assign a role to another account. The available roles are administrator, customer, service-centre employee, and reviewer.
- A service-centre employee needs a customer assignment to see that customer's work. Administrators manage those assignments. Staff access is restricted according to the assigned customers.
- An administrator should not change their own role through the ordinary user-role form. Ask another administrator to make that change if necessary.

### 2. Register a product

As a customer, open **Products** and choose **Register Product**. Enter the product information requested by the form, including the product name, category, brand, model if known, serial number, purchase date, purchase price, retailer, and standard warranty length in months.

Use the date picker where available. Dates shown in examples and forms use the year-month-day style, such as `2026-01-10` for January 10, 2026. When a product is registered, the application creates a standard warranty using the purchase date, duration, and retailer/provider information. If an older product does not have an associated warranty, open the product and use **Add Warranty**. An extended warranty can also be recorded when applicable.

Keep the purchase date and warranty dates accurate. They are used when the application checks whether the claim falls within coverage.

### 3. Add product documents

Open the product's **Documents** page to save product-level documents such as a receipt or warranty card. These documents can be reused as evidence when preparing a claim. Saving a file does not mean that extracted information has been accepted: inspect and verify any values proposed by document extraction before relying on them.

### 4. Create a claim

Open **Claims → New Claim** and select the product and one of its warranties. If the warranty selector is empty, first confirm that the product is registered and has an associated warranty. Registering a product normally creates a standard warranty; older records may need **Add Warranty**.

Complete the claim form. It asks for details such as:

- When the fault happened.
- The fault or damage category. Options include manufacturing defect, electrical failure, mechanical failure, accidental damage, liquid damage, misuse, and other.
- The amount being claimed.
- A clear description of the problem and when it began.
- Relevant service history and previous repairs or replacements.

Save the claim as a draft while information is incomplete. A draft can be edited before submission.

### 5. Attach evidence and verify details

On the claim page, attach available supporting files. Supported file types are PDF, JPG/JPEG, PNG, and MP4. The per-file upload limit is 10 MB. Upload evidence that supports the claim, for example:

- Purchase receipt or invoice.
- Warranty card.
- Product and serial-number photographs.
- Photographs or video showing the fault.
- Repair report or service-centre invoice.

Choose the evidence type shown by the page (for example receipt, warranty card, product image, serial evidence, fault evidence, repair report, invoice, or other). The server also limits the complete upload request size; if a request containing multiple files is too large, upload fewer files at a time.

The application can extract some text from evidence to suggest values for review. OCR is not proof that a value is correct. Check proposed information against the original document and verify it before using it. Image OCR and scanned-PDF OCR require Tesseract. Scanned PDFs are rendered locally, and the first five pages are sent to OCR. If extraction does not work, enter the information manually and keep the original evidence attached.

### 6. Check the claim and submit it

Before submitting, review the product, warranty, dates, amount, description, attachments, repairs, and any policy or missing-information checks displayed on the claim. Add repair records where relevant.

Use **Run models and submit for review**. The application requests Python probabilities from the server, creates the claim card without predictions, runs the image classifier in the browser, records its three scores, compares both outputs, applies warranty/evidence rules, and sends the claim to human review. If a model is unavailable or results disagree, the claim still goes to manual review. The application evaluates the available structured claim data and image summary. Submission locks the claim from ordinary editing while it is being reviewed. If a reviewer requests more information, the claim can be updated in that workflow and resubmitted.

### 7. Follow the review

Use the dashboard and **Notifications** to follow activity. A reviewer or administrator can request more information, approve, reject, or close the claim, with an explanation recorded in the claim history. Reviewers cannot approve their own claims. Model scores and policy checks are supporting information; the human reviewer records the decision.

### 8. View reports and export data

Use the available dashboard, search, notifications, and CSV export pages to follow records. A claim report can be downloaded as HTML and printed or saved as PDF using the browser's print dialog. Exports can contain customer information, so store them carefully and share them only with people who should see the data.

## User roles

| Role | Typical access |
| --- | --- |
| Customer | Manage their profile, products, warranties, documents, and claims; provide requested information and follow claim status. |
| Service-centre employee | Work with customers assigned by an administrator, subject to the application's access rules. |
| Reviewer | Review submitted claims, request more information, and record review outcomes. A reviewer cannot approve their own claim. |
| Administrator | Manage users, roles, customer assignments, policy configuration, and administrative functions, as well as review functions available to administrators. |

Public self-registration is intended for customer accounts. A customer cannot grant themselves a staff role by changing form data.

## Models and automated checks

The active Python classifier is `models/python_claim_classifier.joblib`. The ordered input schema and model information are recorded in `models/model_metrics.json`. The image model export consists of `models/model.json`, `models/metadata.json`, and `models/weights.bin`.

The server maps claim and related database information into the saved Python feature schema. The image classifier runs in the browser against a generated claim summary card; it does not require a webcam. TensorFlow.js 1.7.4 and Teachable Machine Image 0.8.5 are bundled under `static/vendor/`, so the browser does not need CDN access at runtime. The trained model files are delivered through application routes.

Predictions and their model versions are recorded for the claim. Decision limits are configured in `config/decision.json`. Category-specific warranty terms are in separate files under `policies/`: `laptop.json`, `smartphone.json`, and `appliance.json`. Unknown categories are sent for manual review rather than being treated as covered automatically. A prediction is not a final approval or rejection, and a missing prediction still leaves the claim in human review.

The saved models are used for inference; ordinary website use does not retrain them. Current held-out test results are recorded in `documentation/MODEL_EVALUATION.md`: Python accuracy is 91.11% and Teachable Machine accuracy is 37.33% on the same 225 unseen claims. The image model runs but does not meet the SRS 85% accuracy target. The comparison report is `reports/python_model_evaluation_2026-09-28/model_comparison_2026-09-28.csv`. New claim records do not automatically become training rows or modify the model files.

### Model input fields

The website prepares the Python model input from saved product, warranty, claim, repair, policy, and verified document information. Users do not upload a CSV or enter model feature names. The ordered schema is stored in `models/model_metrics.json`, and `ml_service.py` checks that every request matches that exact order before inference. The current schema contains 35 fields:

`product_category`, `brand`, `retailer`, `purchase_price`, `warranty_months`, `extended_warranty`, `extended_months`, `fault_category`, `fault_covered`, `damage_type`, `claim_amount`, `previous_repairs`, `last_repair_centre`, `unauthorised_repair`, `product_replaced_before`, `receipt_uploaded`, `warranty_card_uploaded`, `product_image_uploaded`, `serial_evidence_uploaded`, `fault_evidence_uploaded`, `repair_report_uploaded`, `missing_documents`, `serial_match`, `duplicate_claim_flag`, `contradiction_claim_before_purchase`, `contradiction_repair_before_purchase`, `contradiction_fault_after_claim`, `contradiction_model_mismatch`, `contradiction_count`, `product_age_days`, `remaining_warranty_days`, `warranty_status`, `reporting_delay_days`, `reported_within_window`, and `claim_to_price_ratio`.

The claim-summary image is a separate model input. The card renderer uses claim facts and evidence indicators, and it must not include the Python prediction, any Python confidence score, or the final decision.

## Data storage and privacy

By default, the application stores:

- SQLite records in `database/assurex.db`.
- Uploaded evidence in the `uploads/` directory.
- The application secret in `instance/secret.key` when one is generated locally.

These locations are local to the project unless changed in configuration. The database and uploads persist when the web server stops. They are excluded from Git so local customer records, evidence, and secrets are not committed. Back up the database and uploads together if you need to preserve records; a database backup without its evidence files may leave records without the related documents. Do not put real customer data or private documents into a public repository.

This setup starts Flask's local development server and is intended for development and demonstration. Do not expose it directly to the public internet as a production service without deploying behind a properly configured production web server and applying appropriate security, privacy, backup, and operational controls.

## Configuration

The main configuration files are:

- `config/settings.json`: application name, database path, upload directory, warranty alert period, and OCR executable setting.
- `config/decision.json`: confidence and comparison thresholds used by the evaluation workflow.
- `policies/`: category-specific warranty rules, one JSON file per supported product category.

Tesseract is a separate Windows program. The app checks `TESSERACT_CMD`, `config/settings.json`, PATH, and common Program Files install folders. If Tesseract is installed elsewhere, set `TESSERACT_CMD` to the full path of `tesseract.exe`.

The application also recognizes these environment variables:

| Variable | Purpose |
| --- | --- |
| `ASSUREX_SECRET_KEY` | Set a stable secret for sessions. Use a private, random value; do not publish it. |
| `ASSUREX_DATABASE` | Override the default SQLite database file path. |
| `ASSUREX_UPLOADS` | Override the evidence upload directory. |
| `ASSUREX_PORT` | Choose the local server port; the default is `5000`. |
| `ASSUREX_DEBUG` | Set to `1` to enable Flask debug mode for local development only. |
| `ASSUREX_HTTPS` | Set to `1` when the application is correctly served through HTTPS so secure-cookie behavior can be enabled. |
| `TESSERACT_CMD` | Full path to `tesseract.exe` when automatic discovery does not find the installation. |

If you change a path, make sure the account running the application can access that directory. Keep secrets out of source control and screenshots.

To refresh warranty and deadline alerts manually, run this in CMD from the repository root while the server is stopped or from a second terminal:

```bat
.venv\Scripts\python.exe -m flask --app app refresh-alerts
```

## Run the automated test suite

From the repository root in CMD, run:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use temporary databases and upload locations so the test run does not need to use your normal application records. They cover account access boundaries, claim validation and workflow, text and scanned-PDF extraction, image OCR review, warranty policy files and snapshots, duplicate detection, reviewer actions, active Python inference, local image-model assets and prediction storage, evaluation limits, and history behavior. The test result notes are in [`documentation/TEST_RESULTS.md`](documentation/TEST_RESULTS.md), and the module review is in [`documentation/MODULE_REVIEW.md`](documentation/MODULE_REVIEW.md).

A passing automated test suite checks the behaviors represented by those tests; it does not replace manually trying the site in a browser with realistic accounts and evidence files.

## Model training and datasets (optional)

You do not need to train models to start the website. The saved exports in `models/` are used for inference. Training is an optional development task for someone preparing a new, properly split dataset.

The training utility is `src/train.py`. It expects train, validation, and test CSV files, the identifier and label column names, and separate records in each split. It compares logistic regression, random forest, and extra trees, then saves the selected classifier, preprocessing data, class order, source hashes, metrics, and test predictions into a new empty version directory. See its command options with:

```bat
.venv\Scripts\python.exe src\train.py --help
```

Do not use the same person, claim, or other related records across training and test splits if that would leak information. Check labels, remove private data, and document how the dataset was collected before training. Training outputs should be reviewed before replacing the active model used by the site.

The dataset and generated card assets are organized under `data/` and `cards/`. The claim-card renderer used for inference is in `dataset_generator/render_cards.py`; using the same layout for training and live inference helps keep image-model inputs consistent.

## Project map

| Path | What it contains |
| --- | --- |
| `app.py` | Flask application entry point, routes, CLI commands, and app setup. |
| `workflow.py`, `app_features.py`, `claim_services.py`, `decision_service.py` | Claim workflow, feature mapping, domain operations, and decision support. |
| `templates/` | HTML pages rendered by Flask. |
| `static/` | CSS, JavaScript, and other browser assets. |
| `database/` | Default location for the SQLite database created at runtime. |
| `uploads/` | Default location for evidence uploaded at runtime. |
| `config/` | Application and decision settings. |
| `policies/` | One JSON policy file per product category. The shipped categories are Laptop, Smartphone, and Appliance. |
| `models/` | Active Python classifier, preprocessing pipeline, ordered schema and metrics, and Teachable Machine export files. |
| `model/` | Guide to the active model artifacts and their relationship to the `models/` directory. |
| `static/vendor/` | Local Bootstrap, TensorFlow.js, and Teachable Machine runtime files plus license notices. |
| `data/`, `cards/` | Dataset material and generated claim-card assets. |
| `src/train.py` | Optional model training command-line program. |
| `tests/` | Automated Python tests. |
| `documentation/` | Module review, test notes, and supporting documentation. |

## Troubleshooting

### CMD says the path cannot be found

Change to the folder that actually contains `app.py`. For the common Documents\GitHub location, copy this exact command:

```bat
cd /d "%USERPROFILE%\Documents\GitHub\AssureX_Claim_Engine"
```

Then confirm the files exist with `dir app.py requirements.txt`. Do not append the Python command to the `cd` command on the same line unless you deliberately use CMD's `&` separator.

### `.venv\Scripts\python.exe` cannot be found

The virtual environment has not been created in this repository, or the current directory is wrong. First `cd` to the folder containing `app.py`, then run `py -3 -m venv .venv`. If `py` is not recognized, install Python 3.11+ and enable the Python Launcher, or use the full path to your Python executable.

### `No module named ...` appears

Install the dependencies using the repository's interpreter:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Port 5000 is already in use

Stop the other application using that port, or start AssureX on another port by setting `ASSUREX_PORT` before running `app.py`. In CMD, for example:

```bat
set ASSUREX_PORT=5001
.venv\Scripts\python.exe app.py
```

Then open `http://127.0.0.1:5001`. Close that CMD window or run `set ASSUREX_PORT=` to clear the temporary setting for that window.

### The browser cannot load the image model

Confirm that `models/model.json`, `models/metadata.json`, and `models/weights.bin` exist and that the local scripts under `static/vendor/` are served successfully. The model runtime is bundled with the project, so an external CDN connection is not needed. If a model prediction still fails, the claim is routed to human review and the browser status message explains the failure.

### Text extraction did not find information

Confirm Tesseract is installed. The app checks `TESSERACT_CMD`, the application setting, PATH, and common Windows installation folders. Text-based PDFs are parsed directly; scanned PDFs are rendered locally and the first five pages are sent to Tesseract. Check and correct extracted fields manually.

### The warranty list is empty on a new claim

Open the product and confirm it has a warranty record. Newly registered products receive a standard warranty based on the purchase details; older products may need **Add Warranty**. Also check that the selected product belongs to the signed-in user or is assigned to the staff account.

## Further documentation

- [Module review](documentation/MODULE_REVIEW.md)
- [Test results](documentation/TEST_RESULTS.md)
