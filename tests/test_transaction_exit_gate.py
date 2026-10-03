"""Actual Git graph proofs for the conservative publication decision."""
import copy
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import transaction_exit_gate as gate


def git(root, *args, input_text=None):
    return subprocess.check_output(["git", *args], cwd=root,
        input=input_text.encode() if input_text is not None else None,
        stderr=subprocess.DEVNULL).decode().strip()


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "Fictional")
        git(self.root, "config", "user.email", "fictional@example.invalid")
        (self.root / "protected.py").write_text("frozen\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "guide.md").write_text("experiment\n")
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "measured head")
        self.before = git(self.root, "rev-parse", "HEAD")
        self.measured_merge = self.make_merge(self.before)
        (self.root / "docs" / "guide.md").write_text("experiment and raw evidence\n")
        git(self.root, "commit", "-qam", "docs only")
        self.after = git(self.root, "rev-parse", "HEAD")
        self.merge = self.make_merge(self.after)
        git(self.root, "checkout", "-q", "--detach", self.merge)
        digest = hashlib.sha256(b"frozen\n").hexdigest()
        self.report = {"schema": gate.series.SERIES_SCHEMA, "status": "complete",
            "identity": {"run_id": "123", "job_id": "windows-series",
                         "head_sha": self.before},
            "runtime": {"platform": "Windows", "host_kind": "github-hosted"},
            "configuration": {"count": 2048, "page_size": 256, "pairs": 4},
            "code": {"revision": self.measured_merge, "dirty": False,
                     "digests": {"protected.py": digest}}}
        self.event = {"action": "synchronize", "before": self.before,
            "after": self.after, "pull_request": {
                "base": {"sha": self.base}, "head": {"sha": self.after}}}
        self.environment = {"GITHUB_EVENT_NAME": "pull_request",
                            "GITHUB_RUN_ATTEMPT": "1"}
        p1 = patch.object(gate, "PROTECTED_FILES", ("protected.py",))
        p2 = patch.object(gate.series, "validate_public_report", return_value=None)
        p1.start(); p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def make_merge(self, head):
        tree = git(self.root, "rev-parse", f"{head}^{{tree}}")
        return git(self.root, "commit-tree", tree, "-p", self.base, "-p", head,
                   input_text="synthetic merge\n")

    def decide(self, event=None, report=None, merge=None, environment=None):
        return gate.decision(self.event if event is None else event,
            self.report if report is None else report,
            self.merge if merge is None else merge, repo=self.root,
            environment=self.environment if environment is None else environment)

    def test_only_proven_attempt_one_docs_delta_skips(self):
        self.assertEqual(self.decide(), (False, "verified_docs_only_evidence"))
        self.assertEqual(self.decide(environment={**self.environment,
            "GITHUB_RUN_ATTEMPT": "2"})[0], True)
        self.assertEqual(self.decide(event={**self.event,
            "action": "opened"})[0], True)
        self.assertEqual(self.decide(report={})[0], True)
        wrong = copy.deepcopy(self.report)
        wrong["identity"]["head_sha"] = self.base
        # The old base is an ancestor, but the protected file did not exist at
        # the wrong identity's measured point only if its bytes differ. Force
        # that mismatch explicitly rather than relying on a malformed SHA.
        wrong["code"]["digests"]["protected.py"] = "0" * 64
        self.assertEqual(self.decide(report=wrong)[0], True)
        wrong_job = copy.deepcopy(self.report)
        wrong_job["identity"]["job_id"] = "other-job"
        self.assertEqual(self.decide(report=wrong_job)[1], "evidence_mismatch")
        self.assertEqual(self.decide(merge=self.after)[1], "invalid_checkout")
        same_merge = copy.deepcopy(self.report)
        same_merge["code"]["revision"] = self.merge
        self.assertEqual(self.decide(report=same_merge)[1], "evidence_revision")
        wrong_measured_merge = copy.deepcopy(self.report)
        tree = git(self.root, "rev-parse", f"{self.before}^{{tree}}")
        wrong_measured_merge["code"]["revision"] = git(self.root, "commit-tree", tree,
            "-p", self.before, "-p", self.base, input_text="wrong old merge\n")
        self.assertEqual(self.decide(report=wrong_measured_merge)[1], "evidence_revision")

    def test_changed_code_and_invalid_merge_parent_force_measurement(self):
        git(self.root, "checkout", "-q", self.after)
        (self.root / "protected.py").write_text("changed\n")
        git(self.root, "commit", "-qam", "changed protected input")
        changed_head = git(self.root, "rev-parse", "HEAD")
        changed_merge = self.make_merge(changed_head)
        git(self.root, "checkout", "-q", "--detach", changed_merge)
        changed_event = copy.deepcopy(self.event)
        changed_event["after"] = changed_head
        changed_event["pull_request"]["head"]["sha"] = changed_head
        self.assertEqual(self.decide(event=changed_event, merge=changed_merge)[1],
                         "changed_inputs")
        # A commit with the wrong first parent is not the PR merge proof.
        tree = git(self.root, "rev-parse", f"{changed_head}^{{tree}}")
        wrong_merge = git(self.root, "commit-tree", tree, "-p", self.before,
                          "-p", changed_head, input_text="wrong merge\n")
        git(self.root, "checkout", "-q", "--detach", wrong_merge)
        self.assertEqual(self.decide(event=changed_event, merge=wrong_merge)[1],
                         "merge_proof_failed")

    def test_missing_and_duplicate_archive_fail_closed_in_no_argument_cli(self):
        event_file = self.root / "event.json"
        event_file.write_text(json.dumps(self.event))
        output_file = self.root / "github-output.txt"
        environment = {**self.environment, "GITHUB_EVENT_PATH": str(event_file),
                       "GITHUB_SHA": self.merge,
                       "GITHUB_OUTPUT": str(output_file)}
        with patch.dict(os.environ, environment):
            with patch.object(gate, "ROOT", self.root):
                stdout = StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(gate.main([]), 0)
        self.assertEqual(json.loads(stdout.getvalue()),
                         {"measure": True, "reason": "missing_evidence"})
        self.assertIn("measure=true", output_file.read_text())

        archive = self.root / gate.EVIDENCE_PREFIX / "series.json"
        archive.parent.mkdir(parents=True)
        archive.write_text('{"schema":"a","schema":"b"}')
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "malformed archive")
        self.assertIsNone(gate._load_evidence(self.root,
            gate.EVIDENCE_PREFIX + "series.json"))


if __name__ == "__main__":
    unittest.main()
