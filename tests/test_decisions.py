import unittest

from decision_service import compare_results, decide


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.limits = dict(minimum_confidence=.7, strong_difference=.05,
                           acceptable_difference=.15, maximum_difference=.25)
        self.checks = [dict(rule_name='coverage', result='Pass', details='Coverage checked.')]

    def scores(self, name='Valid Claim', conf=.9):
        values = dict(zip(('Valid Claim', 'Invalid Claim', 'Manual Review'), [(1-conf)/2]*3))
        values[name] = conf
        return dict(predicted_class=name, valid_conf=values['Valid Claim'],
                    invalid_conf=values['Invalid Claim'], manual_conf=values['Manual Review'], top_conf=conf)

    def test_consistency_categories(self):
        first = self.scores(conf=.95)
        for conf, expected in [(.94, 'Strong Match'), (.85, 'Acceptable Match'), (.72, 'Weak Match'), (.6, 'Uncertain Result')]:
            res = compare_results(first, self.scores(conf=conf), self.limits)
            self.assertEqual(res['status'], expected)
            self.assertAlmostEqual(res['difference'], abs(.95-conf))
        self.assertEqual(compare_results(first, self.scores('Invalid Claim'), self.limits)['status'], 'Model Disagreement')

    def test_final_results(self):
        for name, result in [('Valid Claim', 'Likely Valid'), ('Invalid Claim', 'Likely Invalid'), ('Manual Review', 'Manual Review Required')]:
            res = decide(self.scores(name), self.scores(name), self.checks, self.limits)
            self.assertEqual(res['result'], result)

    def test_all_rule_issues_require_review(self):
        for name in ['coverage', 'documents', 'serial', 'duplicate_document', 'contradictions', 'repairs']:
            for status in ['Fail', 'Warning', 'Review']:
                checks = [dict(rule_name=name, result=status, details='Needs checking.')]
                res = decide(self.scores(), self.scores(), checks, self.limits)
                self.assertEqual(res['result'], 'Manual Review Required')

    def test_missing_and_bad_scores(self):
        rows = [None, self.scores(conf=float('nan')), self.scores(conf=1.2)]
        bad = self.scores()
        bad['top_conf'] = 'bad'
        rows.append(bad)
        for row in rows:
            res = decide(row, self.scores(), self.checks, self.limits)
            self.assertEqual(res['result'], 'Manual Review Required')
            self.assertEqual(res['status'], 'Uncertain Result')

    def test_confidence_limits_and_missing_rules(self):
        self.limits['minimum_confidence'] = .5
        res = decide(self.scores(conf=.99), self.scores(conf=.6), self.checks, self.limits)
        self.assertEqual(res['result'], 'Manual Review Required')
        self.assertEqual(decide(self.scores(), self.scores(), [], self.limits)['result'], 'Manual Review Required')
        self.limits.update(strong_difference=.125, acceptable_difference=.25, maximum_difference=.25)
        self.assertEqual(compare_results(self.scores(conf=1), self.scores(conf=.875), self.limits)['status'], 'Strong Match')
        self.assertEqual(compare_results(self.scores(conf=1), self.scores(conf=.75), self.limits)['status'], 'Acceptable Match')


if __name__ == '__main__':
    unittest.main()
