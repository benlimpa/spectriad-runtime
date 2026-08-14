"""Generate mode end to end against the fixture bundle unit with the
stub subject compiler (no real compiler, no network)."""

import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from spectriad_runtime import generate
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


class GenerateTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name) / "out"

    def tearDown(self):
        os.environ.pop("SPECTRIAD_FIXTURE_OPT", None)
        os.environ.pop("STUB_OPT_MODE", None)
        self._td.cleanup()

    def _generate(self, **kwargs):
        kwargs.setdefault("out_dir", self.out)
        return generate.generate_unit(FIXTURE_UNIT, **kwargs)

    def test_clean_generate(self):
        _configure_stub()
        report = self._generate(seeds=6, seed_base=100)
        self.assertEqual(report["generated"], 6)
        self.assertEqual(report["executed"], 6)
        self.assertEqual(report["rejection_count"], 0)
        self.assertEqual(report["verdict_sets"]["docs/O1"], {"PASS": 6})
        self.assertEqual(report["verdict_sets"]["docs/O2"], {"PASS": 6})
        self.assertEqual(report["findings_preserved"], 0)
        self.assertEqual(report["exit_code"], 0)
        # Nothing clean is preserved; the report always is.
        self.assertEqual(list((self.out / "findings").iterdir()), [])
        on_disk = json.loads((self.out / "report.json").read_text())
        self.assertEqual(on_disk["exit_code"], 0)

    def test_unconfigured_runner_is_infrastructure_not_pass(self):
        report = self._generate(seeds=3)
        self.assertEqual(report["generated"], 3)
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["verdict_sets"], {})
        self.assertEqual(report["exit_code"], 3)
        self.assertIn("not-configured", report["runner"])

    def test_defect_is_preserved_and_fails(self):
        _configure_stub("drop-arith")
        report = self._generate(seeds=4, seed_base=100)
        self.assertEqual(report["exit_code"], 4)
        self.assertIn("FAIL", report["verdict_sets"]["docs/O1"])
        self.assertGreater(report["findings_preserved"], 0)
        finding = sorted((self.out / "findings").iterdir())[0]
        meta = json.loads((finding / "meta.json").read_text())
        self.assertEqual(meta["kind"], "constraint_failure")
        self.assertTrue((finding / "input.mlir").is_file())
        self.assertTrue((finding / "output.mlir").is_file())
        verdicts = json.loads((finding / "verdicts.json").read_text())
        self.assertEqual(verdicts["docs/O1"]["status"], "FAIL")

    def test_rejection_is_behavioral_and_preserved(self):
        _configure_stub("reject")
        report = self._generate(seeds=2, seed_base=100)
        self.assertEqual(report["exit_code"], 4)
        self.assertEqual(report["rejection_count"], 2)
        self.assertEqual(report["findings_preserved"], 2)
        finding = sorted((self.out / "findings").iterdir())[0]
        meta = json.loads((finding / "meta.json").read_text())
        self.assertEqual(meta["kind"], "rejection")
        self.assertTrue((finding / "input.mlir").is_file())
        self.assertIn(
            "rejecting", (finding / "diagnostics.txt").read_text()
        )

    def test_deterministic_from_seed_base(self):
        _configure_stub("drop-arith")
        first = self._generate(seeds=3, seed_base=42, out_dir=self.out / "a")
        second = self._generate(seeds=3, seed_base=42, out_dir=self.out / "b")
        self.assertEqual(first["exit_code"], second["exit_code"])
        a = sorted(p.name for p in (self.out / "a" / "findings").iterdir())
        b = sorted(p.name for p in (self.out / "b" / "findings").iterdir())
        self.assertEqual(a, b)
        for name in a:
            self.assertEqual(
                (self.out / "a" / "findings" / name / "input.mlir").read_bytes(),
                (self.out / "b" / "findings" / name / "input.mlir").read_bytes(),
            )

    def test_zero_duration_budget_never_executes(self):
        _configure_stub()
        report = self._generate(duration=0.0)
        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["exit_code"], 3)

    def test_budget_is_required(self):
        with self.assertRaises(ValueError):
            self._generate()

    def test_cli_end_to_end(self):
        _configure_stub()
        json_out = self.out / "report.json.copy"
        code = cli_main(
            [
                "generate", str(FIXTURE_UNIT), "--seeds", "2",
                "--seed-base", "7", "--out", str(self.out), "--quiet",
                "--json", str(json_out),
            ]
        )
        self.assertEqual(code, 0)
        report = json.loads(json_out.read_text())
        self.assertEqual(report["unit"], "fixture-identity")
        self.assertEqual(report["budget"]["seed_base"], 7)

    def test_cli_requires_a_budget(self):
        code = cli_main(["generate", str(FIXTURE_UNIT), "--quiet"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
