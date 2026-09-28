# AssureX Claim Engine: A Practical Approach to Warranty Claim Review

*How structured claim data, warranty rules, document checks, machine learning, and human review fit into one workflow.*

A warranty claim is more than a fault description. To assess it, a reviewer may need to connect the purchase date, product serial number, warranty terms, fault date, repair history, receipt, and photographs. When those details arrive through different forms and files, even a straightforward claim can take time to verify.

AssureX Claim Engine is a web application built to organize that process. It lets customers register products and warranties, prepare claims, attach evidence, and follow claim status. It also brings together configurable warranty checks, document extraction, a Python classifier, and a Teachable Machine image classifier. The goal is to help reviewers find the important facts and identify uncertainty. The final claim outcome remains a human responsibility.

## Why warranty review needs a structured process

A reviewer is not simply deciding whether a product is broken. They need to know whether the product was covered when the fault happened, whether the fault is included in the policy, and whether the evidence belongs to the product being claimed. They may also need to check for previous repairs, missing documents, possible duplicates, or conflicts between a receipt and the registered product details.

If these checks are performed from memory or across separate spreadsheets and folders, important information can be missed. Two reviewers may interpret the same policy differently. A claim may wait while someone asks for a receipt that was already uploaded under the product record. A mismatch between a serial number and a warranty card may not become visible until late in the process.

The AssureX requirements specification describes a web-based application that brings claim intake, document handling, warranty rules, model support, and review tracking into one place. This is a decision-support problem. A good system should make the evidence easier to inspect and explain why a claim needs attention. It should not make an uncertain case look certain just because a model returned a high score.

## What AssureX does

AssureX is built with Python and Flask. The browser pages use HTML templates, CSS, JavaScript, and Bootstrap styling. SQLite stores application records, while uploaded evidence is stored in a private upload directory. The application includes customer, service-centre employee, reviewer, and administrator roles with role-based access checks.

A customer can register a product, add warranty information, attach documents, and create a claim linked to the product and warranty. The claim form collects information such as the fault date, fault category, damage type, requested amount, description, and relevant repairs or replacements. The reviewer can inspect rule findings and evidence, request more information, record an outcome, and leave a reason in the claim history.

The application also provides dashboards, search and filters, notifications, CSV exports, and a downloadable HTML claim report. These features do not replace a careful review, but they help people find the current state of a claim and the information already recorded about it.

![AssureX system architecture showing the browser, Flask services, data stores, models, and reviewer workflow](figures/system_architecture.png)

*Figure 1. AssureX application architecture. The model outputs support a recommendation; an authorized reviewer records the claim decision.*

## From claim intake to review

The workflow begins with a product and a warranty record. A user creates a claim, enters the event details, and uploads supporting files. The application validates form fields, dates, numbers, and file types. Document extraction can propose information from an image or text-based PDF, and the user can review and correct those values before relying on them.

The system then checks the claim against configured warranty rules and evidence requirements. It can flag missing mandatory documents, an expired warranty, an excluded damage type, a serial-number mismatch, a possible duplicate, or a contradiction between the uploaded evidence and the product record. Repair history is available as another piece of context.

If model results are available, the application records the Python prediction and the Teachable Machine prediction with their model versions and class scores. It compares their predicted classes and top-class confidence values. Low confidence, disagreement, incomplete evidence, or rule findings can keep the claim in manual review. A reviewer can request more information, approve, reject, or close the claim according to the workflow and their permissions.

![Claim intake, validation, parallel model predictions, comparison, and human review](figures/claim_workflow.png)

*Figure 2. Claim processing flow. The models are evaluated in parallel, and the reviewer remains responsible for the recorded outcome.*

## Building a shared dataset

The project includes 1,500 structured claim records. The classes are balanced: 500 Valid Claim records, 500 Invalid Claim records, and 500 Manual Review records. The records are separated into three splits: 1,050 training claims, 225 validation claims, and 225 test claims. Each split contains 75 claims from each class in the validation and test sets, and 350 from each class in the training set.

