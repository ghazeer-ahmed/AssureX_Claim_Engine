# Model artifact guide

The active model artifacts are stored in the repository's `models/` directory. This folder is the SRS-required guide to those artifacts; it is not a second copy of the model files.

- `models/python_claim_classifier.joblib`: active structured-claim classifier pipeline.
- `models/python_preprocessing.joblib`: preprocessing artifact saved alongside the active model.
- `models/model_metrics.json`: ordered input schema, classes, evaluation information, and artifact identity.
- `models/model.json`, `models/metadata.json`, `models/weights.bin`: Teachable Machine TensorFlow.js image model export.
- `reports/python_model_evaluation_2026-09-28/`: test predictions and comparison evidence.

The Python model achieved 91.11% accuracy on the 225-row held-out test split. The Teachable Machine model achieved 37.33% on the corresponding claim cards and does not meet the SRS 85% target. See `documentation/MODEL_EVALUATION.md` for the method, metrics, limitations, and retraining requirements.

To train a Python candidate, use `src/train.py` as described in the root README. Do not replace active artifacts until a new model is selected with validation data and evaluated on an untouched test split. The Teachable Machine export currently lacks its original training project/settings; its existing score must not be presented as meeting the SRS requirement.
