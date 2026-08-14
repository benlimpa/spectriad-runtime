"""Differential execution for Loom graph-lowering passes.

This is the semantic oracle for the graph-lowering units. Every other check in the corpus is structural: it reads the
shape of the output and asks whether the shape is right. A lowering
can be structurally impeccable and still compute the wrong number, and
the audit's evidence is that structure alone misses exactly the
defects that matter (a coherent mux/demux lane swap keeps every
structural relation intact and inverts the result).

The method is a differential between two INDEPENDENT engines:

  input side   still holds structured control flow, so Loom's
               simulator refuses it. Executed by our own reference
               interpreter (checker/refinterp.py), which never
               consults the compiler.
  output side  is a pure dataflow graph. Only Loom's token model
               defines what it means, so it is executed by Loom's own
               simulator (checker/dfgsim.py).

Independence is the point, and it is the same argument the rest of
SpecTriad runs on. Comparing the compiler's output against the
compiler's own idea of the input would be circular and could only ever
confirm the compiler.

Two engines means one hazard worth naming: a divergence can always be
OUR interpreter being wrong rather than the compiler. That is a
spec_defect in the autonomous-triage vocabulary and is diagnosed the
same way as any other. The interpreter refuses to guess (an
unsupported construct raises rather than inventing a value), so its
failure mode is an honest STUB rather than a false accusation.

When the input side is ALREADY a pure dataflow graph, as it is for
graph-constant-lowering, there is no residual structured control flow
for the interpreter to add value on, and both sides run under the
simulator.
"""

from __future__ import annotations

import hashlib
import os
import re

from . import ast as ast_mod
from . import dfgsim
from . import provenance
from .oracles import Unavailable

try:
    from . import refinterp
except Exception:  # pragma: no cover - refinterp is required in practice
    refinterp = None

# Probes per graph. Each is one ssh+docker round trip, so this trades
# oracle strength against campaign wall clock. Two probes already give
# both polarities of an i1 selector, which is the common case.
PROBES = int(os.environ.get("SPECTRIAD_SIM_PROBES", "3"))
FLOAT_TOL = 1e-6

_INT_TY = re.compile(r"^(?:i|si|ui)(\d+)$")
_MEMREF = re.compile(r"^memref<([0-9x?]+)x([^>]+)>$")
# Size used for a dynamic (`?`) memref dimension. The fixture IS the
# buffer, so a dynamic extent is ours to choose. Kept at least as large
# as the largest index fixture so a probe never manufactures an
# out-of-bounds access and blames the compiler for it.
DYN_DIM = 16


class Divergence(Exception):
    """The two engines disagree. Carries a human-readable account."""

    def __init__(self, msg: str, lines: list[int] | None = None):
        super().__init__(msg)
        self.lines = lines or []


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _memref_shape(ty: str) -> tuple[int, str] | None:
    m = _MEMREF.match(ty.strip())
    if not m:
        return None
    n = 1
    for d in m.group(1).split("x"):
        if not d:
            continue
        n *= DYN_DIM if d == "?" else int(d)
    return n, m.group(2).strip()


def _scalar(ty: str, p: int, salt: int) -> str:
    """One deterministic scalar fixture for `ty` on probe `p`."""
    ty = ty.strip()
    if ty == "i1":
        # Alternate polarity across probes so both arms of a selector
        # get exercised even at PROBES=2.
        return str(p % 2)
    m = _INT_TY.match(ty)
    if m:
        width = int(m.group(1))
        pool = [0, 1, 2, 7, 3, 5]
        v = pool[(p + salt) % len(pool)]
        if width >= 32 and p >= 2:
            # One value past the 16-bit boundary, still far from
            # overflow, so a width mistake in either engine shows up.
            v = 70000 + salt % 13
        return str(v)
    if ty == "index":
        # Index arguments are usually memref subscripts. Keep them
        # small so a fixture never manufactures an out-of-bounds access
        # that would be reported as a compiler divergence.
        return str((p + salt) % 4)
    if ty.startswith("f") or ty.startswith("bf"):
        return "%.6e" % float([0.0, 1.0, 2.5, 3.0][(p + salt) % 4])
    raise Unavailable(f"no fixture rule for argument type {ty!r}")


def fixtures(
    arg_types: list[str],
    probe: int,
    salt: int,
    *,
    positive_args: set[int] | None = None,
    bound_args: set[int] | None = None,
):
    """Build one probe's --arg / --memref fixtures for a signature."""
    args: dict[int, str] = {}
    memrefs: dict[int, list[str]] = {}
    positive_args = positive_args or set()
    bound_args = bound_args or set()
    # The tightest memref the loop induction variable could subscript.
    # A trip count past it makes the INPUT program trap, which says
    # nothing about the pass.
    extents = [s[0] for s in (_memref_shape(t) for t in arg_types) if s]
    cap = min(extents) if extents else None
    for i, ty in enumerate(arg_types):
        shape = _memref_shape(ty)
        if shape is None:
            value = _scalar(ty, probe, salt + i)
            # A dynamic scf.for step is a precondition on the execution
            # fixture, not behavior of the pass. Preserve zero elsewhere,
            # where it remains an important boundary value.
            if i in positive_args and int(value, 0) <= 0:
                value = "1"
            # Same reasoning one operand over: an argument used directly
            # as a loop bound has to stay inside the memref its induction
            # variable indexes. _scalar's wide probe (70000+) is chosen to
            # expose width mistakes, and it does that for arguments that
            # are not trip counts.
            if cap is not None and i in bound_args and int(value, 0) > cap:
                value = str(cap)
            args[i] = value
            continue
        n, elem = shape
        if n <= 0 or n > 4096:
            raise Unavailable(f"unusable memref fixture size in {ty!r}")
        memrefs[i] = [_scalar(elem, probe + k, salt + i + k) for k in range(n)]
    return args, memrefs


