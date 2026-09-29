# Model Evaluation Report

**Evaluation date:** 2026-09-29  
**Dataset:** prepared repository train, validation, and reserved test splits  
**Purpose:** report the active Python classifier and the new GTM SavedModel on the same unseen claims, with limitations and reproducibility details.

## Summary

The Python classifier exceeds the SRS accuracy target on this prepared holdout. The GTM SavedModel loads and returns three-class probabilities, but it correctly classified 78 of 225 reserved test cards (34.67%), below the SRS target of 85%. The image model therefore does not meet the accuracy requirement. These results come from the project’s prepared test set and do not predict performance on real insurer records.

| Measure | Python classifier | GTM SavedModel image classifier | SRS target |
| --- | ---: | ---: | ---: |
| Held-out test claims | 225 | 225 matching cards | Unseen claims |
| Accuracy | 91.11% | 34.67% | At least 85% for each model |
| Macro precision | 91.07% | 37.00% | Report |
| Macro recall | 91.11% | 34.67% | Report |
| Macro F1 | 91.06% | 31.06% | Report |
| Prediction agreement | 34.67% (78/225) | same comparison | Compare both models |

![Held-out accuracy compared with the SRS target](figures/model_accuracy_comparison.png)

*Figure 1. Python clears the target on this prepared split; GTM does not.*

On the same 225 claims, the Python and GTM models agreed on 78 and disagreed on 147. With the checked-in thresholds, the comparison produced 37 Strong Match, 8 Acceptable Match, 4 Weak Match, 29 Uncertain Result, and 147 Model Disagreement outcomes. The application should keep disagreement and low-confidence results in human review.

![Python and GTM comparison outcomes](figures/model_consistency_counts.png)

*Figure 2. Most model pairs disagree, so the combined result still needs review.*

## Dataset and method

The structured dataset contains 1,500 records, with 500 examples per class. It is split by claim ID into 1,050 training records, 225 validation records, and 225 reserved test records. The test set has 75 examples in each class. Each test claim ID is matched to one image using `cards/card_manifest.csv`. The held-out cards were not used for training or model selection.

The GTM export is a TensorFlow.js graph model with a 224 by 224 RGB input and three outputs. The evaluation loaded `models/model.json` with the locally bundled TensorFlow.js runtime, resized each manifest-matched card to 224 by 224, scaled pixel values from [0,255] to [-1,1], and mapped output positions using `models/metadata.json`. This output-label order is `valid_claim`, `invalid_claim`, `manual_review`. The application’s browser inference uses the same graph loader, image size, and normalization. All 225 cards produced a valid three-class probability vector.

The Python pipeline selects a classifier using validation macro F1 and evaluates the selected model on the reserved test set. Its reported score is 91.11%. The test set was not used to choose the Python algorithm.

## Python results

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Invalid Claim | 89.74% | 93.33% | 91.50% | 75 |
| Manual Review | 88.73% | 84.00% | 86.30% | 75 |
| Valid Claim | 94.74% | 96.00% | 95.36% | 75 |

The Python model correctly classified 205 of 225 claims. Manual Review recall was 84%, so reviewer oversight remains necessary.

## GTM SavedModel results

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Invalid Claim | 33.96% | 24.00% | 28.13% | 75 |
| Manual Review | 43.48% | 13.33% | 20.41% | 75 |
| Valid Claim | 33.56% | 66.67% | 44.64% | 75 |

The model correctly classified 78 of 225 cards. Its predictions leaned toward Valid Claim: it assigned that label to 149 cards, including 53 Invalid Claim and 46 Manual Review examples. Invalid Claim and Manual Review recall were 24.00% and 13.33%, respectively. These errors make the output unsuitable as a stand-alone decision.

![GTM SavedModel confusion matrix](figures/gtm_savedmodel_confusion_matrix.png)

*Figure 3. Rows are actual classes and columns are predicted classes.*

![GTM SavedModel recall by class](figures/gtm_savedmodel_class_recall.png)

*Figure 4. Recall is weakest for Manual Review and Invalid Claim.*

The application stores image-model output for comparison and human review. The measured inference path completed for all 225 cards, but this evaluation did not measure latency against the SRS five-second target. A successful load and prediction call do not mean the classifier meets the SRS accuracy requirement.

## Model comparison report

`reports/gtm_model_evaluation_2026-09-29/test_predictions.csv` contains one row for each reserved test claim, both model predictions, all six class probabilities, the top-confidence difference, and the consistency status. `metrics.json` contains aggregate metrics, the confusion matrix, class scores, output label order, comparison thresholds, and the combined GTM artifact hash. The agreement rate is 78/225, or 34.67%. Comparison thresholds are in `config/decision.json`: minimum confidence 0.80 and top-confidence difference limits 0.05, 0.15, and 0.25.

The separate structured Python results and the GTM image predictions are aligned by the same claim IDs. Prepared rule fields do not constitute live application claims.

## Live model inputs and recording

For Python inference, `ml_service.claim_features` maps the current product, warranty, claim, verified documents, repairs, and policy findings into the ordered 35-field schema recorded in `models/model_metrics.json`. The saved classifier produces three class probabilities.

For image inference, the application renders a Claim Summary Card from claim facts without including the Python prediction or final decision. The browser loads the TensorFlow.js graph model, converts the card to the model’s 224 by 224 RGB input, applies the documented [-1,1] scaling, and posts the three labelled scores to the application. The server validates and stores the scores with a content-hash model version.

## Limitations and next steps

The image model’s 34.67% accuracy is well below the SRS target of 85%. Do not present it as meeting the target. Review the GTM training data, labels, output-class order, training settings, and card rendering. Tune only with training and validation data, then evaluate a final model once on the reserved test split. Do not select a model based on repeated inspection of the test scores.

The dataset is balanced and split by claim ID, but its synthetic/scenario-generation provenance needs a fuller audit trail. Test scores do not establish performance on manufacturer records, other policy types, or customer evidence. OCR output still needs human verification. Load and availability targets, including 10,000 claims, 99% business-hours availability, and five-second inference, have not been established by this model evaluation.

## Reproducibility artifacts

- `reports/gtm_model_evaluation_2026-09-29/metrics.json`
- `reports/gtm_model_evaluation_2026-09-29/test_predictions.csv`
- `models/model.json`, `models/metadata.json`, and `models/weights.bin`
- `models/gtm_savedmodel.zip`
- `cards/card_manifest.csv` and the `cards/holdout_test/` images
- `documentation/figures/model_accuracy_comparison.png`
- `documentation/figures/model_consistency_counts.png`
- `documentation/figures/gtm_savedmodel_confusion_matrix.png`
- `documentation/figures/gtm_savedmodel_class_recall.png`
