"""Sandboxed execution of agent-written ad-hoc predicates.

A constraint may carry `check_kind: python` with a `check_code:` body
defining `check(inp, out, lib)` over the shared xdsl AST
(checker/ast.py) plus the generic feature library (checker/features)
— generated code never parses text itself. The rule text references
it as `adhoc("<name>")`.

Isolation: the code runs in a SUBPROCESS with a wall-clock timeout
and a restricted builtin set (no import machinery, no file/net/os
access; re/math/itertools/collections are pre-imported). This guards
against accidents and keeps a misbehaving predicate from taking the
server down; it is not a security boundary against a determined
adversary — live-generated predicates only run when an LLM backend
is deliberately enabled (same posture as the deriver allowlist).

check() may return bool, (bool, note) or (bool, note, blame_lines).

Branch coverage: run(..., coverage=True) also reports which decision
branches of the predicate body were exercised. A branch is one side
of a decision. The SAME transformer walk (_instrument_tree) drives
both known_branches (static enumeration) and the child-side runtime
instrumentation, so their branch ids can never disagree.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys

TIMEOUT_S = 20

_SAFE_BUILTINS = (
    "abs all any bool dict divmod enumerate filter float frozenset int "
    "isinstance issubclass len list map max min next range repr reversed "
    "round set sorted str sum tuple zip print True False None "
    "ValueError TypeError KeyError IndexError AttributeError StopIteration "
    "Exception"
).split()

# Injected recorder names; dunder-ish and collision-proof against the
# predicate namespace. Harness code, not sandboxed predicate code.
_BRANCH_FN = "__spec_branch__"
_EVAL_FN = "__spec_eval__"


def _mk_call(fname: str, bid: str, expr: ast.expr) -> ast.Call:
    """`fname("<bid>", expr)` — records and returns expr unchanged."""
    call = ast.Call(
        func=ast.Name(id=fname, ctx=ast.Load()),
        args=[ast.Constant(value=bid), expr],
        keywords=[],
    )
    return ast.copy_location(call, expr)


class _BranchInstrumenter(ast.NodeTransformer):
    """Wraps each decision so coverage is recorded, and collects the
    branch ids in the same pass. A branch id embeds the deciding
    expression's lineno.col_offset (relative to check_code) so
    same-line constructs stay distinct.

    - If/While/IfExp test        -> "<kind>@L.C:T" / ":F"
    - comprehension `if` cond     -> "compif@L.C:T" / ":F"
    - BoolOp operand i            -> "bool@L.C.i" (covered == evaluated;
      an unevaluated short-circuit operand is an uncovered branch)
    """

    def __init__(self) -> None:
        self.branches: list[str] = []

    def _wrap_test(self, kind: str, test: ast.expr) -> ast.expr:
        bid = "%s@%d.%d" % (kind, test.lineno, test.col_offset)
        self.branches.append(bid + ":T")
        self.branches.append(bid + ":F")
        return _mk_call(_BRANCH_FN, bid, test)

    def visit_If(self, node: ast.If) -> ast.AST:
        self.generic_visit(node)
        node.test = self._wrap_test("if", node.test)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        self.generic_visit(node)
        node.test = self._wrap_test("while", node.test)
        return node

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        self.generic_visit(node)
        node.test = self._wrap_test("ifexp", node.test)
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        wrapped = []
        for i, operand in enumerate(node.values):
            bid = "bool@%d.%d.%d" % (node.lineno, node.col_offset, i)
            self.branches.append(bid)
            wrapped.append(_mk_call(_EVAL_FN, bid, operand))
        node.values = wrapped
        return node

    def visit_comprehension(self, node: ast.comprehension) -> ast.AST:
        self.generic_visit(node)
        node.ifs = [self._wrap_comp_if(cond) for cond in node.ifs]
        return node

    def _wrap_comp_if(self, cond: ast.expr) -> ast.expr:
        bid = "compif@%d.%d" % (cond.lineno, cond.col_offset)
        self.branches.append(bid + ":T")
        self.branches.append(bid + ":F")
        return _mk_call(_BRANCH_FN, bid, cond)


def _instrument_tree(code: str) -> tuple[ast.Module, list[str]]:
    """Parse and transform code. Returns (instrumented tree, sorted
    branch ids). Raises on parse errors; callers decide the fallback.
    Shared by known_branches and the child instrumentation."""
    tree = ast.parse(code)
    inst = _BranchInstrumenter()
    tree = inst.visit(tree)
    ast.fix_missing_locations(tree)
    return tree, sorted(set(inst.branches))


def known_branches(code: str) -> list[str]:
    """Statically enumerate every branch id in the predicate source.
    Deterministic and sorted; [] when the source does not parse."""
    try:
        _, ids = _instrument_tree(code)
    except Exception:
        return []
    return ids


_CHILD = r"""
import json, sys, builtins

payload = json.load(sys.stdin)
from spectriad_runtime.checker import ast as ast_mod
from spectriad_runtime.checker import features as lib
from spectriad_runtime.checker import adhoc as adhoc_mod

