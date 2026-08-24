"""Replay and generate over a spec-only (schema 2) bundle unit with the
stub subject compiler (no real compiler, no network).

The fixture has two generators, `I1` and `baseline`. OC1 is checked on
the baseline population (its statement names no generator), OC2 and OC3
are scoped to I1. Sorted, the streams are ["I1", "baseline"], so seed
`s` draws from `streams[s % 2]`.
"""

import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from spectriad_runtime import bundle, generate, replay

FIXTURE_UNIT = Path(__file__).parent / "fixtures" / "units" / "fixture-spec-only"
STUB = Path(__file__).parent / "stub_opt.py"


def configure_stub(mode: str | None = None):
    os.environ["SPECTRIAD_FIXTURE_OPT"] = " ".join(
        shlex.quote(p) for p in (sys.executable, str(STUB))
    )
    if mode is None:
        os.environ.pop("STUB_OPT_MODE", None)
    else:
        os.environ["STUB_OPT_MODE"] = mode


def clear_stub():
    os.environ.pop("SPECTRIAD_FIXTURE_OPT", None)
    os.environ.pop("STUB_OPT_MODE", None)


def empty_corpus_copy(dest: Path) -> Path:
    """The fixture unit with an honestly empty seed corpus."""
    shutil.copytree(FIXTURE_UNIT, dest)
    corpus = json.loads((dest / "seeds" / "corpus.json").read_text())
    corpus["records"] = []
    (dest / "seeds" / "corpus.json").write_text(json.dumps(corpus))
    return dest


class SpecOnlyLoadTest(unittest.TestCase):
    def test_composition_puts_the_generator_first(self):
        unit = bundle.load_unit(FIXTURE_UNIT)
        self.assertEqual(unit["schema"], 2)
        self.assertEqual(sorted(unit["generators"]), ["I1", "baseline"])
        composed = bundle.statement_grammar_text(unit, "I1")
        # The start rule must come from the generator, not the base:
        # a compiled generator roots at the first nonterminal it sees.
        self.assertLess(composed.index("start:"), composed.index("sig:"))
        self.assertEqual(
            bundle.constraint_generators(unit),
            {"OC1": ["baseline"], "OC2": ["I1"], "OC3": ["I1"]},
        )

    def test_no_generators_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            unit = Path(td) / "fixture-spec-only"
            shutil.copytree(FIXTURE_UNIT, unit)
            shutil.rmtree(unit / "spec" / "gen")
            with self.assertRaises(bundle.BundleError):
                bundle.load_unit(unit)


class SpecOnlyReplayTest(unittest.TestCase):
    def tearDown(self):
        clear_stub()

    def test_replay_scopes_constraints_to_their_generator(self):
        configure_stub()
        report = replay.replay_unit(FIXTURE_UNIT)
        self.assertTrue(report["spec_hash_ok"])
        self.assertEqual(report["executed"], 4)
        # Bare constraint ids, no source prefix. The corpus draws two
        # seeds from each generator, and a constraint is counted only on
        # the population its statement scopes it to.
        self.assertEqual(
            report["verdict_sets"],
            {"OC1": {"PASS": 2}, "OC2": {"PASS": 2}, "OC3": {"PASS": 2}},
        )
        self.assertEqual(report["exit_code"], 0)

    def test_empty_corpus_is_not_a_clean_replay(self):
        configure_stub()
        with tempfile.TemporaryDirectory() as td:
            report = replay.replay_unit(empty_corpus_copy(Path(td) / "u"))
        self.assertTrue(report["corpus_empty"])
        self.assertEqual(report["exit_code"], 5)
        self.assertIn("generate", replay.format_report(report))


class SpecOnlyGenerateTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.out = Path(self._td.name) / "out"

    def tearDown(self):
        clear_stub()
        self._td.cleanup()

    def test_generate_round_robins_generators_and_scopes_constraints(self):
        configure_stub()
        report = generate.generate_unit(FIXTURE_UNIT, seeds=6, out_dir=self.out)
        self.assertEqual(report["generated"], 6)
        self.assertEqual(report["executed"], 6)
        # Seeds 0..5 alternate I1 / baseline, three each.
        self.assertEqual(
            report["verdict_sets"],
            {"OC1": {"PASS": 3}, "OC2": {"PASS": 3}, "OC3": {"PASS": 3}},
        )
        self.assertEqual(report["exit_code"], 0)

    def test_defect_surfaces_under_bare_constraint_ids(self):
        configure_stub("drop-arith")
        report = generate.generate_unit(FIXTURE_UNIT, seeds=4, out_dir=self.out)
        self.assertEqual(report["exit_code"], 4)
        self.assertIn("FAIL", report["verdict_sets"]["OC1"])
        self.assertIn("FAIL", report["verdict_sets"]["OC2"])
        finding = sorted((self.out / "findings").iterdir())[0]
        meta = json.loads((finding / "meta.json").read_text())
        # The preserved meta keeps its "source" key; in a spec-only unit
        # it carries the generator id, as the corpus does.
        self.assertIn(meta["source"], ("I1", "baseline"))


if __name__ == "__main__":
    unittest.main()
