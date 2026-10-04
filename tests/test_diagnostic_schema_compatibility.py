"""Archive readers accept fixed historical schemas; producers require current schema."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from benchmarks import source_scan_profile_series as profile, source_scan_exit_series as exit_series
from benchmarks import source_scan_exit_probe as probe
from test_scan_profile_series import fictional_pair, fictional_trial, local_environment


class SchemaCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.env = local_environment()
        self.env.__enter__()
        self.addCleanup(self.env.__exit__, None, None, None)
        self.job = patch.dict(os.environ, GITHUB_JOB='local')
        self.job.__enter__()
        self.addCleanup(self.job.__exit__, None, None, None)
        self.identity, self.code = profile.actual_identity()
        self.runtime = profile.runtime_metadata()
        self.exit_identity, self.exit_code = exit_series.actual_identity(session_token='a' * 32)

    def pair(self, module, index=1, platform=None):
        identity, code = ((self.identity, self.code) if module is profile else
                          (self.exit_identity, self.exit_code))
        pair = fictional_pair(self.runtime['platform'] if platform is None else platform,
                              index, identity, code, self.runtime)
        if module is exit_series:
            pair['schema'] = module.PAIR_SCHEMA
            for sample in pair['samples']:
                trial = sample['trial']
                trial['schema'] = module.TRIAL_SCHEMA
                if trial['variant'] == 'instrumented':
                    trial['phases'] = {phase: {'elapsed_ns': 0, 'strata': {
                        name: probe.empty_metric() for name in probe.STRATA}}
                        for phase in probe.PHASES}
        return pair

    def schema(self, pair, version):
        for sample in pair['samples']:
            sample['trial']['soak']['catalog_schema_version'] = version
        return pair

    def test_closed_reader_allowlist_rejects_unknown_boolean_and_float_versions(self):
        for module in (profile, exit_series):
            for version in (4, 5):
                module.validate_pair(self.schema(self.pair(module), version))
            for version in (True, False, 4.0, 5.0, 0, 1, 3, 6, '4', None):
                with self.subTest(module=module.__name__, version=version), self.assertRaises(ValueError):
                    module.validate_pair(self.schema(self.pair(module), version))

    def test_mixed_trial_versions_are_refused_within_each_pair(self):
        for module in (profile, exit_series):
            pair = self.pair(module)
            pair['samples'][0]['trial']['soak']['catalog_schema_version'] = 4
            with self.assertRaises(ValueError): module.validate_pair(pair)

    def test_profile_archive_cross_platform_uniformity_and_live_aggregate_refusal(self):
        grid = [self.pair(profile, index, platform) for platform in profile.PLATFORMS for index in range(1, 5)]
        result = profile.aggregate(grid, count=64, page_size=16)
        self.assertEqual(result['status'], 'complete')
        archive = copy.deepcopy(result)
        for pair in archive['pairs']: self.schema(pair, 4)
        profile.validate_series(archive)
        mixed = copy.deepcopy(archive)
        for pair in mixed['pairs']:
            if pair['runtime']['platform'] == 'Windows': self.schema(pair, 5)
        with self.assertRaises(ValueError): profile.validate_series(mixed)
        current = profile.aggregate(archive['pairs'], count=64, page_size=16)
        self.assertEqual(current['status'], 'incomplete')
        self.assertEqual(current['pairs'], [])
        self.assertIn('incomparable', {item['code'] for item in current['issues']})

    def test_exit_archive_series_uniformity_and_current_series_producer_refusal(self):
        # Check each host contract locally as well as in the hosted OS matrix.
        # Synthetic children must match their parent's runtime before exercising
        # the schema gate; the explicit cross-platform archive grid stays separate.
        for platform in profile.PLATFORMS:
            runtime = dict(self.runtime, platform=platform)
            with self.subTest(platform=platform), patch.object(self, 'runtime', runtime), \
                    patch.object(profile, 'runtime_metadata', return_value=runtime):
                self.check_exit_archive_series_and_producer()

    def check_exit_archive_series_and_producer(self):
        pairs = [self.schema(self.pair(exit_series, index), 4) for index in range(1, 5)]
        archive = {'schema': exit_series.SERIES_SCHEMA, 'status': 'complete',
                   'identity': self.exit_identity, 'code': self.exit_code, 'runtime': self.runtime,
                   'configuration': {'count': 64, 'page_size': 16, 'pairs': 4},
                   'pairs': pairs, 'issues': [], 'note': exit_series.NOTE,
                   'attribution': exit_series._attribution(pairs)}
        exit_series.validate_series(archive)
        self.schema(pairs[2], 5)
        with self.assertRaises(ValueError): exit_series.validate_series(archive)
        with patch.object(exit_series, 'run_pair', return_value=self.schema(self.pair(exit_series), 4)):
            result = exit_series.run_series(64, 16, session_token='a' * 32)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['pairs'], [])
        self.assertIn('incomparable', {item['code'] for item in result['issues']})

    def test_current_trial_producers_reject_old_schema_from_measurement_adapter(self):
        for module, adapter in ((profile, profile.profile), (exit_series, exit_series.probe)):
            trial = self.schema(self.pair(module), 4)['samples'][0]['trial']
            measured = {key: trial[key] for key in ('soak', 'phases')}
            with patch.object(adapter, 'run_trial', return_value=measured), self.assertRaises(ValueError):
                if module is profile: module.run_trial(64, 16, 'baseline')
                else: module.run_trial(64, 16, 'baseline', session_token='a' * 32)

    def test_current_pair_producers_reject_old_schema_children(self):
        for platform in profile.PLATFORMS:
            runtime = dict(self.runtime, platform=platform)
            with self.subTest(platform=platform), patch.object(self, 'runtime', runtime), \
                    patch.object(profile, 'runtime_metadata', return_value=runtime):
                self.check_current_pair_producers()

    def check_current_pair_producers(self):
        for module in (profile, exit_series):
            trial = self.schema(self.pair(module), 4)['samples'][0]['trial']
            with patch.object(module, '_run_child', return_value=(trial, None, True)):
                if module is profile: result = module.run_pair(64, 16)
                else: result = module.run_pair(64, 16, session_token='a' * 32)
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['samples'], [])
            self.assertIn('incomparable', {item['code'] for item in result['issues']})

    def test_all_retained_public_reports_validate_without_rewriting_bytes_or_digests(self):
        root = Path(__file__).resolve().parents[1]
        scanned = 0
        for directory, module in (('benchmarks/source-scan-results', profile),
                                  ('docs/transaction-exit-benchmark-results', exit_series),
                                  ('docs/transaction-exit-benchmark-history', exit_series)):
            for path in sorted((root / directory).rglob('*.json')):
                original = path.read_bytes()
                value = json.loads(original)
                if value.get('schema') not in (module.TRIAL_SCHEMA, module.PAIR_SCHEMA, module.SERIES_SCHEMA):
                    continue
                digest = hashlib.sha256(original).hexdigest()
                module.validate_public_report(value)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
                scanned += 1
        self.assertGreater(scanned, 10)


if __name__ == '__main__':
    unittest.main()