def _positive_step_args(gop) -> set[int]:
    """Function arguments used directly as dynamic scf.for steps.

    dataflow.graph block argument zero is the implicit control token;
    the remaining block arguments share the simulator's function-input
    index space. Generated graph-for inputs use those arguments directly
    for loop bounds and steps, so this is enough to keep fixtures legal
    without discarding zero as a useful value for unrelated arguments.
    """
    op = gop.op if hasattr(gop, "op") else gop
    if not op.regions:
        return set()
    blocks = list(op.regions[0].blocks)
    if not blocks:
        return set()
    block_args = list(blocks[0].args)
    arg_indexes = {id(arg): i - 1 for i, arg in enumerate(block_args[1:], 1)}
    found: set[int] = set()

    def walk(parent):
        for region in parent.regions:
            for block in region.blocks:
                for child in block.ops:
                    if (
                        ast_mod._real_name(child) == "scf.for"
                        and len(child.operands) >= 3
                    ):
                        index = arg_indexes.get(id(child.operands[2]))
                        if index is not None:
                            found.add(index)
                    walk(child)

    walk(op)
    return found


# Width and index conversions a trip count reaches a loop bound through.
# Generated graph-for inputs take an i32 count argument and widen it:
#   %limit = arith.extui %count : i32 to i64
#   scf.for %zero_i64 to %limit step %one_i64
# so matching only direct block arguments misses the bound entirely.
_CAST_OPS = frozenset({
    "arith.extui",
    "arith.extsi",
    "arith.trunci",
    "arith.index_cast",
    "arith.index_castui",
    "builtin.unrealized_conversion_cast",
})


def _through_casts(value, arg_indexes: dict[int, int], depth: int = 0):
    """The block argument a value comes from, across width/index casts."""
    index = arg_indexes.get(id(value))
    if index is not None:
        return index
    if depth >= 8:
        return None
    op = provenance.defining_op(value)
    if op is None or ast_mod._real_name(op) not in _CAST_OPS:
        return None
    if len(op.operands) != 1:
        return None
    return _through_casts(op.operands[0], arg_indexes, depth + 1)


def _bound_args(gop) -> set[int]:
    """Function arguments that reach a dynamic scf.for lower or upper
    bound, directly or through a width/index cast.

    Same index space and the same purpose as _positive_step_args: a trip
    count is a precondition on the fixture. An argument that is a loop
    bound cannot also carry _scalar's deliberately wide probe value
    without driving the induction variable off the end of the memref it
    subscripts, which traps the reference interpreter and costs the probe
    rather than testing the pass.
    """
    op = gop.op if hasattr(gop, "op") else gop
    if not op.regions:
        return set()
    blocks = list(op.regions[0].blocks)
    if not blocks:
        return set()
    block_args = list(blocks[0].args)
    arg_indexes = {id(arg): i - 1 for i, arg in enumerate(block_args[1:], 1)}
    found: set[int] = set()

    def walk(parent):
        for region in parent.regions:
            for block in region.blocks:
                for child in block.ops:
                    if (
                        ast_mod._real_name(child) == "scf.for"
                        and len(child.operands) >= 2
                    ):
                        for operand in child.operands[:2]:
                            index = _through_casts(operand, arg_indexes)
                            if index is not None:
                                found.add(index)
                    walk(child)

    walk(op)
    return found


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def _has_structured(gop) -> bool:
    """True when the graph body still holds structured control flow."""
    found = False

    def walk(op):
        nonlocal found
        for region in op.regions:
            for block in region.blocks:
                for child in block.ops:
                    name = ast_mod._real_name(child)
                    if name.startswith("scf.") or name.startswith("affine."):
                        found = True
                        return
                    walk(child)

    walk(gop.op)
    return found


def _to_num(s: str):
    try:
        return int(s, 0)
    except ValueError:
        return float(s)


