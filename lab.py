"""Local observation records and transparent comparison hypotheses. No third-party dependencies."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VERSION = '0.1.0'
SCHEMA = 'bird-voice-lab/1'
CONTROLS = {
    'chance': 'Uniform chance', 'position': 'First-position bias',
    'brightness': 'Brightness bias', 'habit': 'Past-choice frequency',
    'echo': 'Prompt echo', 'context': 'Recorded context',
}


class LabError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, label, maximum=2000, required=False):
    if not isinstance(value, str):
        raise LabError(f'{label} must be text.')
    value = value.strip()
    if len(value) > maximum or (required and not value):
        raise LabError(f'{label} must contain 1–{maximum} characters.' if required else f'{label} is too long.')
    return value


def number(value, label, minimum=0, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LabError(f'{label} must be a finite number.')
    if not minimum <= value <= maximum:
        raise LabError(f'{label} must be between {minimum} and {maximum}.')
    return value


def integer(value, label, minimum, maximum):
    number(value, label, minimum, maximum)
    if int(value) != value:
        raise LabError(f'{label} must be a whole number.')
    return int(value)


def normalize(weights):
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()} if total > 0 else {k: 1 / len(weights) for k in weights}


def predictions(choices, features, prompt, previous):
    """The signature excludes objective answers and current/future observations."""
    n = len(choices)
    counts = {c: 1.0 for c in choices}  # Laplace prior, only completed earlier responses.
    for observation in previous:
        if observation['outcome'] == 'response' and observation['choice'] in counts:
            counts[observation['choice']] += 1
    mentions = [(prompt.casefold().rfind(c.casefold()), c) for c in choices]
    index, echo = max(mentions)
    echo_weights = {c: 1.0 for c in choices}
    if index >= 0:
        echo_weights[echo] = 8.0
    weights = {
        'chance': {c: 1 for c in choices},
        'position': {c: 4 if i == 0 else 1 for i, c in enumerate(choices)},
        'brightness': {f['choice']: 0.05 + f['brightness'] for f in features},
        'habit': counts,
        'echo': echo_weights,
        'context': {f['choice']: 0.05 + f['context_weight'] for f in features},
    }
    visible = {
        'chance': ['available_choices'], 'position': ['recorded_display_order'],
        'brightness': ['brightness'], 'habit': ['previous_completed_choices'],
        'echo': ['prompt', 'available_choices'], 'context': ['precommitted_context_weights'],
    }
    notes = {
        'chance': 'Each available option is equally likely.',
        'position': 'The first recorded position has weight 4; others have weight 1.',
        'brightness': 'Weights equal recorded brightness plus 0.05.',
        'habit': 'Counts earlier completed choices plus one per available option.',
        'echo': 'The last label occurring in the prompt has weight 8; others have weight 1. Substring matching is a simple authored heuristic.',
        'context': 'Uses researcher-supplied context weights plus 0.05. These ratings are not an independent measurement of meaning.',
    }
    return [{'id': k, 'name': CONTROLS[k], 'probabilities': normalize(v),
             'visible_inputs': visible[k], 'rationale': notes[k], 'weights': v,
             'prior_response_count': sum(o['outcome'] == 'response' for o in previous) if k == 'habit' else 0}
            for k, v in weights.items()]


def verify_export(bundle):
    errors = []
    if not isinstance(bundle, dict) or bundle.get('schema') != SCHEMA:
        return {'valid': False, 'errors': ['Unsupported export schema.']}
    events = bundle.get('events')
    receipt = bundle.get('receipt')
    if not isinstance(events, list) or not isinstance(receipt, dict) or not events:
        return {'valid': False, 'errors': ['Missing events or receipt.']}
    previous = '0' * 64
    for i, event in enumerate(events, 1):
        try:
            unsigned = {k: v for k, v in event.items() if k != 'hash'}
            if event['sequence'] != i or event['previous_hash'] != previous or digest(unsigned) != event['hash']:
                errors.append(f'Event {i} does not match the chain.')
            previous = event['hash']
        except (AttributeError, KeyError, TypeError, ValueError):
            errors.append(f'Event {i} is malformed.')
    if receipt.get('count') != len(events) or receipt.get('head') != previous:
        errors.append('The export does not match its receipt.')
    return {'valid': not errors, 'errors': errors, 'count': len(events), 'head': previous}


def score(trials):
    completed = [t for t in trials if 'observation' in t]
    responses = [t for t in completed if t['observation']['outcome'] == 'response']
    assessed = [t for t in responses if t['observation']['corroboration'] in ('yes', 'no')]
    corroborated = sum(t['observation']['corroboration'] == 'yes' for t in assessed)
    objective = [t for t in responses if t['target'] is not None]
    controls = []
    for key, label in CONTROLS.items():
        brier, losses = [], []
        for t in responses:
            p = next(p['probabilities'] for p in t['predictions'] if p['id'] == key)
            choice = t['observation']['choice']
            brier.append(sum((v - int(c == choice)) ** 2 for c, v in p.items()))
            losses.append(-math.log(max(p[choice], 1e-15)))
        controls.append({'id': key, 'name': label, 'n': len(responses),
            'brier': sum(brier) / len(brier) if brier else None,
            'log_loss': sum(losses) / len(losses) if losses else None})
    return {'completed': len(completed), 'responses': len(responses),
        'withdrawals': sum(t['observation']['outcome'] == 'withdrawal' for t in completed),
        'missing': sum(t['observation']['outcome'] == 'no_response' for t in completed),
        'distress': sum(t['observation']['outcome'] == 'distress' for t in completed),
        'corroboration_assessed': len(assessed), 'corroborated': corroborated,
        'corroboration_rate': corroborated / len(assessed) if assessed else None,
        'objective_trials': len(objective),
        'objective_correct': sum(t['observation']['choice'] == t['target'] for t in objective),
        'controls': controls,
        'interpretation': 'Descriptive prediction fit only. Lower scores indicate a better match to recorded choices, not proof of communication or agency. Corroboration uses the predeclared criterion and requires independent review.'}


class Lab:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (study TEXT NOT NULL, sequence INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(study, sequence))')
            db.execute("CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'Events are append-only'); END")
            db.execute("CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'Events are append-only'); END")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _events(self, db, study):
        return [json.loads(row[0]) for row in db.execute('SELECT record FROM events WHERE study=? ORDER BY sequence', (study,))]

    def _state(self, events):
        if not events:
            raise LabError('Study not found.')
        receipt = {'head': events[-1]['hash'], 'count': len(events)}
        if not verify_export({'schema': SCHEMA, 'events': events, 'receipt': receipt})['valid']:
            raise LabError('The stored event chain does not verify. Preserve the database for inspection.')
        config = copy.deepcopy(events[0]['payload'])
        state = {**config, 'status': 'open', 'trials': [], 'head': receipt['head'], 'event_count': len(events)}
        for event in events[1:]:
            if event['type'] == 'trial':
                state['trials'].append({**copy.deepcopy(event['payload']), 'status': 'pending'})
            elif event['type'] == 'observation':
                trial = next(t for t in state['trials'] if t['id'] == event['payload']['trial_id'])
                trial['observation'] = copy.deepcopy(event['payload']); trial['status'] = 'recorded'
            elif event['type'] == 'closed':
                state['status'] = 'closed'; state['closed_reason'] = event['payload']['reason']
        state['summary'] = score(state['trials'])
        return state

    def _append(self, db, study, kind, payload):
        events = self._events(db, study)
        if events:
            self._state(events)
        event = {'sequence': len(events) + 1, 'study_id': study, 'timestamp': now(),
            'type': kind, 'payload': payload, 'previous_hash': events[-1]['hash'] if events else '0' * 64}
        event['hash'] = digest(event)
        db.execute('INSERT INTO events VALUES (?, ?, ?)', (study, event['sequence'], canonical(event)))
        return event

    def list_studies(self):
        with self.connect() as db:
            rows = db.execute('SELECT DISTINCT study FROM events ORDER BY rowid DESC').fetchall()
            result = []
            for row in rows:
                s = self._state(self._events(db, row[0]))
                result.append({k: s[k] for k in ('id', 'title', 'subject', 'synthetic', 'status', 'created_at') } | {'trials': len(s['trials'])})
            return result

    def get_study(self, study, reveal=False):
        with self.connect() as db:
            s = self._state(self._events(db, study))
        for trial in s['trials']:
            if trial['status'] == 'pending' and not reveal:
                trial.pop('predictions', None)
        return s

    def create_study(self, data):
        choices = data.get('choices', [])
        if not isinstance(choices, list) or not 2 <= len(choices) <= 12:
            raise LabError('Choose between 2 and 12 symbols.')
        choices = [text(c, 'Symbol', 60, True) for c in choices]
        if len({c.casefold() for c in choices}) != len(choices):
            raise LabError('Symbols must be distinct, ignoring capitalization.')
        synthetic = data.get('synthetic', False)
        if not isinstance(synthetic, bool): raise LabError('Synthetic must be true or false.')
        config = {'id': uuid.uuid4().hex, 'title': text(data.get('title', ''), 'Study name', 120, True),
            'subject': text(data.get('subject', ''), 'Subject code', 80, True),
            'question': text(data.get('question', ''), 'Question', 2000, True),
            'criterion': text(data.get('criterion', ''), 'Corroboration criterion', 2000, True),
            'seed': integer(data.get('seed', 42), 'Seed', 0, 2**31 - 1),
            'max_trials': integer(data.get('max_trials', 40), 'Maximum trials', 1, 200),
            'choices': choices, 'synthetic': synthetic, 'created_at': now(), 'software_version': VERSION,
            'control_labels_hash': digest(CONTROLS), 'design': 'Prospective observation; manual scoring; six authored comparison models.'}
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); self._append(db, config['id'], 'study', config)
        return self.get_study(config['id'])

    def commit_trial(self, study, data):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            s = self._state(self._events(db, study))
            if s['status'] != 'open': raise LabError('This study is closed. Start a new study to continue.')
            if any(t['status'] == 'pending' for t in s['trials']): raise LabError('Record the pending observation first.')
            if len(s['trials']) >= s['max_trials']: raise LabError('The predeclared trial limit has been reached.')
            features = data.get('features')
            if not isinstance(features, list) or len(features) != len(s['choices']):
                raise LabError('Record each available symbol and its features.')
            clean = []
            for f in features:
                if not isinstance(f, dict): raise LabError('Invalid symbol features.')
                clean.append({'choice': text(f.get('choice', ''), 'Symbol', 60, True),
                    'brightness': number(f.get('brightness', 0.5), 'Brightness', 0, 1),
                    'context_weight': number(f.get('context_weight', 1), 'Context weight', 0, 10)})
            choices = [f['choice'] for f in clean]
            if set(choices) != set(s['choices']) or len(set(choices)) != len(choices):
                raise LabError('The display must contain each study symbol exactly once.')
            target = data.get('target') or None
            if target is not None and target not in choices: raise LabError('Objective target must be an available symbol.')
            prompt = text(data.get('prompt', ''), 'Prompt')
            trial = {'id': uuid.uuid4().hex, 'number': len(s['trials']) + 1, 'prompt': prompt,
                'context': text(data.get('context', ''), 'Context'), 'target': target,
                'features': clean, 'display_order': choices, 'committed_at': now(),
                'predictions': predictions(choices, clean, prompt, [t['observation'] for t in s['trials'] if 'observation' in t])}
            self._append(db, study, 'trial', trial)
        return {'id': trial['id'], 'number': trial['number'], 'committed_at': trial['committed_at']}

    def record_observation(self, study, trial_id, data):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); s = self._state(self._events(db, study))
            if s['status'] != 'open': raise LabError('Study is closed.')
            trial = next((t for t in s['trials'] if t['id'] == trial_id), None)
            if trial is None or trial['status'] != 'pending': raise LabError('Only the pending trial can receive an observation.')
            outcome = data.get('outcome', 'response')
            if outcome not in ('response', 'no_response', 'withdrawal', 'distress'): raise LabError('Invalid observation outcome.')
            choice = data.get('choice') or None
            if outcome == 'response' and choice not in s['choices']: raise LabError('Select an available response.')
            if outcome != 'response' and choice is not None: raise LabError('A nonresponse cannot also contain a selection.')
            corroboration = data.get('corroboration', 'unknown')
            if corroboration not in ('yes', 'no', 'unknown', 'not_applicable'): raise LabError('Invalid corroboration value.')
            if outcome != 'response' and corroboration == 'yes': raise LabError('A nonresponse cannot be corroborated.')
            latency = data.get('latency_seconds')
            if latency is not None: latency = number(latency, 'Latency', 0, 86400)
            initiated = data.get('initiated', False)
            if not isinstance(initiated, bool): raise LabError('Initiated must be true or false.')
            record = {'trial_id': trial_id, 'choice': choice, 'outcome': outcome,
                'corroboration': corroboration, 'initiated': initiated, 'latency_seconds': latency,
                'notes': text(data.get('notes', ''), 'Observation notes', 4000),
                'media_reference': text(data.get('media_reference', ''), 'Media reference', 500),
                'recorded_at': now()}
            self._append(db, study, 'observation', record)
            previous = [t['observation'] for t in s['trials'] if 'observation' in t] + [record]
            reason = outcome if outcome in ('withdrawal', 'distress') else None
            if len(previous) >= s['max_trials']: reason = reason or 'Trial limit reached'
            if len(previous) >= 2 and all(o['outcome'] == 'no_response' for o in previous[-2:]): reason = reason or 'Two consecutive nonresponses'
            if reason: self._append(db, study, 'closed', {'reason': reason})
        return self.get_study(study)

    def close_study(self, study):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); s = self._state(self._events(db, study))
            if s['status'] == 'closed': return s
            if any(t['status'] == 'pending' for t in s['trials']): raise LabError('Record or withdraw from the pending trial before closing.')
            self._append(db, study, 'closed', {'reason': 'Researcher closed session'})
        return self.get_study(study)

    def export_study(self, study):
        with self.connect() as db:
            events = self._events(db, study); state = self._state(events)
        return {'schema': SCHEMA, 'software_version': VERSION, 'exported_at': now(),
            'notice': 'Includes unblinded controls. Store the receipt separately. Hash chaining detects changes relative to a retained receipt, not fabrication or a fully rewritten chain.',
            'events': events, 'receipt': {'count': len(events), 'head': events[-1]['hash']}, 'summary': state['summary']}

    def demo(self):
        s = self.create_study({'title': 'A first look · synthetic example', 'subject': 'Demo Bird',
            'question': 'Do selections change when the recorded context changes?',
            'criterion': 'Synthetic fulfillment recorded by the example generator, not a bird observation.',
            'choices': ['apple', 'music', 'rest'], 'seed': 42, 'max_trials': 12, 'synthetic': True})
        for i in range(12):
            preferred = s['choices'][i // 4]
            order = s['choices'][i % 3:] + s['choices'][:i % 3]
            t = self.commit_trial(s['id'], {'prompt': '', 'context': f'Synthetic context favors {preferred}.',
                'features': [{'choice': c, 'brightness': 0.5, 'context_weight': 8 if c == preferred else 1} for c in order]})
            self.record_observation(s['id'], t['id'], {'choice': preferred, 'initiated': True,
                'corroboration': 'yes' if i % 4 != 0 else 'unknown', 'notes': 'Generated example, not empirical data.'})
        return self.get_study(s['id'])


def simulate(data):
    """Paired synthetic environments: choices affect subsequent learned values."""
    seed = integer(data.get('seed', 42), 'Seed', 0, 2**31 - 1)
    steps = integer(data.get('steps', 80), 'Steps', 10, 300)
    reverse = integer(data.get('reverse_at', steps // 2), 'Reversal step', 1, steps - 1)
    choices = ['apple', 'music', 'rest']
    agents = {}
    for kind in ('adaptive', 'frozen', 'chance'):
        rng = random.Random(seed)
        values = {c: 0.0 for c in choices}; counts = {c: 0 for c in choices}; fatigue = 0.0
        trace = []
        for i in range(steps):
            before = {'values': dict(values), 'fatigue': fatigue, 'visits': dict(counts)}
            scores = {c: values[c] + 0.16 / (1 + counts[c]) - 0.20 * fatigue for c in choices}
            scores['rest'] = values['rest'] + 0.16 / (1 + counts['rest']) + 0.60 * fatigue
            draw = rng.random()
            explore_draw = rng.randrange(len(choices))
            if kind == 'chance' or draw < 0.12:
                chosen = choices[explore_draw]; reason = 'Seeded exploration' if kind != 'chance' else 'Uniform random choice'
            else:
                chosen = max(choices, key=lambda c: scores[c]); reason = 'Highest state-dependent score'
            rewards = {'apple': 0.9 if i < reverse else 0.1, 'music': 0.1 if i < reverse else 0.9, 'rest': 0.25}
            reward = rewards[chosen]
            if kind == 'adaptive': values[chosen] += 0.25 * (reward - values[chosen])
            counts[chosen] += 1
            fatigue = max(0.0, fatigue - 0.40) if chosen == 'rest' else min(1.0, fatigue + 0.10)
            trace.append({'step': i + 1, 'phase': 'before reversal' if i < reverse else 'after reversal',
                'choice': chosen, 'reward': reward, 'scores': scores, 'reason': reason, 'random_draw': draw,
                'exploration_index': explore_draw, 'state_before': before,
                'state_after': {'values': dict(values), 'fatigue': fatigue, 'visits': dict(counts)}})
        agents[kind] = {'trace': trace, 'final_values': values,
            'total_reward': sum(t['reward'] for t in trace), 'counts': counts}
    return {'synthetic': True, 'seed': seed, 'steps': steps, 'reverse_at': reverse, 'agents': agents,
        'rules': {'learning_rate': 0.25, 'exploration_probability': 0.12, 'choice_order_for_ties': choices,
            'exploration_bonus': '0.16/(1+visits)', 'activity_fatigue_cost': 0.20, 'rest_fatigue_bonus': 0.60,
            'fatigue_increase': 0.10, 'fatigue_recovery': 0.40,
            'rewards_before': {'apple': 0.9, 'music': 0.1, 'rest': 0.25},
            'rewards_after': {'apple': 0.1, 'music': 0.9, 'rest': 0.25}},
        'interpretation': 'Authored learning mechanisms in a constructed environment. Learning-disabled shares the adaptive action rule and random tape; chance is a separate policy. A successful reversal demonstrates this implementation, not subjective experience or a validated model of a bird.'}