The dataset fields cover product and purchase details, warranty length and status, fault category, damage type, claim amount, repairs, evidence availability, serial matching, duplicate indicators, contradictions, product age, and time remaining on the warranty. This gives the model a structured view of the information a reviewer may need to consider.

The same claim identities are represented in the Claim Summary Card manifest. Training has two visual versions for each training claim, or 2,100 training images. The validation and test cards are kept separate, with 225 cards in each split. Keeping all versions of a claim in one split matters. Otherwise, a model could see a variation of a test claim while training and appear more accurate than it is on unseen cases.

The records are balanced, but balance does not prove that the examples represent real customer claims. The repository contains the CSV files and split map, while the original process used to create and label the full dataset is not fully documented in the current checkout. Before publication or operational use, the team should record whether the examples are synthetic, how scenarios and labels were chosen, and how representative they are of real warranty policies.

![Dataset split with balanced claim classes and separate card holdouts](figures/dataset_split.png)

*Figure 3. The 70/15/15 split keeps training, validation, and test claims separate. Training cards have two image variations per claim.*

## Preparing features for the Python model

The Python classifier receives a fixed set of 35 features. Examples include product category, brand, retailer, purchase price, warranty duration, fault type, damage type, claim amount, previous repairs, whether required documents were uploaded, serial-number matching, duplicate and contradiction flags, product age, remaining warranty days, and the ratio between claim amount and purchase price.

The training script handles numeric and categorical features separately. It fills missing numeric values using the median and scales numeric values. It fills missing categories using the most common value and encodes categories with one-hot encoding. These operations are kept inside a scikit-learn pipeline so the training and inference paths can use the same transformations.

This preparation is important because models expect consistent inputs. A date needs to become a meaningful number of days. A category such as “Smartphone” must be represented consistently. An unknown category at prediction time should not cause the whole model pipeline to fail. The application also maps current product, claim, verified document, repair, and policy information into the model's feature order.

## Comparing Python algorithms

The training utility compares logistic regression, random forest, and extra trees. It scores each candidate on the validation split and selects the model with the best macro-averaged F1 score. Macro F1 calculates the score for each class and gives the classes equal weight. That is useful here because the system needs to recognize Valid Claim, Invalid Claim, and Manual Review rather than favoring one outcome.

I reran the repository's training utility on the checked-in train, validation, and test splits and saved a separate evaluation run under `reports/python_model_evaluation_2026-09-28`. Logistic regression was selected. Its validation accuracy was 89.78% and its validation macro F1 was 89.85%. Random forest reached 87.11% validation accuracy and 87.11% macro F1. Extra trees reached 87.11% validation accuracy and 87.17% macro F1.

The test split was not used to choose the algorithm. After selection, the logistic regression model reached 91.11% accuracy on the 225 test claims. Its macro precision was 91.07%, macro recall was 91.11%, and macro F1 was 91.06%. Those figures are above the SRS target of 85% for the Python model on unseen test claims, but they describe this prepared test set. They do not guarantee the same performance on new manufacturers, policies, or real customer claims.

![Validation accuracy and macro F1 for the three Python model candidates](figures/python_validation_comparison.png)

*Figure 4. Model candidates compared on validation data. The held-out test accuracy is shown separately after model selection.*

## Reading the confusion matrix

Accuracy summarizes correct predictions, but it does not show which mistakes the model makes. The confusion matrix gives that detail. Rows represent the actual class and columns represent the predicted class. Each test row contains 75 examples.

The rerun model correctly classified 70 of 75 Invalid Claim examples, 63 of 75 Manual Review examples, and 72 of 75 Valid Claim examples. Five invalid claims were predicted as manual review. Eight manual-review claims were predicted as invalid, and four were predicted as valid. Three valid claims were predicted as manual review. There were no invalid claims predicted as valid in this test run.

The Manual Review class deserves particular attention. Its recall was 84%, which means 63 of the 75 actual manual-review cases were recognized as manual review. The remaining cases were pushed into one of the other classes. That is one reason to combine predictions with explicit rules and human review rather than treating the highest model score as an automatic verdict.