def _run_side(text, gop, name, args, memrefs, force_sim: bool):
    """Execute one side, returning (outputs, memory) in engine-neutral form."""
    if force_sim or not _has_structured(gop):
        rep = dfgsim.simulate(text, name, args, memrefs)
        if not rep.ok:
            raise Divergence(f"loom-dfg-sim refused the graph: {rep.error}")
        return rep.outputs, rep.memory
    if refinterp is None:
        raise Unavailable("checker.refinterp is unavailable")
    iargs = {i: _to_num(v) for i, v in args.items()}
    imem = {i: [_to_num(v) for v in vs] for i, vs in memrefs.items()}
    try:
        res = refinterp.interpret(gop, iargs, imem)
    except refinterp.Unsupported as e:
        raise Unavailable(f"reference interpreter: {e}")
    except refinterp.Trap as e:
        raise Unavailable(f"reference interpreter trapped on its own fixture: {e}")
    return res.outputs, res.memory


def _same(a, b) -> bool:
    ta, va = a
    tb, vb = b
    if isinstance(va, float) or isinstance(vb, float):
        try:
            fa, fb = float(va), float(vb)
        except (TypeError, ValueError):
            return va == vb
        scale = max(1.0, abs(fa), abs(fb))
        return abs(fa - fb) <= FLOAT_TOL * scale
    if isinstance(va, int) and isinstance(vb, int):
        # Types can differ legitimately across engines (index vs i64);
        # the value is what the program computed.
        return va == vb
    return va == vb


def _compare(graph, probe, args, want, got) -> None:
    wout, wmem = want
    gout, gmem = got
    where = f"graph @{graph}, probe {probe} (" + ", ".join(
        f"arg{i}={v}" for i, v in sorted(args.items())
    ) + ")"
    if len(wout) != len(gout):
        raise Divergence(
            f"{where}: input produces {len(wout)} value results, "
            f"output produces {len(gout)}"
        )
    for k, (w, g) in enumerate(zip(wout, gout)):
        if not _same(w, g):
            raise Divergence(
                f"{where}: result #{k} is {g[1]} after the pass, "
                f"but the input program computes {w[1]}"
            )
    for idx in sorted(set(wmem) | set(gmem)):
        wv, gv = wmem.get(idx, []), gmem.get(idx, [])
        if len(wv) != len(gv):
            raise Divergence(
                f"{where}: memref arg{idx} has {len(gv)} elements after "
                f"the pass, {len(wv)} in the input program"
            )
        for k, (w, g) in enumerate(zip(wv, gv)):
            if not _same(w, g):
                raise Divergence(
                    f"{where}: memref arg{idx}[{k}] is {g[1]} after the "
                    f"pass, but the input program leaves {w[1]}"
                )


def _blame(out_ast, graph: str) -> list[int]:
    """Output lines to highlight: the graph header and its selectors."""
    lines = []
    for view in out_ast.ops:
        if view.name == "dataflow.graph":
            if view.prop_str("sym_name") not in (None, f'"{graph}"', graph):
                continue
        if view.name in ("dataflow.mux", "dataflow.demux",
                         "dataflow.graph.return") and view.line:
            lines.append(view.line)
    return sorted(set(lines))[:12]


def sim_equiv(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    """Execute both sides of the pair and compare observable results."""
    if not dfgsim.available():
        raise Unavailable(f"{dfgsim.ENV_VAR} not configured")
    if refinterp is None:
        raise Unavailable("checker.refinterp is unavailable")
    try:
        pair = ast_mod.parse_pair(in_text, out_text)
    except ast_mod.AstError as e:
        raise Unavailable(str(e))

    in_graphs = refinterp.graphs(pair.input)
    out_graphs = refinterp.graphs(pair.output)
    shared = sorted(set(in_graphs) & set(out_graphs))
    if not shared:
        raise Unavailable("no dataflow.graph symbol present on both sides")

    salt = int(hashlib.sha256(
        (in_text + out_text).encode()
    ).hexdigest()[:8], 16)
    checked = 0
    for name in shared:
        gin, gout = in_graphs[name], out_graphs[name]
        sin, sout = refinterp.signature(gin), refinterp.signature(gout)
        if sin.arg_types != sout.arg_types:
            # A lowering that changes the graph's interface is a
            # structural matter, and comparing executions across
            # different signatures would compare different programs.
            raise Unavailable(
                f"graph @{name} signature changed: "
                f"{sin.arg_types} -> {sout.arg_types}"
            )
        positive_args = _positive_step_args(gin)
        bound_args = _bound_args(gin)
        for probe in range(max(1, PROBES)):
            args, memrefs = fixtures(
                sin.arg_types,
                probe,
                salt,
                positive_args=positive_args,
                bound_args=bound_args,
            )
            try:
                want = _run_side(in_text, gin, name, args, memrefs, False)
            except Divergence as e:
                # The INPUT was refused. That says nothing about the
                # pass, so it is not a verdict.
                raise Unavailable(f"input side not executable: {e}")
            try:
                # A refusal HERE is a verdict: the pass emitted a graph
                # that Loom's own simulator will not run, on an input
                # the reference engine executes fine.
                got = _run_side(out_text, gout, name, args, memrefs, True)
                _compare(name, probe, args, want, got)
            except Divergence as e:
                return False, str(e)[:600], _blame(pair.output, name)
            checked += 1

    note = (
        f"differential execution agrees on {checked} probe(s) across "
        f"{len(shared)} graph(s): the lowered graph computes what the "
        f"input program computes"
    )
    return True, note, []
