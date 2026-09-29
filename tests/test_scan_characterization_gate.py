"""Fictional Git/event/evidence proofs; no benchmark measurements are run."""
import copy
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from scripts import scan_characterization_gate as gate
from benchmarks import source_scan_profile_series as series, source_scan_soak as soak
from test_scan_profile_series import fictional_pair


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fictional-characterization-gate-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '--quiet')
        for key, value in (('user.name', 'Fictional Benchmark'), ('user.email', 'fictional@example.invalid'),
                           ('core.autocrlf', 'false'), ('core.hooksPath', str(self.root / 'no-hooks'))):
            self.git('config', key, value)
        for name in gate.PROTECTED_FILES:
            self.write(name, (series.ROOT / name).read_bytes())
        self.write('docs/fictional.md', b'Fictional documentation before publication.\n')
        self.before = self.commit('fictional predecessor')
        digests = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest() for name in series.CODE_FILES}
        code = {'revision': self.before, 'dirty': False, 'checkout_dirty': True, 'digests': digests}
        identity = {'run_id': '123', 'run_attempt': 1}
        runtime = dict(series.runtime_metadata(), host_kind='github-hosted')
        pairs = [fictional_pair(system, index, identity, code, runtime, count=2048, page_size=256)
                 for system in series.PLATFORMS for index in range(1, 5)]
        self.report = {'schema': series.SERIES_SCHEMA, 'status': 'complete', 'identity': identity, 'code': code,
                       'configuration': {'count': 2048, 'page_size': 256, 'pairs': 4,
                                         'platforms': list(series.PLATFORMS)},
                       'pairs': pairs, 'issues': [], 'note': series.NOTE,
                       'summaries': series._summaries(pairs, series.PLATFORMS)}
        series.validate_public_report(self.report)
        self.archive = gate.EVIDENCE_PREFIX + 'fictional-hosted-series.json'
        self.write(self.archive, json.dumps(self.report).encode())
        self.publish()

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.root, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, check=True, timeout=10).stdout.decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def commit(self, message, *parents):
        self.git('add', '-A')
        tree = self.git('write-tree')
        arguments = ['commit-tree', tree, '-m', message]
        for parent in parents:
            arguments += ['-p', parent]
        return self.git(*arguments)

    def publish(self, *, parent=None, base=None):
        self.write('docs/fictional.md', b'Fictional documentation/evidence publication.\n')
        after = self.commit('fictional publication', parent or self.before)
        current = self.commit('fictional merge checkout', base or self.before, after)
        self.git('update-ref', 'HEAD', current)
        self.event = {'action': 'synchronize', 'before': self.before, 'after': after,
                      'pull_request': {'head': {'sha': after}, 'base': {'sha': base or self.before}}}
        self.environment = {'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': current}

    def decision(self, event=None, environment=None):
        return gate.decide(self.root, self.event if event is None else event,
                           self.environment if environment is None else environment)

    def test_complete_canonical_archive_and_full_delta_skip_without_relabel_or_aggregation(self):
        original = (self.root / self.archive).read_bytes()
        with patch.object(series, 'aggregate', side_effect=AssertionError('Old data must not be reaggregated')):
            result = self.decision()
        self.assertFalse(result.measure)
        self.assertEqual(result.reason, 'accepted_archive')
        self.assertEqual(result.evidence['revision'], self.before)
        self.assertEqual(result.evidence['run_id'], '123')
        self.assertEqual((self.root / self.archive).read_bytes(), original)
        self.assertTrue(self.report['code']['checkout_dirty'])  # Downloaded artifacts can make this true.

    def test_other_events_attempts_malformed_or_mismatched_refs_always_measure(self):
        for action in ('opened', 'reopened', 'closed', None):
            event = dict(self.event, action=action)
            with self.subTest(action=action):
                self.assertTrue(self.decision(event).measure)
        for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_RUN_ATTEMPT', None),
                           ('GITHUB_EVENT_NAME', 'push'), ('GITHUB_SHA', 'f' * 40)):
            environment = dict(self.environment, **{key: value})
            with self.subTest(environment=key, value=value):
                self.assertTrue(self.decision(environment=environment).measure)
        for key, value in (('before', 'f' * 40), ('before', 'private argument'),
                           ('after', self.before), ('before', self.event['after'])):
            with self.subTest(field=key, value=value):
                self.assertTrue(self.decision(dict(self.event, **{key: value})).measure)
        orphan = self.commit('fictional unrelated history')
        self.assertTrue(self.decision(dict(self.event, before=orphan)).measure)

    def test_wrong_merge_checkout_and_nonmerge_head_measure(self):
        self.git('update-ref', 'HEAD', self.event['after'])
        environment = dict(self.environment, GITHUB_SHA=self.event['after'])
        self.assertTrue(self.decision(environment=environment).measure)

    def test_multi_commit_endpoint_detects_source_change_hidden_from_head_parent(self):
        name = series.CODE_FILES[0]
        self.write(name, (self.root / name).read_bytes() + b'\n# Fictional protected change.\n')
        middle = self.commit('fictional source change', self.before)
        self.publish(parent=middle)
        self.assertEqual(self.decision().reason, 'changed_inputs')

    def test_renamed_sensitive_path_and_nonpublication_path_measure(self):
        name = series.CODE_FILES[0]
        (self.root / name).rename(self.root / 'docs' / 'renamed-source.py')
        self.publish()
        self.assertEqual(self.decision().reason, 'changed_inputs')
        self.write(name, (series.ROOT / name).read_bytes())
        self.write('README.md', b'Fictional nonallowlisted publication.\n')
        self.publish()
        self.assertEqual(self.decision().reason, 'changed_inputs')

    def test_base_or_worktree_protected_drift_measure(self):
        for name in (*series.CODE_FILES, '.gitattributes', 'requirements.txt',
                     '.github/workflows/scan-characterization.yml', 'scripts/scan_characterization_gate.py'):
            original = (self.root / name).read_bytes()
            self.write(name, original + b'\n# Fictional drift.\n')
            with self.subTest(path=name):
                self.assertTrue(self.decision().measure)
            self.write(name, original)
        original_after = self.event['after']
        name = series.CODE_FILES[0]
        self.write(name, (self.root / name).read_bytes() + b'\n# Fictional base drift.\n')
        base = self.commit('fictional changed base', self.before)
        current = self.commit('fictional changed-base merge', base, original_after)
        self.git('update-ref', 'HEAD', current)
        self.event['pull_request']['base']['sha'] = base
        self.environment['GITHUB_SHA'] = current
        self.assertEqual(self.decision().reason, 'changed_inputs')

    def test_incomplete_local_dirty_wrong_digest_grid_fixture_and_math_archives_measure(self):
        def identities(value):
            return [value['identity'], *[pair['identity'] for pair in value['pairs']],
                    *[sample['trial']['identity'] for pair in value['pairs'] for sample in pair['samples']]]
        def codes(value):
            return [value['code'], *[pair['code'] for pair in value['pairs']],
                    *[sample['trial']['code'] for pair in value['pairs'] for sample in pair['samples']]]
        def runtimes(value):
            return [pair['runtime'] for pair in value['pairs']] + [sample['trial']['runtime']
                    for pair in value['pairs'] for sample in pair['samples']]
        changes = {
            'incomplete': lambda value: (value.update(status='incomplete', issues=[series._issue('missing_pair')]), value.pop('summaries')),
            'local': lambda value: [identity.update(run_id='local') for identity in identities(value)],
            'dirty': lambda value: [code.update(dirty=True) for code in codes(value)],
            'digest': lambda value: [code['digests'].update({series.CODE_FILES[0]: 'f' * 64}) for code in codes(value)],
            'missing': lambda value: value['pairs'].pop(),
            'duplicate': lambda value: value['pairs'].__setitem__(1, copy.deepcopy(value['pairs'][0])),
            'math': lambda value: value['summaries']['Linux']['intervals']['observation']['variant_ns']['baseline'].update(median=999),
            'legacy': lambda value: [sample['trial']['soak']['fixture'].update(recipe=soak.FIXTURE_RECIPE)
                                     for pair in value['pairs'] for sample in pair['samples']],
            'self-hosted': lambda value: [runtime.update(host_kind='self-hosted') for runtime in runtimes(value)],
        }
        for label, change in changes.items():
            value = copy.deepcopy(self.report)
            change(value)
            if label in ('local', 'dirty', 'digest', 'legacy', 'self-hosted'):
                series.validate_public_report(value)  # Gate refusal must not depend on invalid shape.
            self.write(self.archive, json.dumps(value).encode())
            self.publish()
            with self.subTest(label=label):
                self.assertTrue(self.decision().measure)

    def test_untracked_dirty_symlink_oversized_and_duplicate_json_archives_measure(self):
        original = (self.root / self.archive).read_bytes()
        (self.root / self.archive).unlink()
        self.publish()
        self.write(self.archive, original)  # Untracked evidence is not publication proof.
        self.assertTrue(self.decision().measure)
        self.publish()
        self.write(self.archive, original + b'\n')  # Different working bytes from the tracked blob.
        self.assertTrue(self.decision().measure)
        self.write(self.archive, original)
        with patch.object(gate.Path, 'is_symlink', return_value=True):
            self.assertTrue(self.decision().measure)
        self.write(self.archive, b' ' * (gate.MAX_REPORT_BYTES + 1))
        self.publish()
        self.assertTrue(self.decision().measure)
        self.write(self.archive, original.replace(b'"status": "complete"', b'"status": "incomplete", "status": "complete"', 1))
        self.publish()
        self.assertTrue(self.decision().measure)

    def test_git_failure_and_bounds_choose_measure(self):
        for failure in (subprocess.TimeoutExpired('private Git argument', 10), OSError('private Git path')):
            with self.subTest(error=type(failure).__name__), patch.object(gate, '_git', side_effect=failure):
                self.assertTrue(self.decision().measure)
        for raw in (b'not-null-terminated', b'../private\0', b'docs/a\0' * (gate.MAX_PATHS + 1)):
            with self.subTest(path_list=len(raw)), self.assertRaises(ValueError):
                gate._paths(raw)

    def test_an_invalid_archive_cannot_hide_behind_an_earlier_valid_one(self):
        self.write(gate.EVIDENCE_PREFIX + 'zzz-fictional-invalid.json', b'{"status":"private arbitrary status"}')
        self.publish()
        result = self.decision()
        self.assertTrue(result.measure)
        self.assertEqual(result.reason, 'no_accepted_archive')

    def test_valid_historical_local_and_incomplete_archives_coexist_with_accepted_evidence(self):
        local = (series.ROOT / 'benchmarks/source-scan-results/2026-09-29/linux-local-series.json').read_bytes()
        incomplete = copy.deepcopy(self.report)
        incomplete.update(status='incomplete', issues=[series._issue('incomparable')])
        incomplete.pop('summaries')
        incomplete['pairs'][-1].update(status='incomplete', samples=[], issues=[series._issue('child_timeout')])
        series.validate_public_report(incomplete)
        self.write(gate.EVIDENCE_PREFIX + 'earlier-local.json', local)
        self.write(gate.EVIDENCE_PREFIX + 'earlier-incomplete.json', json.dumps(incomplete).encode())
        minimal = {'schema': series.PAIR_SCHEMA, 'status': 'incomplete', 'samples': [],
                   'issues': [series._issue('invalid_report', ValueError())]}
        pair = copy.deepcopy(self.report['pairs'][0])
        series.validate_public_report(minimal)
        series.validate_public_report(pair)
        self.write(gate.EVIDENCE_PREFIX + 'earlier-minimal-pair.json', json.dumps(minimal).encode())
        self.write(gate.EVIDENCE_PREFIX + 'earlier-complete-pair.json', json.dumps(pair).encode())
        self.publish()
        result = self.decision()
        self.assertFalse(result.measure)
        self.assertEqual(result.evidence['revision'], self.report['code']['revision'])
        self.assertEqual((self.root / (gate.EVIDENCE_PREFIX + 'earlier-local.json')).read_bytes(), local)

    def test_cli_outputs_fixed_decision_and_evidence_summary_and_visible_write_failure(self):
        event = self.root / 'fictional-event.json'
        event.write_text(json.dumps(self.event))
        output, summary = self.root / 'output.txt', self.root / 'summary.md'
        environment = {**self.environment, 'GITHUB_EVENT_PATH': str(event),
                       'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}
        with patch.dict(os.environ, environment), patch.object(series, 'ROOT', self.root), redirect_stdout(StringIO()):
            self.assertEqual(gate.main(), 0)
        self.assertIn('measure=false', output.read_text())
        self.assertIn(self.before, summary.read_text())
        event.write_text('{"action":"synchronize","action":"private duplicate"}')
        with patch.dict(os.environ, environment), patch.object(series, 'ROOT', self.root), redirect_stdout(StringIO()):
            self.assertEqual(gate.main(), 0)
        self.assertTrue(output.read_text().endswith('measure=true\nreason=proof_unavailable\n'))
        environment['GITHUB_OUTPUT'] = str(self.root / 'absent' / 'private-output')
        captured = StringIO()
        with patch.dict(os.environ, environment), patch.object(series, 'ROOT', self.root), redirect_stdout(captured):
            self.assertEqual(gate.main(), 1)
        self.assertNotIn('private', captured.getvalue())


if __name__ == '__main__':
    unittest.main()
