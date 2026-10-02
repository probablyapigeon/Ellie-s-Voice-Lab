import copy
import tempfile
import unittest
from pathlib import Path

from lab import Lab, LabError, verify_export, simulate


class LabTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'lab.sqlite'
        self.lab = Lab(self.path)

    def tearDown(self):
        self.folder.cleanup()

    def study(self):
        return self.lab.create_study({'title': 'Example', 'subject': 'Bird A',
            'question': 'Are choices related to context?', 'criterion': 'Consumes offered item',
            'seed': 42, 'choices': ['apple', 'music', 'rest'], 'max_trials': 10})

    def trial(self, study):
        return self.lab.commit_trial(study['id'], {'prompt': 'Would you like music?',
            'context': 'Quiet afternoon', 'target': None, 'features': [
                {'choice': 'apple', 'brightness': 0.2, 'context_weight': 1},
                {'choice': 'music', 'brightness': 0.8, 'context_weight': 2},
                {'choice': 'rest', 'brightness': 0.5, 'context_weight': 1}]})

    def test_locked_trial_and_restart(self):
        s = self.study(); t = self.trial(s)
        hidden = self.lab.get_study(s['id'])['trials'][0]
        self.assertNotIn('predictions', hidden)
        self.assertEqual(hidden['status'], 'pending')
        with self.assertRaises(LabError): self.trial(s)
        self.lab.record_observation(s['id'], t['id'], {'choice': 'music', 'corroboration': 'yes'})
        with self.assertRaises(LabError):
            self.lab.record_observation(s['id'], t['id'], {'choice': 'apple'})
        reopened = Lab(self.path).get_study(s['id'])
        self.assertEqual(reopened['trials'][0]['observation']['choice'], 'music')
        self.assertEqual(reopened['summary']['responses'], 1)

    def test_predictions_cannot_see_target_or_future_response(self):
        s = self.study(); t = self.trial(s)
        before = self.lab.export_study(s['id'])['events'][1]['payload']['predictions']
        self.lab.record_observation(s['id'], t['id'], {'choice': 'rest'})
        after = self.lab.export_study(s['id'])['events'][1]['payload']['predictions']
        self.assertEqual(before, after)
        for prediction in before:
            self.assertEqual(set(prediction['probabilities']), {'apple', 'music', 'rest'})
            self.assertAlmostEqual(sum(prediction['probabilities'].values()), 1)
            self.assertNotIn('target', prediction['visible_inputs'])

    def test_chance_scoring_and_unknown_corroboration(self):
        s = self.study(); t = self.trial(s)
        self.lab.record_observation(s['id'], t['id'], {'choice': 'apple', 'corroboration': 'unknown'})
        report = self.lab.get_study(s['id'])['summary']
        chance = next(x for x in report['controls'] if x['id'] == 'chance')
        self.assertAlmostEqual(chance['brier'], 2/3)
        self.assertEqual(report['corroboration_assessed'], 0)
        self.assertIsNone(report['corroboration_rate'])

    def test_withdrawal_is_not_an_incorrect_answer(self):
        s = self.study(); t = self.trial(s)
        self.lab.record_observation(s['id'], t['id'], {'outcome': 'withdrawal'})
        state = self.lab.get_study(s['id'])
        self.assertEqual(state['summary']['responses'], 0)
        self.assertEqual(state['summary']['withdrawals'], 1)
        self.assertEqual(state['status'], 'closed')
        with self.assertRaises(LabError): self.trial(s)

    def test_export_detects_changes_and_truncation_with_receipt(self):
        s = self.study(); t = self.trial(s)
        self.lab.record_observation(s['id'], t['id'], {'choice': 'music'})
        bundle = self.lab.export_study(s['id'])
        self.assertTrue(verify_export(bundle)['valid'])
        altered = copy.deepcopy(bundle); altered['events'][1]['payload']['prompt'] = 'changed'
        self.assertFalse(verify_export(altered)['valid'])
        shortened = copy.deepcopy(bundle); shortened['events'].pop()
        self.assertFalse(verify_export(shortened)['valid'])

    def test_validation_and_missingness(self):
        with self.assertRaises(LabError): self.lab.create_study({'choices': ['a', 'A']})
        s = self.study(); t = self.trial(s)
        with self.assertRaises(LabError):
            self.lab.record_observation(s['id'], t['id'], {'choice': 'unknown'})
        with self.assertRaises(LabError):
            self.lab.record_observation(s['id'], t['id'], {'choice': 'apple', 'outcome': 'no_response'})
        self.lab.record_observation(s['id'], t['id'], {'outcome': 'no_response'})
        self.assertEqual(self.lab.get_study(s['id'])['summary']['missing'], 1)

    def test_sandbox_replay_and_learning_ablation(self):
        params = {'seed': 42, 'steps': 80, 'reverse_at': 40}
        a = simulate(params); b = simulate(params)
        self.assertEqual(a, b)
        self.assertTrue(a['synthetic'])
        self.assertNotEqual(a['agents']['adaptive']['final_values'], a['agents']['frozen']['final_values'])
        self.assertEqual(a['agents']['frozen']['final_values'], {'apple': 0.0, 'music': 0.0, 'rest': 0.0})


if __name__ == '__main__':
    unittest.main()
