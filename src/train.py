import argparse
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def train(args):
    root = Path(__file__).resolve().parent.parent
    meta = json.loads(Path(args.schema).read_text(encoding='utf-8'))
    features = meta['features']
    numeric = meta['numeric_features']
    categorical = meta['categorical_features']
    if set(numeric) & set(categorical) or set(features) != set(numeric + categorical):
        raise ValueError('Feature groups must match the feature list without overlap.')
    if args.label in features or args.id in features:
        raise ValueError('The label and record identifier cannot be input features.')
    names = ['train', 'validation', 'test']
    frames = {}
    hashes = {}
    seen = set()
    labels = {'Valid Claim', 'Invalid Claim', 'Manual Review'}
    for name in names:
        path = root / 'data' / ('claims_' + name + '.csv')
        df = pd.read_csv(path)
        missing = set(features + [args.id, args.label]) - set(df.columns)
        if missing:
            raise ValueError('Missing columns in ' + name + ': ' + ', '.join(sorted(missing)))
        if df[args.id].isna().any() or df[args.id].duplicated().any():
            raise ValueError('Record identifiers must be present and unique.')
        ids = set(df[args.id].astype(str))
        if seen & ids:
            raise ValueError('A record appears in more than one split.')
        seen.update(ids)
        if set(df[args.label]) != labels:
            raise ValueError('Each split must contain the three required classes.')
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors='raise')
        frames[name] = df
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(seen) < 1500:
        raise ValueError('The SRS requires at least 1500 distinct records.')
    if frames['train'][args.label].value_counts().min() < 5:
        raise ValueError('Each training class needs at least five records for the configured checks.')

    candidates = [LogisticRegression(max_iter=2000, random_state=42),
                  RandomForestClassifier(n_estimators=150, random_state=42),
                  ExtraTreesClassifier(n_estimators=150, random_state=42)]
    results = []
    best = None
    best_score = -1
    for estimator in candidates:
        prep = ColumnTransformer([
            ('numbers', Pipeline([('fill', SimpleImputer(strategy='median')), ('scale', StandardScaler())]), numeric),
            ('categories', Pipeline([('fill', SimpleImputer(strategy='most_frequent')),
                                     ('encode', OneHotEncoder(handle_unknown='ignore'))]), categorical)
        ])
        model = Pipeline([('prep', prep), ('classifier', estimator)])
        model.fit(frames['train'][features], frames['train'][args.label])
        actual = frames['validation'][args.label]
        predicted = model.predict(frames['validation'][features])
        score = f1_score(actual, predicted, average='macro')
        cv = cross_val_score(model, frames['train'][features], frames['train'][args.label], cv=5, scoring='f1_macro')
        results.append(dict(name=type(estimator).__name__, settings=estimator.get_params(),
                            validation_accuracy=accuracy_score(actual, predicted), validation_f1=score,
                            class_results=classification_report(actual, predicted, output_dict=True, zero_division=0),
                            confusion_matrix=confusion_matrix(actual, predicted, labels=sorted(labels)).tolist(),
                            training_cv_f1=cv.tolist()))
        if score > best_score:
            best, best_score = model, score

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Choose an empty output folder to preserve earlier versions.')
    actual = frames['test'][args.label]
    predicted = best.predict(frames['test'][features])
    joblib.dump(best, out / 'classifier.joblib')
    joblib.dump(best.named_steps['prep'], out / 'preprocessing.joblib')
    version = hashlib.sha256((out / 'classifier.joblib').read_bytes()).hexdigest()
    data = dict(version=version, features=features, numeric_features=numeric, categorical_features=categorical,
                classes=list(best.classes_), source_hashes=hashes, candidates=results,
                selected=type(best.named_steps['classifier']).__name__,
                test_accuracy=accuracy_score(actual, predicted),
                test_results=classification_report(actual, predicted, output_dict=True, zero_division=0),
                test_confusion_matrix=confusion_matrix(actual, predicted, labels=sorted(labels)).tolist())
    (out / 'metrics.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    res = frames['test'][[args.id, args.label]].copy()
    res['prediction'] = predicted
    for name, conf in zip(best.classes_, best.predict_proba(frames['test'][features]).T):
        res[name] = conf
    res.to_csv(out / 'test_results.csv', index=False)
    print('training complete:', out)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        train(args)
    except Exception as e:
        parser.exit(1, str(e) + '\n')
