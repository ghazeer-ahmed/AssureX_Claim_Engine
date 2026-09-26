import json
import math
from pathlib import Path

from flask import current_app


classes = ('Valid Claim', 'Invalid Claim', 'Manual Review')


def load_limits():
    path = current_app.config.get('DECISION_FILE')
    if not path:
        path = Path(current_app.root_path) / 'config' / 'decision.json'
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    values = [data[key] for key in ('strong_difference', 'acceptable_difference', 'maximum_difference')]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValueError('Comparison limits must be numbers.')
    if not 0 <= values[0] <= values[1] <= values[2] <= 1:
        raise ValueError('Comparison differences must be ordered between zero and one.')
    if not 0 <= data['minimum_confidence'] <= 1:
        raise ValueError('Minimum confidence must be between zero and one.')
    return data


def valid_scores(row):
    if not row or row['predicted_class'] not in classes:
        return False
    scores = [row[key] for key in ('valid_conf', 'invalid_conf', 'manual_conf')]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in scores):
        return False
    if not isinstance(row['top_conf'], (int, float)) or not math.isfinite(row['top_conf']):
        return False
    return (abs(sum(scores) - 1) < 0.00001
            and abs(max(scores) - row['top_conf']) < 0.00001
            and scores[classes.index(row['predicted_class'])] == max(scores))


def compare_results(first, second, limits):
    if not valid_scores(first) or not valid_scores(second):
        return dict(status='Uncertain Result', difference=None, matches=None)
    gap = abs(first['top_conf'] - second['top_conf'])
    matches = first['predicted_class'] == second['predicted_class']
    if not matches:
        status = 'Model Disagreement'
    elif min(first['top_conf'], second['top_conf']) < limits['minimum_confidence']:
        status = 'Uncertain Result'
    elif gap <= limits['strong_difference']:
        status = 'Strong Match'
    elif gap <= limits['acceptable_difference']:
        status = 'Acceptable Match'
    else:
        status = 'Weak Match'
    return dict(status=status, difference=gap, matches=matches)


def decide(first, second, findings, limits):
    res = compare_results(first, second, limits)
    reasons = [item['details'] for item in findings if item['result'] != 'Pass']
    if not findings:
        reasons.append('Warranty checks are unavailable.')
    if res['status'] in ('Model Disagreement', 'Uncertain Result'):
        reasons.append('Both classifiers must return valid, confident, matching results.')
    if res['difference'] is not None and res['difference'] > limits['maximum_difference']:
        reasons.append('The confidence difference exceeds the configured limit.')
    result = 'Manual Review Required'
    if not reasons and first['predicted_class'] == 'Valid Claim':
        result = 'Likely Valid'
    elif not reasons and first['predicted_class'] == 'Invalid Claim':
        result = 'Likely Invalid'
    elif not reasons:
        reasons.append('Both classifiers recommend manual review.')
    res.update(result=result, reasons=reasons,
               passed=[item['details'] for item in findings if item['result'] == 'Pass'])
    return res


def latest_evaluation(db, claim_id):
    row = db.execute('SELECT * FROM evaluations WHERE claim_id=? ORDER BY id DESC LIMIT 1', (claim_id,)).fetchone()
    return json.loads(row['details']) if row else None


def store_evaluation(db, claim_id, findings, first=None, second=None):
    limits = load_limits()
    res = decide(first, second, findings, limits)
    res['limits'] = limits
    res['prediction_ids'] = [dict(row)['id'] for row in (first, second) if row]
    db.execute('INSERT INTO evaluations(claim_id,result,consistency,difference,details,created_at) VALUES(?,?,?,?,?,datetime(\'now\'))',
               (claim_id, res['result'], res['status'], res['difference'], json.dumps(res)))
    return res