![Confusion matrix for the Python model on the 225-claim test split](figures/python_test_confusion_matrix.png)

*Figure 5. Test confusion matrix. The diagonal cells are correct predictions; off-diagonal cells show the errors.*

![Python model precision, recall, and F1 score by class](figures/python_test_class_metrics.png)

*Figure 6. Per-class test scores. Each class has 75 test examples.*

![Python and Teachable Machine accuracy compared with the SRS target](figures/model_accuracy_comparison.png)

![Consistency categories from the 225-claim comparison](figures/model_consistency_counts.png)

## The Teachable Machine image model

The second classifier evaluates a visual Claim Summary Card. The card is generated from the claim details and includes information such as product age, warranty status, fault type, repair history, and document availability. The SRS says the card must not include the Python prediction, its confidence score, or the final claim result. That separation lets the image classifier make its own prediction from the claim information.

The repository contains the exported TensorFlow.js model definition, metadata, and weights. The metadata lists the three labels: valid claim, invalid claim, and manual review. The application code loads the image model in the browser and records its returned scores. The browser-based path needs access to TensorFlow.js and the Teachable Machine image library.

I ran the exported image classifier against one card for each of the 225 reserved test claims. I first bundled the same versions of TensorFlow.js and the Teachable Machine image runtime locally, so the browser did not need to reach a public CDN. The model loaded its JSON graph, metadata, and weights and returned three class probabilities for every card.

The result was not good enough. The image model reached **37.33% accuracy**, below the SRS target of 85%. Invalid Claim recall was 14.67%, Manual Review recall was 54.67%, and Valid Claim recall was 42.67%. It predicted Manual Review for many claims, including a large share of claims from the other classes.

![Teachable Machine test confusion matrix](figures/teachable_machine_confusion_matrix.png)

The issue is model quality rather than JavaScript integration. The repository contains the export and card images, but not the original Teachable Machine project or the settings used to train it. The model should be retrained using the 2,100 training cards, checked against the 225 validation cards, and only then evaluated once on the reserved test set. Until retraining is done, the image model does not meet the SRS requirement.

## Comparing predictions and confidence

For an evaluated claim, the application compares the top-class confidence from the Python model with the top-class confidence from the image model. The absolute difference is:

**Confidence difference = |Python top-class confidence - image-model top-class confidence|**

A small difference can mean that the two models assign similar confidence to their own top class. It does not prove that either model is correct. The predicted classes also need to match. If the predictions disagree, if confidence is below the configured threshold, or if required model output is missing, the case should stay in manual review.

The application defines consistency labels such as Strong Match, Acceptable Match, Weak Match, Model Disagreement, and Uncertain Result. These thresholds are configuration values, which makes them easier to inspect and adjust than values hidden throughout the code. The consistency label is one input to the workflow, not a payment decision.

The project now has a comparison report for all 225 unseen test claims. The Python model and image model predicted the same class on 85 claims, an agreement rate of 37.78%. They disagreed on 140. For every claim the report lists both classes, each model’s three confidence scores, the confidence difference, evidence and rule flags, consistency status, recommendation, and review reasons. The comparison confirms that most cases need human review until the image model is improved.

## Warranty rules and data checks

A model learns patterns in examples. A warranty policy states conditions that the application can check directly. AssureX stores sample warranty terms in JSON by product category. The sample policies include coverage duration, reporting periods, covered faults, exclusions, required documents, repair requirements, and conditions that lead to manual review.

For example, the sample laptop and smartphone policies cover listed manufacturing, electrical, and mechanical faults while excluding accidental damage, liquid damage, and misuse. The appliance example uses a different warranty duration and reporting window. These are example policies, not universal legal terms. A real organization would need to replace them with its own approved policy wording and confirm that every configured category is correct.

The workflow checks dates and conditions, required evidence, serial information, repairs, possible duplicate claims, and conflicts between verified document values and the registered product. These checks provide more direct reasons for escalation than a model score alone. Their accuracy still depends on the quality of the policy configuration and the information a customer supplies.

## OCR and document processing

