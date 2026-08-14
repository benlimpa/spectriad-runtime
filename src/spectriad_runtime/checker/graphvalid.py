"""graph_valid: does the pass emit a graph Loom itself will run?

Workflow audit priority 0 item 4 follow-up (2026-08-03). The adversarial
reviews of `graph-for-lowering` and `graph-index-switch-lowering` turned
up twelve survivors, and four of them are not value divergences at all:
they are graphs `loom-dfg-sim` refuses before it executes anything, with
diagnostics like

    error: graph @g_for_reduce value output #0 is not statically exact-one
    error: graph @g_for_store completion witness #0 is not statically one-shot

Those four need no probes, no argument fixtures and no reference
interpreter to catch. Loom validates a finalized graph BEFORE it binds
runtime arguments, so running the simulator on the output side with NO
arguments separates the two cases exactly:

    bad graph      -> error: ... is not statically exact-one
    correct graph  -> error: missing runtime argument 0

The second message means the graph cleared validation and the simulator
got as far as wanting inputs. That is the whole test.

WHY THIS IS A SEPARATE ORACLE FROM sim_equiv. sim_equiv subsumes these
cases when it can run, and on these two units it does. But it needs the
INPUT side to be executable on checker/refinterp, and when the input
holds an op the reference interpreter does not model, sim_equiv must
STUB honestly and says nothing at all. graph_valid never looks at the
input, so it keeps its verdict exactly where the semantic oracle loses
one. It is strictly weaker and strictly more robust, which is why both
are worth shipping.

It is a well-formedness oracle, not a semantic one: it can only see
defects that break Loom's static token discipline. A miscompilation
that keeps the graph statically well formed and changes the value is
invisible here and is sim_equiv's job.
"""

from __future__ import annotations

import re

from . import dfgsim
from .oracles import Unavailable

try:  # pragma: no cover - exercised by the absence path only
    from . import ast as ast_mod
except Exception:  # pragma: no cover
    ast_mod = None  # type: ignore[assignment]


# Diagnostics from lib/Dataflow/IR/DataflowGraphValidation.cpp, i.e. the
# graph validator proper. Grounded in that file's string literals rather
# than guessed from the messages we happened to see, so a defect class we
# have not hit yet still classifies as a refusal instead of falling into
# the "unknown" bucket and reading as a STUB.
_STATIC_REFUSAL = re.compile(
    r"is not statically (?:exact-one|one-shot)"
    r"|has no statically proven close/commit"
    r"|finalized graph (?:contains|is missing|must have|routes)"
    r"|retirement frontier does not"
    r"|nontrivial graph uses raw start as a retirement completion witness"
    r"|fresh memory export must use a memref result"
    r"|memref\.alloc dynamic extent must be a graph value input"
)

# The simulator cleared validation and reached argument binding.
_CLEARED = re.compile(r"missing runtime argument")

# "error: graph @g_for_store completion witness #0 is not ..." — the
# symbol the validator is complaining about.
_OFFENDER = re.compile(r"graph @([A-Za-z_][\w.$]*)")


def _graph_names(a) -> dict[str, int | None]:
    """sym_name -> its line, for every dataflow.graph in the module."""
    found: dict[str, int | None] = {}
    for view in a.ops:
        if view.name != "dataflow.graph":
            continue
        sym = view.prop_str("sym_name")
        if sym is None:
            continue
        found[sym.strip('"')] = view.line
    return found


# The refusal families, as kinds. Two refusals of the same kind on the
# two sides of a rewrite mean the pass did not introduce the defect.
_KINDS = (
    ("exact-one", re.compile(r"is not statically exact-one")),
    ("one-shot", re.compile(r"is not statically one-shot")),
    ("close-commit", re.compile(r"has no statically proven close/commit")),
    ("raw-start-witness", re.compile(r"nontrivial graph uses raw start")),
    ("retirement-frontier", re.compile(r"retirement frontier does not")),
    ("residual-structured", re.compile(r"residual structured operation")),
    ("residual-memory", re.compile(r"residual memory operation")),
    ("finalized-graph", re.compile(r"finalized graph ")),
)


def _refusal_kind(message: str) -> str | None:
    for kind, pattern in _KINDS:
        if pattern.search(message):
            return kind
    return None


def _refusal_kind_of(text: str) -> str | None:
    """The refusal kind the OTHER side of the pair already exhibits."""
    if not text.strip():
        return None
    try:
        a = ast_mod.parse(text)
    except Exception:
        return None
    names = _graph_names(a)
    if not names:
        return None
    try:
        report = dfgsim.simulate(text, sorted(names)[0])
    except Unavailable:
        return None
    err = (report.error or "").strip()
    if not err or not _STATIC_REFUSAL.search(err):
        return None
    return _refusal_kind(err.splitlines()[0])


def _blame(a, graph: str, header: int | None) -> list[int]:
    """The graph header plus its token-shaping ops."""
    lines: list[int] = [header] if header else []
    for view in a.ops:
        if view.name.startswith("dataflow.") and view.line:
            lines.append(view.line)
    return sorted(set(lines))[:12]


def graph_valid(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    """FAIL when the output holds a graph Loom's validator rejects."""
    if not dfgsim.available():
        raise Unavailable(f"{dfgsim.ENV_VAR} not configured")
    if ast_mod is None:
        raise Unavailable("checker.ast is unavailable")
    try:
        out_ast = ast_mod.parse(out_text)
    except ast_mod.AstError as e:
        raise Unavailable(f"output side does not parse: {e}")

    names = _graph_names(out_ast)
    if not names:
        raise Unavailable("output holds no dataflow.graph to validate")

    # The validator runs over the whole module, not just the graph named
    # by --graph: asking for @g_for_index is what surfaced the @g_for_store
    # refusal in every case below. So one invocation covers every graph,
    # and the offending symbol has to be read out of the diagnostic rather
    # than assumed to be the one we asked about.
    probe = sorted(names)[0]
    report = dfgsim.simulate(out_text, probe)
    err = (report.error or "").strip()
    first = err.splitlines()[0] if err else ""

    if _STATIC_REFUSAL.search(err):
        m = _OFFENDER.search(first)
        offender = m.group(1) if m else probe
        # Did the PASS introduce this, or was the input already like
        # that? For a lowering pass the input is normally refused too,
        # but for a DIFFERENT reason ("residual structured operation" —
        # it still holds scf), and that refusal is expected rather than
        # a defect. So compare the refusal KIND: only an output refusal
        # the input does not already exhibit is attributable to the pass.
        #
        # This is not hypothetical. graph-constant-lowering's isolated
        # profile emits, and is GIVEN, graphs that both trip "nontrivial
        # graph uses raw start as a retirement completion witness".
        # Blaming the pass for that would be a false positive.
        pre = _refusal_kind_of(in_text)
        kind = _refusal_kind(first)
        if pre is not None and kind is not None and pre == kind:
            raise Unavailable(
                f"the input is already refused the same way ({kind}), so "
                f"this says nothing about the pass"
            )
        note = (
            f"Loom's own validator rejects the emitted graph @{offender}: "
            f"{first[:300]}"
        )
        return False, note, _blame(out_ast, offender, names.get(offender))

    if report.ok or _CLEARED.search(err):
        return True, (
            f"all {len(names)} graph(s) clear Loom's static validator "
            f"(token cardinality, retirement frontier, no residual "
            f"structured ops)"
        ), []

    # Neither a validation refusal nor a clean pass. Claiming
    # well-formedness from that would be a guess.
    raise Unavailable(
        f"loom-dfg-sim gave no readable validation verdict: {first[:300]}"
    )
