"""Checker tests on a canned MLIR pair (a real raising-pass input and
its recorded head output, copied from the internal corpus)."""

import unittest
from pathlib import Path

from spectriad_runtime.checker.ptc import check_constraint

PAIR = Path(__file__).parent / "fixtures" / "pair"
IN_TEXT = (PAIR / "while-to-for.in.mlir").read_text()
OUT_TEXT = (PAIR / "while-to-for.head.mlir").read_text()


def c(rule, **kw):
    return {"id": "T", "trigger": '{id="out"}', "rule": rule, **kw}


class CheckerTest(unittest.TestCase):
    def test_op_mapped_passes_on_recorded_pair(self):
        v = check_constraint(
            c('op_mapped("scf.while", "scf.while|scf.for")'), IN_TEXT, OUT_TEXT
        )
        self.assertEqual(v.status, "PASS", v.detail)

    def test_memory_ops_preserved(self):
        v = check_constraint(
            c('ops_preserved("memref.*")'), IN_TEXT, OUT_TEXT
        )
        self.assertEqual(v.status, "PASS", v.detail)

    def test_violation_reported_as_fail(self):
        # The recorded output still contains an scf.for, so claiming
        # there are no loop ops at all must FAIL, not error out.
        v = check_constraint(
            c('no_ops("out", "scf.for|scf.while")'), IN_TEXT, OUT_TEXT
        )
        self.assertEqual(v.status, "FAIL", v.detail)

    def test_unknown_feature_is_error_not_pass(self):
        v = check_constraint(
            c('definitely_not_a_feature("x")'), IN_TEXT, OUT_TEXT
        )
        self.assertEqual(v.status, "ERROR")

    def test_adhoc_predicate_runs_in_sandbox(self):
        v = check_constraint(
            c(
                'adhoc("counts")',
                check_kind="python",
                check_code=(
                    "def check(inp, out, lib):\n"
                    "    n = len([op for op in out.ops if op.name == 'func.func'])\n"
                    "    return (n >= 1, 'saw %d funcs' % n, [])\n"
                ),
            ),
            IN_TEXT,
            OUT_TEXT,
        )
        self.assertEqual(v.status, "PASS", v.detail)

    def test_adhoc_none_is_abstain(self):
        v = check_constraint(
            c(
                'adhoc("decline")',
                check_kind="python",
                check_code=(
                    "def check(inp, out, lib):\n"
                    "    return (None, 'outside this source space', [])\n"
                ),
            ),
            IN_TEXT,
            OUT_TEXT,
        )
        self.assertEqual(v.status, "ABSTAIN", v.detail)


if __name__ == "__main__":
    unittest.main()
