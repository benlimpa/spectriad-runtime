"""Replay end to end against the fixture bundle unit with the stub
subject compiler (no real compiler, no network)."""

import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from spectriad_runtime import bundle, replay
from spectriad_runtime.cli import main as cli_main

FIXTURE_UNIT = Path(__file__).parent / "fixtures" / "units" / "fixture-identity"
STUB = Path(__file__).parent / "stub_opt.py"


def _configure_stub(mode: str | None = None):
    os.environ["SPECTRIAD_FIXTURE_OPT"] = " ".join(
        shlex.quote(p) for p in (sys.executable, str(STUB))
    )
    if mode is None:
        os.environ.pop("STUB_OPT_MODE", None)
    else:
        os.environ["STUB_OPT_MODE"] = mode


class ReplayTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SPECTRIAD_FIXTURE_OPT", None)
        os.environ.pop("STUB_OPT_MODE", None)

    def test_clean_replay(self):
        _configure_stub()
        report = replay.replay_unit(FIXTURE_UNIT)
        self.assertTrue(report["spec_hash_ok"])
        self.assertEqual(report["seeds"]["hash_matched"], 4)
        self.assertEqual(report["seeds"]["hash_mismatched"], 0)
        self.assertEqual(report["executed"], 4)
        self.assertEqual(report["acceptance"]["agree"], 4)
        self.assertEqual(report["verdict_sets"]["docs/O1"], {"PASS": 4})
        self.assertEqual(report["verdict_sets"]["docs/O2"], {"PASS": 4})
        self.assertEqual(report["exit_code"], 0)

    def test_unconfigured_runner_is_infrastructure_not_pass(self):
        report = replay.replay_unit(FIXTURE_UNIT)
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["verdict_sets"], {})
        self.assertEqual(report["seeds"]["hash_matched"], 4)
        self.assertEqual(report["exit_code"], 3)
        self.assertIn("not-configured", report["runner"])

    def test_defect_surfaces_as_fail(self):
        _configure_stub("drop-arith")
        report = replay.replay_unit(FIXTURE_UNIT)
        self.assertEqual(report["executed"], 4)
        self.assertIn("FAIL", report["verdict_sets"]["docs/O1"])
        self.assertEqual(report["exit_code"], 4)

    def test_rejection_is_acceptance_drift(self):
        _configure_stub("reject")
        report = replay.replay_unit(FIXTURE_UNIT)
        self.assertEqual(report["acceptance"]["agree"], 0)
        self.assertEqual(len(report["acceptance"]["disagree"]), 4)
        self.assertEqual(report["exit_code"], 4)

    def test_hash_mismatch_fails_loudly(self):
        _configure_stub()
        with tempfile.TemporaryDirectory() as td:
            unit = Path(td) / "fixture-identity"
            shutil.copytree(FIXTURE_UNIT, unit)
            corpus_path = unit / "seeds" / "corpus.json"
            corpus = json.loads(corpus_path.read_text())
            corpus["records"][0]["input_sha"] = "000000000000"
            corpus_path.write_text(json.dumps(corpus))
            report = replay.replay_unit(unit)
        self.assertEqual(report["seeds"]["hash_mismatched"], 1)
        self.assertEqual(report["exit_code"], 2)
        # The tampered seed's input is never executed or checked.
        self.assertEqual(report["executed"], 3)

    def test_spec_drift_refused(self):
        with tempfile.TemporaryDirectory() as td:
            unit = Path(td) / "fixture-identity"
            shutil.copytree(FIXTURE_UNIT, unit)
            g = unit / "spec" / "docs.pg"
            g.write_text(g.read_text() + "// drifted\n")
            with self.assertRaises(bundle.BundleError):
                replay.replay_unit(unit)

    def test_cli_end_to_end(self):
        _configure_stub()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "report.json"
            code = cli_main(
                ["replay", str(FIXTURE_UNIT), "--quiet", "--json", str(out)]
            )
            self.assertEqual(code, 0)
            report = json.loads(out.read_text())
        self.assertEqual(report["unit"], "fixture-identity")
        self.assertEqual(report["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
