"""Generic predicate/feature library over the xdsl AST.

These are the dialect-agnostic building blocks output-spec rules can
call directly from the PTC DSL (checker/ptc.py dispatches funcalls
here), so most structural constraints need no generated code at all.
Every function takes the parsed AstPair plus string arguments from
the rule text and returns a FeatureResult carrying the value, the
output lines to blame when the enclosing check fails, and a note.

Op-name patterns: `|`-separated alternatives; each alternative is an
exact op name ("llvm.add"), a dialect prefix wildcard ("llvm.*"),
or a name-prefix wildcard ("llvm.mlir.*").
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import provenance
from .ast import Ast, AstPair, OpView


@dataclass
class FeatureResult:
    value: object  # bool for predicates, int for value-position calls
    lines: list[int] = field(default_factory=list)  # output-side blame
    note: str = ""


class FeatureError(Exception):
    """Bad arguments (unknown side, malformed pattern): ERROR verdict."""


def _side(pair: AstPair, side: str) -> Ast:
    if side == "in":
        return pair.input
    if side == "out":
        return pair.output
    raise FeatureError(f"side must be \"in\" or \"out\", got {side!r}")


def _match(pattern: str):
    alts = [a.strip() for a in pattern.split("|") if a.strip()]
    if not alts:
        raise FeatureError(f"empty op pattern {pattern!r}")

    def match(name: str) -> bool:
        for a in alts:
            if a.endswith(".*"):
                if name == a[:-2] or name.startswith(a[:-1]):
                    return True
            elif name == a:
                return True
        return False

    return match


def _ops(ast: Ast, pattern: str) -> list[OpView]:
    m = _match(pattern)
    return [o for o in ast.body_ops() if m(o.name)]


def _fmt(counter: Counter) -> str:
    return ", ".join(f"{k} x{v}" for k, v in sorted(counter.items())) or "(none)"


# --------------------------------------------------------------------------
# Value-position features (used inside comparisons)
# --------------------------------------------------------------------------


def count_ops(pair: AstPair, side: str, pattern: str) -> FeatureResult:
    """count_ops("out", "llvm.add|llvm.sub") -> int."""
    ops = _ops(_side(pair, side), pattern)
    lines = [o.line for o in ops if side == "out" and o.line]
    return FeatureResult(len(ops), lines)


# --------------------------------------------------------------------------
# Predicate-position features
# --------------------------------------------------------------------------


def no_ops(pair: AstPair, side: str, pattern: str) -> FeatureResult:
    """No op matching the pattern remains on the given side."""
    ops = _ops(_side(pair, side), pattern)
    lines = [o.line for o in ops if side == "out" and o.line]
    note = (
        f"{len(ops)} op(s) matching {pattern!r} present"
        if ops
        else f"no ops matching {pattern!r}"
    )
    return FeatureResult(not ops, lines, note)


def ops_preserved(pair: AstPair, pattern: str) -> FeatureResult:
    """The multiset of matching op names is identical on both sides."""
    a = Counter(o.name for o in _ops(pair.input, pattern))
    b = Counter(o.name for o in _ops(pair.output, pattern))
    if a == b:
        return FeatureResult(True, [], f"preserved: {_fmt(a)}")
    changed = set((a - b).keys()) | set((b - a).keys())
    lines = [
        o.line
        for o in _ops(pair.output, pattern)
        if o.name in changed and o.line
    ]
    return FeatureResult(
        False, lines, f"input has {_fmt(a)}; output has {_fmt(b)}"
    )


def op_mapped(pair: AstPair, in_pattern: str, out_pattern: str) -> FeatureResult:
    """Every input op matching in_pattern is accounted for by an
    output op matching out_pattern (count equality)."""
    ins = _ops(pair.input, in_pattern)
    outs = _ops(pair.output, out_pattern)
    ok = len(ins) == len(outs)
    note = f"{len(ins)} in-op(s) {in_pattern!r} vs {len(outs)} out-op(s) {out_pattern!r}"
    lines = [] if ok else [o.line for o in outs if o.line]
    return FeatureResult(ok, lines, note)


def survives_unchanged(pair: AstPair, pattern: str) -> FeatureResult:
    """Every matching op in the OUTPUT was already in the input, verbatim.

    "Verbatim" means structurally identical modulo SSA naming: same
    operand provenance, result types, properties, and region contents
    (see checker/provenance.py). This is the refusal contract as a
    predicate. A pass that declines to transform something must leave it
    alone, and checking only that an op of the same NAME is still present
    misses every edit to it.

    The direction is deliberate: output is contained in input, not the
    reverse. A pass may legitimately rewrite some matching ops away; what
    it may not do is emit one that was never there in that exact form.
    """
    outs = _ops(pair.output, pattern)
    if not outs:
        return FeatureResult(True, [], f"no output op matches {pattern!r}")
    in_forms, _ = provenance.canon_counts(pair.input, _ops(pair.input, pattern))
    changed = [o for o in outs if provenance.canon(o) not in in_forms]
    if not changed:
        return FeatureResult(
            True, [], f"{len(outs)} surviving op(s) identical to their source"
        )
    lines = [o.line for o in changed if o.line]
    return FeatureResult(
        False,
        lines,
        f"{len(changed)} of {len(outs)} op(s) matching {pattern!r} differ "
        "from every input op of that kind (operands, properties or body "
        "were rewritten)",
    )


def operand_origins_preserved(
    pair: AstPair, in_pattern: str, out_pattern: str, count: str = ""
) -> FeatureResult:
    """Matching ops carry the same operands, from the same sources, in
    the same ORDER, across the rewrite.

    `count` limits the comparison to the first N operand positions, which
    is what comparing loop headers needs: `scf.for` and `scf.forall`
    agree on lower bound, upper bound and step and then diverge.

    Order is what makes this catch a swap. Comparing the SET of operand
    origins would pass a rewrite that exchanged a loop's bounds, which is
    precisely the defect class structural checks were missing.
    """
    try:
        n = int(count) if str(count).strip() else None
    except ValueError:
        raise FeatureError(f"count must be an integer, got {count!r}")
    ins = _ops(pair.input, in_pattern)
    outs = _ops(pair.output, out_pattern)
    if not ins and not outs:
        return FeatureResult(True, [], "neither side has a matching op")
    a = Counter(
        tuple(provenance.operand_origins(o, n)) for o in ins
    )
    b = Counter(
        tuple(provenance.operand_origins(o, n)) for o in outs
    )
    if a == b:
        return FeatureResult(
            True, [], f"{len(outs)} op(s) carry their source operands in order"
        )
    missing = a - b
    extra = b - a
    lines = [
        o.line for o in outs
        if o.line and tuple(provenance.operand_origins(o, n)) in extra
    ]
    return FeatureResult(
        False,
        lines,
        f"operand provenance differs: input has {[list(t) for t in missing]}, "
        f"output has {[list(t) for t in extra]}",
    )


def _constants(ast: Ast) -> Counter:
    vals = Counter()
    for o in ast.body_ops():
        if o.name in ("arith.constant", "llvm.mlir.constant"):
            vals[o.prop_str("value")] += 1
    return vals


def constants_preserved(pair: AstPair) -> FeatureResult:
    """Multiset of constant values (with their types) is unchanged."""
    a, b = _constants(pair.input), _constants(pair.output)
    if a == b:
        return FeatureResult(True, [], f"constants: {_fmt(a)}")
    changed = set((a - b).keys()) | set((b - a).keys())
    lines = [
        o.line
        for o in pair.output.body_ops()
        if o.name in ("arith.constant", "llvm.mlir.constant")
        and o.prop_str("value") in changed
        and o.line
    ]
    return FeatureResult(False, lines, f"input {_fmt(a)}; output {_fmt(b)}")


_CMP_OPS = {
    "llvm.icmp": "int",
    "arith.cmpi": "int",
    "llvm.fcmp": "float",
    "arith.cmpf": "float",
}


def _cmp_predicates(ast: Ast) -> Counter:
    """Multiset of (int|float, numeric predicate) across dialects.

    llvm and arith share predicate enum numbering for the supported
    predicates (the pass relies on exactly this), so the numeric
    value is the dialect-neutral identity.
    """
    preds = Counter()
    for o in ast.body_ops():
        kind = _CMP_OPS.get(o.name)
        if kind:
            v = o.prop("predicate")
            num = getattr(getattr(v, "value", None), "data", None)
            preds[(kind, num if num is not None else str(v))] += 1
    return preds


def predicates_preserved(pair: AstPair) -> FeatureResult:
    """Compare predicates survive the rewrite with identical meaning."""
    a, b = _cmp_predicates(pair.input), _cmp_predicates(pair.output)
    if a == b:
        note = ", ".join(f"{k}:{p}" for k, p in sorted(a.elements())) or "(none)"
        return FeatureResult(True, [], f"predicates: {note}")
    changed = set((a - b).keys()) | set((b - a).keys())
    lines = [
        o.line
        for o in pair.output.body_ops()
        if o.name in _CMP_OPS
        and (
            _CMP_OPS[o.name],
            getattr(getattr(o.prop("predicate"), "value", None), "data", None),
        )
        in changed
        and o.line
    ]
    return FeatureResult(False, lines, f"input {dict(a)}; output {dict(b)}")


def signatures_preserved(pair: AstPair) -> FeatureResult:
    """Every function symbol keeps its argument/result types (the
    llvm.func -> func.func raise is name-transparent)."""

    def sigs(ast: Ast) -> dict:
        out = {}
        for o in ast.body_ops():
            if o.name in ("func.func", "llvm.func"):
                sym = o.prop_str("sym_name")
                ft = o.prop("function_type")
                out[sym] = str(ft)
        return out

    def norm(t: str) -> str:
        # llvm.func prints !llvm.func<f32 (f32)>; func.func prints
        # (f32) -> f32. Normalize to "args->results".
        t = t.replace("!llvm.func<", "").rstrip(">")
        if "(" in t and "->" not in t:
            ret, args = t.split("(", 1)
            return f"({args.rstrip(')')})->{ret.strip()}"
        return t.replace(" -> ", "->").strip()

    a = {k: norm(v) for k, v in sigs(pair.input).items()}
    b = {k: norm(v) for k, v in sigs(pair.output).items()}
    if a == b:
        return FeatureResult(True, [], f"{len(a)} function signature(s) preserved")
    diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    lines = [
        o.line
        for o in pair.output.body_ops()
        if o.name in ("func.func", "llvm.func")
        and o.prop_str("sym_name") in diff
        and o.line
    ]
    return FeatureResult(
        False, lines, f"differing symbols: {sorted(diff)}"
    )


# Name -> (callable, value-position allowed). The PTC evaluator
# dispatches funcalls with string args here; bool results may also be
# used in predicate position.
REGISTRY = {
    "count_ops": count_ops,
    "no_ops": no_ops,
    "ops_preserved": ops_preserved,
    "op_mapped": op_mapped,
    "constants_preserved": constants_preserved,
    "predicates_preserved": predicates_preserved,
    "signatures_preserved": signatures_preserved,
    "survives_unchanged": survives_unchanged,
    "operand_origins_preserved": operand_origins_preserved,
}