A receipt or invoice can contain purchase dates, product names, retailer details, amounts, model numbers, and serial numbers. AssureX can extract text from text-based PDFs and use Tesseract OCR for supported image files when Tesseract is installed. The extracted values are presented for review so a user can correct them before they become verified claim information.

OCR is not a guarantee of correct data. A photograph may be blurred, tilted, faded, or cropped. Handwriting and unusual receipt layouts can also reduce extraction quality. Scanned PDF pages are not automatically converted to images for OCR in the current workflow. When extraction misses a field, users need to enter it manually and compare it with the original document.

The application checks uploaded file types and size limits and keeps evidence associated with the relevant product or claim. It also records file hashes to identify an identical file used again. A file hash can show that two files are byte-for-byte identical, but it cannot establish whether two different receipts describe the same purchase.

## Review, privacy, and security

The application stores user, product, warranty, claim, document, repair, prediction, evaluation, notification, and audit data. User roles and access rules limit which records a person can access. Security features in the code include password hashing, CSRF protection, login throttling, upload validation, private document handling, session-secret configuration, and audit records for important actions.

These safeguards are part of a local development project, not proof of production readiness. The app currently uses SQLite and the Flask development server in local setup instructions. The SRS asks for at least 10,000 claims, business-hours availability of 99%, and model inference within five seconds. The repository does not include load-test or uptime evidence for those targets. A production deployment would need an appropriate application server, database and backup plan, monitoring, secure configuration, and privacy controls.

The claim report and CSV export can contain personal or purchase information. Anyone using the application should use sample data for public demonstrations, keep private evidence out of the public repository, and protect exported files.

## What went wrong and what the numbers do not tell us

One practical difficulty was that the saved model artifacts and their metrics were not all in sync. The checked-in `models/model_metrics.json` contains a previous test score, while a fresh run of `src/train.py` saved a new model and evaluation under the dated reports folder. Loading the older active classifier with the installed scikit-learn version also produced a warning that it was serialized with a different version. For this reason, the report above uses the fresh training run and its own test results, and the application model file was not silently replaced during documentation work.

The image model initially depended on an external browser runtime that this environment blocked. Bundling the pinned TensorFlow.js and Teachable Machine libraries solved the loading problem and allowed a complete holdout run. That exposed a more important issue: the model scored 37.33%, far below the 85% SRS target, and it disagreed with Python on 140 of 225 claims. A working inference path does not make an inaccurate model ready for claim decisions.

There are also dataset questions. The files contain balanced classes and matching claim IDs, but the repository does not fully document how every scenario and label was generated. A future project iteration should preserve the dataset creation procedure, label rules, version hashes, and evaluation environment alongside the saved models.

## Lessons and next steps

The main lesson is that warranty review is not just a classification task. Product records, evidence, policy rules, and a traceable review process all matter. A model can help prioritize a case, but the system still needs a safe path for missing information, contradictory records, and low-confidence results.

The most useful next steps are clear. First, run the Teachable Machine model on the holdout cards in a browser that can load the pinned TensorFlow.js and Teachable Machine libraries. Second, generate the required comparison report for at least 30 unseen claims and save both models' three-class scores, agreement status, confidence difference, rule findings, and final review outcome. Third, update the model metadata so that it identifies the exact active model artifact and evaluation run. Finally, record the dataset's source and scenario-generation method, and measure performance, mobile usability, and uptime against the non-functional requirements.

AssureX Claim Engine brings the parts of a warranty workflow into one application and gives reviewers a structured view of each claim. The current Python results provide a useful baseline on the prepared test set. Completing the image-model evaluation and the operational checks is the next step toward a fully evidenced SRS submission.

## Project sources

- [AssureX Claim Engine repository](https://github.com/ghazeer-ahmed/AssureX_Claim_Engine)
- Project requirements: *AssureX Claim Engine Software Requirements Specification, Version 1.0, Aptech Limited.*
- Training outputs: `reports/python_model_evaluation_2026-09-28/metrics.json` and `reports/python_model_evaluation_2026-09-28/test_results.csv`.
