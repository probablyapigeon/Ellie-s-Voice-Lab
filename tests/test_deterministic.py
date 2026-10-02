import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab import Lab, LEGACY_CONTROLS, predictions, simulate, score, canonical, digest


class DeterministicTests(unittest.TestCase):
    def features(self):
        return [{'choice':'apple','brightness':0.2,'context_weight':1},
                {'choice':'music','brightness':0.8,'context_weight':1},
                {'choice':'rest','brightness':0.8,'context_weight':1}]

    def predict(self, history=(), context='Quiet afternoon'):
        return {p['id']:p for p in predictions(['apple','music','rest'], self.features(), '',
            [h['observation'] for h in history], context, history)}

    def test_fixed_rules_and_declared_ties(self):
        with patch('lab.random.Random', side_effect=AssertionError('Randomness forbidden')):
            p = self.predict()
        self.assertEqual(p['det_position']['selected_choice'], 'apple')
        self.assertEqual(p['det_brightness']['selected_choice'], 'music')
        self.assertEqual(p['det_habit']['selected_choice'], 'apple')
        for key in ('det_position','det_brightness','det_habit','det_learner'):
            self.assertTrue(p[key]['deterministic'])
            self.assertEqual(sum(p[key]['probabilities'].values()), 1)
            self.assertEqual(sorted(p[key]['probabilities'].values()), [0,0,1])

    def test_context_learner_uses_only_assessed_prior_behavior(self):
        history = [{'context':' Quiet  AFTERNOON ', 'observation':
            {'outcome':'response','choice':'music','corroboration':'yes'}}]
        p = self.predict(history)['det_learner']
        self.assertEqual(p['selected_choice'], 'music')
        self.assertEqual(p['state']['values']['music'], 0.25)
        history.append({'context':'Quiet afternoon','observation':
            {'outcome':'response','choice':'music','corroboration':'no'}})
        self.assertEqual(self.predict(history)['det_learner']['state']['values']['music'], 0.1875)
        self.assertEqual(self.predict(history, 'A different context')['det_learner']['selected_choice'], 'apple')
        for outcome, corroboration in [('response','unknown'),('no_response','not_applicable'),('withdrawal','not_applicable')]:
            extra = {'context':'Quiet afternoon','observation':
                {'outcome':outcome,'choice':'rest' if outcome == 'response' else None,'corroboration':corroboration}}
            self.assertEqual(self.predict(history+[extra])['det_learner']['state'], self.predict(history)['det_learner']['state'])

    def test_seed_independence_and_zero_random_draws(self):
        a = simulate({'seed':1,'steps':80,'reverse_at':40})
        b = simulate({'seed':999,'steps':80,'reverse_at':40})
        for kind in ('deterministic','det_frozen'):
            self.assertEqual(a['agents'][kind], b['agents'][kind])
            self.assertTrue(all(t['random_draw'] is None and t['exploration_index'] is None for t in a['agents'][kind]['trace']))
        self.assertNotEqual(a['agents']['chance']['trace'], b['agents']['chance']['trace'])
        self.assertEqual(a['agents']['det_frozen']['final_values'], {'apple':0,'music':0,'rest':0})
        self.assertNotEqual(a['agents']['deterministic']['final_values'], a['agents']['det_frozen']['final_values'])

    def test_deterministic_scoring_retains_impossible_predictions(self):
        trial = {'target':None,'predictions':list(self.predict().values()),
            'observation':{'outcome':'response','choice':'rest','corroboration':'unknown'}}
        result = next(p for p in score([trial])['controls'] if p['id'] == 'det_position')
        self.assertEqual(result['brier'], 2)
        self.assertEqual(result['exact_matches'], 0)
        self.assertEqual(result['zero_probability_responses'], 1)
        self.assertAlmostEqual(result['log_loss'], 34.538776394910684)

    def test_existing_six_control_studies_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            lab = Lab(Path(folder)/'lab.sqlite')
            s = lab.create_study({'title':'Legacy','subject':'Bird A','question':'Question',
                'criterion':'Criterion','choices':['apple','music','rest']})
            # Construct the pre-0.2 initial record, including its valid original hash chain.
            with lab.connect() as db:
                event = lab._events(db, s['id'])[0]
                event['payload'].pop('control_ids'); event['payload']['software_version'] = '0.1.0'
                event.pop('hash'); event['hash'] = digest(event)
                db.execute('DROP TRIGGER no_update')
                db.execute('UPDATE events SET record=? WHERE study=?', (canonical(event),s['id']))
            t = lab.commit_trial(s['id'], {'features':self.features()})
            bundle = lab.export_study(s['id'])
            self.assertEqual([p['id'] for p in bundle['events'][1]['payload']['predictions']], list(LEGACY_CONTROLS))
            lab.record_observation(s['id'],t['id'],{'choice':'music'})
            self.assertEqual(len(lab.get_study(s['id'])['summary']['controls']),6)

    def test_new_predictions_remain_locked_after_response(self):
        with tempfile.TemporaryDirectory() as folder:
            lab = Lab(Path(folder)/'lab.sqlite')
            s = lab.create_study({'title':'New','subject':'Bird A','question':'Question',
                'criterion':'Criterion','choices':['apple','music','rest']})
            t = lab.commit_trial(s['id'],{'features':self.features(),'context':'Quiet afternoon','target':'rest'})
            before = copy.deepcopy(lab.export_study(s['id'])['events'][1]['payload']['predictions'])
            lab.record_observation(s['id'],t['id'],{'choice':'music','corroboration':'yes'})
            self.assertEqual(before,lab.export_study(s['id'])['events'][1]['payload']['predictions'])
            lab.commit_trial(s['id'],{'features':self.features(),'context':'Quiet afternoon'})
            next_predictions = lab.export_study(s['id'])['events'][3]['payload']['predictions']
            self.assertEqual(next(p for p in next_predictions if p['id']=='det_learner')['selected_choice'],'music')
            self.assertTrue(all('target' not in p['visible_inputs'] for p in next_predictions))
