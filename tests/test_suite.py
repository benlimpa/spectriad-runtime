"""The `suite` mode over a fake bundle checkout: discovery, per-unit
mode selection, and the drift-expectation policy."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from spectriad_runtime import suite
from spectriad_runtime.cli import main as cli_main
from test_spec_only import (
    FIXTURE_UNIT,
    clear_stub,
    configure_stub,
    empty_corpus_copy,
)


class SuiteTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "bundle"
        self.out = Path(self._td.name) / "out"
        units = self.root / "units"
        units.mkdir(parents=True)
        self._unit(units / "seeded")
        self._unit(empty_corpus_copy(units / "empty"))

    def tearDown(self):
        clear_stub()
        self._td.cleanup()

    def _unit(self, dest: Path) -> Path:
        """One bundle unit named after its directory, so the two copies of
        the fixture are distinguishable in the report."""
        if not dest.exists():
            shutil.copytree(FIXTURE_UNIT, dest)
        manifest_path = dest / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["unit"] = dest.name
        manifest_path.write_text(json.dumps(manifest))
        return dest

    def _suite(self, **kwargs):
        kwargs.setdefault("out_dir", self.out)
        kwargs.setdefault("generate_seeds", 2)
        return suite.run_suite(self.root, **kwargs)

    def test_auto_replays_a_seeded_unit_and_generates_over_an_empty_one(self):
        configure_stub()
        report = self._suite()
        modes = {r["unit"]: r["mode"] for r in report["units"]}
        self.assertEqual(modes, {"empty": "generate", "seeded": "replay"})
        self.assertEqual({r["status"] for r in report["units"]}, {"CLEAN"})
        self.assertEqual(report["exit_code"], 0)
        on_disk = json.loads((self.out / "suite-report.json").read_text())
        self.assertEqual(on_disk["summary"]["units"], 2)

    def test_forced_replay_reports_an_empty_corpus_rather_than_covering_for_it(self):
        configure_stub()
        report = self._suite(mode="replay")
        rows = {r["unit"]: r for r in report["units"]}
        self.assertEqual(rows["empty"]["status"], "NO-SEEDS")
        self.assertEqual(rows["empty"]["exit_code"], 5)
        self.assertEqual(rows["seeded"]["mode"], "replay")
        self.assertEqual(report["exit_code"], 5)

    def test_forced_generate_runs_fresh_inputs_on_every_unit(self):
        configure_stub()
        report = self._suite(mode="generate")
        self.assertEqual({r["mode"] for r in report["units"]}, {"generate"})
        self.assertEqual({r["seeds"] for r in report["units"]}, {2})
        self.assertEqual(report["exit_code"], 0)

    def test_known_drift_is_quiet_and_unexpected_clean_is_flagged(self):
        expectations = self.root / "expectations.json"
        expectations.write_text(json.dumps({
            "seeded": {"status": "known-drift", "note": "fixture drift"},
        }))
        configure_stub("drop-arith")
        drifting = self._suite()
        rows = {r["unit"]: r for r in drifting["units"]}
        self.assertEqual(rows["seeded"]["status"], "KNOWN-DRIFT")
        self.assertEqual(rows["seeded"]["effective_exit_code"], 0)
        self.assertEqual(rows["empty"]["status"], "DRIFT")
        self.assertEqual(drifting["exit_code"], 4)

        configure_stub()
        clean = self._suite()
        rows = {r["unit"]: r for r in clean["units"]}
        self.assertEqual(rows["seeded"]["status"], "UNEXPECTED-CLEAN")
        self.assertEqual(rows["seeded"]["effective_exit_code"], 4)
        self.assertEqual(clean["exit_code"], 4)
        self.assertIn("recheck the spec", suite.format_report(clean))

    def test_a_broken_unit_does_not_take_the_bundle_with_it(self):
        configure_stub()
        broken = self.root / "units" / "broken"
        self._unit(broken)
        (broken / "spec" / "base.pg").write_text("// drifted\n")
        report = self._suite()
        rows = {r["unit"]: r for r in report["units"]}
        self.assertEqual(rows["broken"]["status"], "BROKEN")
        self.assertEqual(rows["seeded"]["status"], "CLEAN")
        self.assertEqual(report["exit_code"], 2)

    def test_no_units_discovered_is_never_a_clean_zero(self):
        with tempfile.TemporaryDirectory() as td:
            code = cli_main(["suite", td, "--quiet", "--out", str(self.out)])
        self.assertEqual(code, 1)

    def test_cli_end_to_end(self):
        configure_stub()
        json_out = Path(self._td.name) / "suite.json"
        code = cli_main([
            "suite", str(self.root), "--quiet", "--generate-seeds", "2",
            "--out", str(self.out), "--json", str(json_out),
        ])
        self.assertEqual(code, 0)
        report = json.loads(json_out.read_text())
        self.assertEqual(report["summary"]["by_status"], {"CLEAN": 2})


if __name__ == "__main__":
    unittest.main()