pair = ast_mod.parse_pair(payload["input"], payload["output"])

import re, math, itertools, collections
from collections import Counter

safe = {name: getattr(builtins, name) for name in %(names)r}
env = {
    "__builtins__": safe,
    "re": re, "math": math, "itertools": itertools,
    "collections": collections, "Counter": Counter,
    "lib": lib,
}

# Coverage: instrument in-child with the SAME transformer known_branches
# uses. Recorder helpers are harness code (not under the restricted
# builtins), injected into env. On any instrumentation failure fall back
# to the original code with taken=[] — coverage must never break checks.
coverage = bool(payload.get("coverage"))
compiled = None
taken = None
if coverage:
    try:
        tree, _ = adhoc_mod._instrument_tree(payload["code"])
        compiled = compile(tree, "<check_code>", "exec")
        taken = set()
        def %(branch_fn)s(bid, val, _t=taken):
            _t.add(bid + (":T" if val else ":F"))
            return val
        def %(eval_fn)s(bid, val, _t=taken):
            _t.add(bid)
            return val
        env["%(branch_fn)s"] = %(branch_fn)s
        env["%(eval_fn)s"] = %(eval_fn)s
    except Exception:
        compiled = None
        taken = []
if compiled is None:
    compiled = compile(payload["code"], "<check_code>", "exec")

try:
    exec(compiled, env)
    fn = env.get("check")
    if not callable(fn):
        raise ValueError("check_code must define check(inp, out, lib)")
    res = fn(pair.input, pair.output, lib)
except Exception:
    import traceback
    print(json.dumps({"error": traceback.format_exc(limit=6)}))
    sys.exit(0)

if isinstance(res, tuple):
    ok, note, lines = (list(res) + ["", []])[:3]
else:
    ok, note, lines = res, "", []
out = {
    # None is the abstain signal: the predicate declines to assert on
    # this pair. Distinct from True, which claims the pair conforms.
    "ok": None if ok is None else bool(ok),
    "note": str(note)[:500],
    "lines": [int(l) for l in (lines or [])][:50],
}
if coverage:
    out["taken"] = sorted(taken) if taken else []
print(json.dumps(out))
""" % {
    "names": _SAFE_BUILTINS,
    "branch_fn": _BRANCH_FN,
    "eval_fn": _EVAL_FN,
}


class AdhocError(Exception):
    """Predicate failed to run (syntax error, exception, timeout);
    the message carries the traceback for repair-loop feedback."""


def validate_source(code: str) -> None:
    """Validate the predicate contract without giving it an observed pair.

    The output-blind intent phase uses this check before execution is
    unlocked. Full workspace validation still calls ``run`` afterwards,
    so this deliberately checks only syntax and the required function
    signature rather than pretending to prove runtime correctness.
    """
    try:
        tree = ast.parse(code)
        compile(tree, "<check_code>", "exec")
    except (SyntaxError, ValueError, TypeError) as e:
        raise AdhocError(f"ad-hoc predicate source is invalid: {e}") from e
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "check"
    ]
    if len(definitions) != 1 or isinstance(definitions[0], ast.AsyncFunctionDef):
        raise AdhocError(
            "check_code must define exactly one synchronous "
            "check(inp, out, lib)"
        )
    fn = definitions[0]
    positional = [*fn.args.posonlyargs, *fn.args.args]
    if (
        len(positional) != 3
        or fn.args.vararg is not None
        or fn.args.kwarg is not None
        or fn.args.kwonlyargs
    ):
        raise AdhocError("check_code must define check(inp, out, lib)")


def run(code: str, in_text: str, out_text: str, coverage: bool = False):
    """Run the predicate in the sandbox subprocess.

    coverage=False: returns (ok, note, lines) — byte-identical to the
    long-standing contract. coverage=True: returns
    (ok, note, lines, taken) with taken a sorted list of the branch
    ids exercised during execution.

    `ok` is True, False, or None. None means the predicate declined to
    assert on this pair (the input is outside the space its source
    covers), which the caller turns into an ABSTAIN verdict rather than
    counting as a pass."""
    payload = json.dumps(
        {
            "code": code,
            "input": in_text,
            "output": out_text,
            "coverage": bool(coverage),
        }
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD],
            input=payload,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise AdhocError(f"ad-hoc predicate timed out after {TIMEOUT_S}s")
    if proc.returncode != 0:
        raise AdhocError(
            f"ad-hoc predicate crashed: {proc.stderr.strip()[-500:]}"
        )
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        raise AdhocError(
            f"ad-hoc predicate produced no result (stdout: {proc.stdout[:200]!r})"
        )
    if "error" in result:
        raise AdhocError(f"ad-hoc predicate raised:\n{result['error']}")
    if coverage:
        return result["ok"], result["note"], result["lines"], result.get("taken", [])
    return result["ok"], result["note"], result["lines"]
