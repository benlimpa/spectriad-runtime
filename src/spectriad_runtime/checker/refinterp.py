"""Reference interpreter for the pre-lowering side of a Loom graph.

`sim_equiv` compares what a graph-lowering pass was given against what
it produced, by executing both. The OUTPUT side is a pure
`dataflow.graph` and Loom's own simulator runs it (checker/dfgsim.py).
The INPUT side cannot go the same way: it still carries structured
control flow inside the graph, and the simulator refuses such a module
outright ("finalized graph contains residual structured operation
'scf.if'"). So the input side needs an engine of its own.

Independence is the point of that engine. If the input side were
executed by anything derived from the compiler under test, an oracle
built on the comparison would only confirm that the compiler agrees
with itself. This module therefore implements the `scf`/`arith`/
`memref` semantics directly from their definitions, over the shared
xdsl AST layer (checker/ast.py), and consults nothing else.

Two rules keep the engine honest:

  * Integer arithmetic wraps at the declared bit width, in two's
    complement. Python's unbounded ints would silently disagree with
    the simulator on exactly the overflow boundaries the campaigns aim
    inputs at, which is where a wrong answer would matter most.
  * Anything outside the measured vocabulary raises `Unsupported`,
    naming the construct. Upstream that becomes a STUB verdict. A
    guessed value would become a false bug report instead.

Argument indexing follows the simulator's, so fixtures are shared: a
graph's block arguments are `(%ctrl: none, <the function_type inputs>)`
and the leading control argument has no index, so block argument k+1 is
`--arg k`. Scalars and memrefs share that one index space.
"""

from __future__ import annotations

import math
import re
import struct
import weakref
from dataclasses import dataclass, field

from .ast import Ast, _real_name

DEFAULT_MAX_STEPS = 200_000


class Unsupported(Exception):
    """Construct outside the interpreted subset."""


class Trap(Exception):
    """Runtime violation, e.g. an out-of-bounds access."""

    def __init__(self, msg: str, line: int | None = None):
        super().__init__(msg)
        self.line = line


@dataclass
class GraphSig:
    name: str
    arg_types: list[str]  # function_type INPUTS, in --arg index order
    result_types: list[str]  # function_type RESULTS


@dataclass
class ExecResult:
    """One execution, in dfgsim.Report's value shape.

    `outputs` and `memory` carry `(type_string, python_value)` pairs so
    a caller can compare the two engines element by element without
    knowing which produced which.
    """

    # Value results only, in function_type result order. Stream, memory
    # and control results of dataflow.graph.return are bookkeeping and
    # are dropped here, exactly as dfgsim.Report drops the aggregate
    # control token.
    outputs: list[tuple[str, object]] = field(default_factory=list)
    # {function_type input index: [element values]}
    memory: dict[int, list[tuple[str, object]]] = field(default_factory=dict)


# ---------------------------------------------------------------- types

_INT_T = re.compile(r"^i(\d+)$")
_FLOAT_T = re.compile(r"^f(16|32|64)$")
_MEMREF_T = re.compile(r"^memref<(.+)>$")

_FLOAT_FMT = {16: "e", 32: "f", 64: "d"}


def _int_width(ty: str) -> int | None:
    """Bit width of an integer-like type, or None. `index` is 64-bit."""
    if ty == "index":
        return 64
    m = _INT_T.match(ty)
    return int(m.group(1)) if m else None


def _float_width(ty: str) -> int | None:
    m = _FLOAT_T.match(ty)
    return int(m.group(1)) if m else None


def _wrap(v: int, width: int) -> int:
    """Truncate to `width` bits, two's complement signed.

    i1 is the one exception: it is kept unsigned, 0 or 1. That is how a
    boolean reads everywhere else in the pipeline, and it is what xdsl
    hands back for the literal `true` (which it stores as the signed
    i1 value -1).
    """
    v &= (1 << width) - 1
    if width > 1 and v >= 1 << (width - 1):
        v -= 1 << width
    return v


def _unsigned(v: int, width: int) -> int:
    return v & ((1 << width) - 1)


def _round_float(v: float, width: int) -> float:
    """Round to the declared float precision.

    Python floats are f64, so an f32 computation carried at full double
    precision would drift away from the simulator's over a reduction
    loop. Rounding after every operation is the cheap way to stay in the
    declared format.
    """
    fmt = _FLOAT_FMT.get(width)
    if fmt is None or width == 64:
        return float(v)
    try:
        return struct.unpack(fmt, struct.pack(fmt, v))[0]
    except OverflowError:
        return math.inf if v > 0 else -math.inf


@dataclass
class _Buf:
    """A memref fixture: element type, shape, and dense row-major data."""

    elt: str
    shape: list[int]
    data: list

    def offset(self, indices: list[int], line: int | None) -> int:
        if len(indices) != len(self.shape):
            raise Trap(
                f"rank mismatch: {len(indices)} indices for shape {self.shape}",
                line,
            )
        off = 0
        for x, d in zip(indices, self.shape):
            if not 0 <= x < d:
                raise Trap(
                    f"out-of-bounds index {x} for dimension of size {d}", line
                )
            off = off * d + x
        return off


def _parse_memref(ty: str) -> tuple[str, list[int | None]]:
    """(element type, shape) of a memref type string; None = dynamic."""
    m = _MEMREF_T.match(ty)
    if not m:
        raise Unsupported(f"argument type '{ty}' is not a memref")
    parts = m.group(1).split("x")
    if len(parts) < 2:
        raise Unsupported(f"memref type '{ty}' has no shape")
    elt = parts[-1]
    if _int_width(elt) is None and _float_width(elt) is None:
        # A layout map or memory space would land here too, and neither
        # has a meaning this engine could honour.
        raise Unsupported(f"memref element type '{elt}' in '{ty}'")
    shape: list[int | None] = []
    for d in parts[:-1]:
        if d == "?":
            shape.append(None)
        elif d.isdigit():
            shape.append(int(d))
        else:
            raise Unsupported(f"memref dimension '{d}' in '{ty}'")
    return elt, shape


def _coerce(ty: str, value, where: str):
    """A fixture value in the engine's representation for `ty`."""
    w = _int_width(ty)
    if w is not None:
        try:
            return _wrap(int(value), w)
        except (TypeError, ValueError):
            raise Trap(f"{where}: '{value}' is not an integer")
    w = _float_width(ty)
    if w is not None:
        try:
            return _round_float(float(value), w)
        except (TypeError, ValueError):
            raise Trap(f"{where}: '{value}' is not a float")
    raise Unsupported(f"{where}: type '{ty}' is outside the interpreted subset")


def _make_buf(ty: str, values, index: int) -> _Buf:
    elt, shape = _parse_memref(ty)
    n = len(values)
    if shape.count(None) == 1 and len(shape) == 1:
        # The only dynamic case the corpus produces is a 1-D `memref<?x`,
        # whose extent the fixture itself declares.
        shape = [n]
    elif None in shape:
        raise Unsupported(f"argument {index}: dynamic shape in '{ty}'")
    want = 1
    for d in shape:
        want *= d
    if want != n:
        raise Trap(
            f"argument {index}: fixture has {n} elements, '{ty}' declares {want}"
        )
    data = [
        _coerce(elt, v, f"argument {index} element {k}")
        for k, v in enumerate(values)
    ]
    return _Buf(elt=elt, shape=list(shape), data=data)


# ------------------------------------------------------------- discovery

# Source lines are only known to the Ast, and `interpret` is handed a
# single graph. `graphs` records the mapping so traps can name a line;
# a graph obtained some other way simply reports line=None.
_LINES: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _raw(gop):
    """Accept either an OpView or a raw xdsl operation."""
    return getattr(gop, "op", gop)


def _attr(op, key: str):
    """Property or attribute by name, or None.

    An explicit None test is load-bearing: xdsl's zero-valued
    IntegerAttr is falsy, so the usual `properties.get(k) or
    attributes.get(k)` idiom silently loses every `constant 0`.
    """
    v = op.properties.get(key)
    if v is None:
        v = op.attributes.get(key)
    return v


def graphs(a: Ast) -> dict[str, object]:
    """sym_name -> the dataflow.graph OpView, for an Ast from ast.parse."""
    found: dict[str, object] = {}
    for view in a.ops:
        if view.name != "dataflow.graph":
            continue
        sym = view.prop_str("sym_name")
        if sym is None:
            continue
        found[sym.strip('"')] = view
    if found:
        lines = {id(v.op): v.line for v in a.ops if v.line is not None}
        for view in found.values():
            _LINES[view.op] = lines
    return found


def signature(gop) -> GraphSig:
    op = _raw(gop)
    ft = _attr(op, "function_type")
    if ft is None:
        raise Unsupported("dataflow.graph without a function_type property")
    sym = _attr(op, "sym_name")
    return GraphSig(
        name=str(sym).strip('"') if sym is not None else "",
        arg_types=[str(t) for t in ft.inputs.data],
        result_types=[str(t) for t in ft.outputs.data],
    )


# ------------------------------------------------------------ execution


@dataclass
class _Term:
    """The terminator a block reached, and the values it carried."""

    name: str
    values: list
    op: object = None


_TERMINATORS = ("scf.yield", "scf.condition", "dataflow.graph.return")


class _Ctx:
    def __init__(self, lines: dict[int, int], max_steps: int):
        self.env: dict[int, object] = {}
        self.lines = lines
        self.steps = 0
        self.max_steps = max_steps

    def line(self, op) -> int | None:
        return self.lines.get(id(op))

    def get(self, value):
        try:
            return self.env[id(value)]
        except KeyError:
            raise Unsupported("a value was used before it was computed")

    def set(self, value, val) -> None:
        self.env[id(value)] = val

    def tick(self, op) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise Trap("step budget exhausted", self.line(op))


def _result_type(op, i: int = 0) -> str:
    return str(op.results[i].type)


def _need_int(ty: str, op, ctx: _Ctx) -> int:
    w = _int_width(ty)
    if w is None:
        raise Unsupported(
            f"'{_real_name(op)}' on non-integer type '{ty}'"
        )
    return w


def _need_float(ty: str, op) -> int:
    w = _float_width(ty)
    if w is None:
        raise Unsupported(f"'{_real_name(op)}' on non-float type '{ty}'")
    return w


def _const(op, ctx: _Ctx, key: str = "value"):
    attr = _attr(op, key)
    if attr is None:
        raise Unsupported("arith.constant without a value attribute")
    ty = _result_type(op)
    w = _int_width(ty)
    if w is not None:
        inner = getattr(attr, "value", None)
        data = getattr(inner, "data", None)
        if not isinstance(data, int):
            raise Unsupported(f"arith.constant of '{ty}' with a non-integer value")
        return _wrap(data, w)
    w = _float_width(ty)
    if w is not None:
        inner = getattr(attr, "value", None)
        data = getattr(inner, "data", None)
        if not isinstance(data, (int, float)):
            raise Unsupported(f"arith.constant of '{ty}' with a non-float value")
        return _round_float(float(data), w)
    raise Unsupported(f"arith.constant of type '{ty}'")


# arith.cmpi predicate encoding, in the order the enum declares it.
_CMPI = ("eq", "ne", "slt", "sle", "sgt", "sge", "ult", "ule", "ugt", "uge")


def _cmpi(op, ctx: _Ctx) -> int:
    attr = _attr(op, "predicate")
    code = getattr(getattr(attr, "value", None), "data", None)
    if not isinstance(code, int) or not 0 <= code < len(_CMPI):
        raise Unsupported(f"arith.cmpi with predicate {attr}")
    pred = _CMPI[code]
    ty = str(op.operands[0].type)
    w = _need_int(ty, op, ctx)
    a = ctx.get(op.operands[0])
    b = ctx.get(op.operands[1])
    if pred[0] == "u":
        # The engine holds signed values, so an unsigned comparison has
        # to reinterpret both operands at their declared width first.
        a, b = _unsigned(a, w), _unsigned(b, w)
    result = {
        "eq": a == b,
        "ne": a != b,
        "slt": a < b,
        "sle": a <= b,
        "sgt": a > b,
        "sge": a >= b,
        "ult": a < b,
        "ule": a <= b,
        "ugt": a > b,
        "uge": a >= b,
    }[pred]
    return 1 if result else 0


def _bind(op, values: list, ctx: _Ctx) -> None:
    if len(values) != len(op.results):
        raise Unsupported(
            f"'{_real_name(op)}' yields {len(values)} values for "
            f"{len(op.results)} results"
        )
    for res, val in zip(op.results, values):
        ctx.set(res, val)


def _run_block(block, ctx: _Ctx) -> _Term:
    for op in block.ops:
        ctx.tick(op)
        name = _real_name(op)
        if name in _TERMINATORS:
            return _Term(name, [ctx.get(o) for o in op.operands], op)
        _exec(op, name, ctx)
    return _Term("", [], None)


def _run_region(op, index: int, ctx: _Ctx, args: list | None = None) -> _Term:
    if index >= len(op.regions):
        raise Unsupported(f"'{_real_name(op)}' has no region {index}")
    blocks = list(op.regions[index].blocks)
    if not blocks:
        # An omitted `else` region prints as `{}` and runs as a no-op.
        return _Term("", [], None)
    if len(blocks) > 1:
        raise Unsupported(
            f"'{_real_name(op)}' region {index} has unstructured control flow"
        )
    block = blocks[0]
    args = list(args or [])
    bargs = list(block.args)
    if len(bargs) != len(args):
        raise Unsupported(
            f"'{_real_name(op)}' region {index} takes {len(bargs)} arguments, "
            f"{len(args)} supplied"
        )
    for ba, val in zip(bargs, args):
        ctx.set(ba, val)
    return _run_block(block, ctx)


def _expect(term: _Term, want: str, op) -> list:
    if term.name != want:
        got = term.name or "no terminator"
        raise Unsupported(f"'{_real_name(op)}' region ends in {got}, not {want}")
    return term.values


def _exec_if(op, ctx: _Ctx) -> None:
    cond = ctx.get(op.operands[0])
    term = _run_region(op, 0 if cond != 0 else 1, ctx)
    if term.name == "" and not op.results:
        return
    _bind(op, _expect(term, "scf.yield", op), ctx)


def _exec_for(op, ctx: _Ctx) -> None:
    lb, ub, step = (ctx.get(op.operands[i]) for i in range(3))
    w = _need_int(str(op.operands[0].type), op, ctx)
    if step <= 0:
        # The verifier requires a positive step, and honouring anything
        # else here would only invent a loop the language does not have.
        raise Trap(f"scf.for step must be positive, got {step}", ctx.line(op))
    carried = [ctx.get(o) for o in op.operands[3:]]
    iv = lb
    while iv < ub:
        ctx.tick(op)
        term = _run_region(op, 0, ctx, [iv] + carried)
        nxt = _expect(term, "scf.yield", op)
        if len(nxt) != len(carried):
            raise Unsupported(
                f"scf.for body yields {len(nxt)} values for {len(carried)} "
                "iteration arguments"
            )
        carried = nxt
        iv = _wrap(iv + step, w)
    _bind(op, carried, ctx)


def _exec_while(op, ctx: _Ctx) -> None:
    carried = [ctx.get(o) for o in op.operands]
    while True:
        ctx.tick(op)
        before = _expect(_run_region(op, 0, ctx, carried), "scf.condition", op)
        if not before:
            raise Unsupported("scf.condition without a condition operand")
        cond, forwarded = before[0], before[1:]
        if cond == 0:
            _bind(op, forwarded, ctx)
            return
        after = _expect(_run_region(op, 1, ctx, forwarded), "scf.yield", op)
        carried = after


def _exec_index_switch(op, ctx: _Ctx) -> None:
    attr = _attr(op, "cases")
    if attr is None:
        raise Unsupported("scf.index_switch without a cases attribute")
    cases = list(attr.get_values())
    value = ctx.get(op.operands[0])
    # Region 0 is the default; case region j follows case value j.
    index = 0
    for j, c in enumerate(cases):
        if value == c:
            index = j + 1
            break
    term = _run_region(op, index, ctx)
    if term.name == "" and not op.results:
        return
    _bind(op, _expect(term, "scf.yield", op), ctx)


def _exec_load(op, ctx: _Ctx) -> None:
    buf = ctx.get(op.operands[0])
    if not isinstance(buf, _Buf):
        raise Unsupported("memref.load on a value that is not a memref fixture")
    idx = [ctx.get(o) for o in op.operands[1:]]
    ctx.set(op.results[0], buf.data[buf.offset(idx, ctx.line(op))])


def _exec_store(op, ctx: _Ctx) -> None:
    val = ctx.get(op.operands[0])
    buf = ctx.get(op.operands[1])
    if not isinstance(buf, _Buf):
        raise Unsupported("memref.store on a value that is not a memref fixture")
    idx = [ctx.get(o) for o in op.operands[2:]]
    buf.data[buf.offset(idx, ctx.line(op))] = val


def _exec_dataflow_load(op, ctx: _Ctx) -> None:
    """dataflow.load(%memref, %idx..., %ctrl) -> (value, token)."""
    buf = ctx.get(op.operands[0])
    if not isinstance(buf, _Buf):
        raise Unsupported("dataflow.load on a value that is not a memref fixture")
    # The last operand is the control token; the rest are subscripts.
    idx = [ctx.get(o) for o in op.operands[1:-1]]
    ctx.set(op.results[0], buf.data[buf.offset(idx, ctx.line(op))])
    # Control tokens carry no data; the entry block's ctrl argument is
    # bound to None for the same reason.
    for extra in op.results[1:]:
        ctx.set(extra, None)


def _exec_dataflow_store(op, ctx: _Ctx) -> None:
    """dataflow.store(%memref, %idx..., %value, %ctrl) -> token."""
    buf = ctx.get(op.operands[0])
    if not isinstance(buf, _Buf):
        raise Unsupported("dataflow.store on a value that is not a memref fixture")
    val = ctx.get(op.operands[-2])
    idx = [ctx.get(o) for o in op.operands[1:-2]]
    buf.data[buf.offset(idx, ctx.line(op))] = val
    for extra in op.results:
        ctx.set(extra, None)


def _exec(op, name: str, ctx: _Ctx) -> None:
    if name == "arith.constant":
        ctx.set(op.results[0], _const(op, ctx))
        return
    if name == "dataflow.load":
        _exec_dataflow_load(op, ctx)
        return
    if name == "dataflow.store":
        _exec_dataflow_store(op, ctx)
        return
    if name == "dataflow.constant":
        # A graph-entry constant: it takes a control token and produces
        # its `const_value` when fired. Input grammars emit these
        # alongside residual scf, so the input side of a lowering pair
        # is not pure upstream MLIR. Firing is a token-model concern the
        # simulator owns; here the value is all that is observable.
        ctx.set(op.results[0], _const(op, ctx, "const_value"))
        return
    if name in ("arith.addi", "arith.subi", "arith.muli"):
        ty = _result_type(op)
        w = _need_int(ty, op, ctx)
        a, b = ctx.get(op.operands[0]), ctx.get(op.operands[1])
        # Overflow flags (nsw/nuw) declare that overflow does not happen;
        # they do not change the value when it does, so they are ignored.
        raw = a + b if name == "arith.addi" else a - b if name == "arith.subi" else a * b
        ctx.set(op.results[0], _wrap(raw, w))
        return
    if name in ("arith.addf", "arith.subf", "arith.mulf"):
        ty = _result_type(op)
        w = _need_float(ty, op)
        a, b = ctx.get(op.operands[0]), ctx.get(op.operands[1])
        raw = a + b if name == "arith.addf" else a - b if name == "arith.subf" else a * b
        ctx.set(op.results[0], _round_float(raw, w))
        return
    if name in ("arith.andi", "arith.ori", "arith.xori"):
        w = _need_int(_result_type(op), op, ctx)
        # Bitwise ops act on the two's complement bit pattern, so go
        # through the unsigned representation and wrap back.
        a = _unsigned(ctx.get(op.operands[0]), w)
        b = _unsigned(ctx.get(op.operands[1]), w)
        raw = a & b if name == "arith.andi" else a | b if name == "arith.ori" else a ^ b
        ctx.set(op.results[0], _wrap(raw, w))
        return
    if name in ("arith.shli", "arith.shrsi", "arith.shrui"):
        w = _need_int(_result_type(op), op, ctx)
        a, sh = ctx.get(op.operands[0]), ctx.get(op.operands[1])
        if sh < 0 or sh >= w:
            # Shifting by the width or more is poison in MLIR, so there
            # is no value to reproduce.
            raise Unsupported(f"'{name}' by {sh} at width {w} is poison")
        if name == "arith.shli":
            raw = _unsigned(a, w) << sh
        elif name == "arith.shrsi":
            raw = a >> sh  # Python's >> is already arithmetic
        else:
            raw = _unsigned(a, w) >> sh
        ctx.set(op.results[0], _wrap(raw, w))
        return
    if name in ("arith.divsi", "arith.remsi"):
        w = _need_int(_result_type(op), op, ctx)
        a, b = ctx.get(op.operands[0]), ctx.get(op.operands[1])
        if b == 0:
            raise Trap(f"'{name}' by zero", ctx.line(op))
        # MLIR rounds the quotient toward zero and takes the remainder's
        # sign from the dividend. Python floors and takes it from the
        # divisor, so neither operator can be used directly.
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        ctx.set(op.results[0], _wrap(q if name == "arith.divsi" else a - q * b, w))
        return
    if name == "arith.cmpi":
        ctx.set(op.results[0], _cmpi(op, ctx))
        return
    if name == "arith.select":
        cond = ctx.get(op.operands[0])
        ctx.set(op.results[0], ctx.get(op.operands[1 if cond != 0 else 2]))
        return
    if name in ("arith.index_cast", "arith.extsi", "arith.trunci"):
        # All three are a signed reinterpretation at the target width.
        # The engine already holds signed values, so widening is the
        # identity and narrowing is exactly the wrap.
        w = _need_int(_result_type(op), op, ctx)
        ctx.set(op.results[0], _wrap(ctx.get(op.operands[0]), w))
        return
    if name in ("arith.extui", "arith.index_castui"):
        # Unsigned widening reads the SOURCE's bit pattern as a
        # non-negative number, so it needs the source width. Using the
        # signed value here would turn -1 : i32 into -1 rather than
        # 4294967295.
        src = _need_int(str(op.operands[0].type), op, ctx)
        w = _need_int(_result_type(op), op, ctx)
        ctx.set(op.results[0], _wrap(_unsigned(ctx.get(op.operands[0]), src), w))
        return
    if name == "memref.load":
        _exec_load(op, ctx)
        return
    if name == "memref.store":
        _exec_store(op, ctx)
        return
    if name == "scf.if":
        _exec_if(op, ctx)
        return
    if name == "scf.for":
        _exec_for(op, ctx)
        return
    if name == "scf.while":
        _exec_while(op, ctx)
        return
    if name == "scf.index_switch":
        _exec_index_switch(op, ctx)
        return
    if name == "ub.poison":
        # A poison value has no single behaviour to reproduce, and any
        # choice here would be a guess the oracle would then report as
        # the compiler's fault.
        raise Unsupported("'ub.poison' has no defined value to interpret")
    raise Unsupported(f"operation '{name}' is outside the interpreted subset")


# ------------------------------------------------------------ entry point


def _value_result_count(term: _Term, fallback: int) -> int:
    """How many of graph.return's operands are VALUE results.

    `operandSegmentSizes` is `array<i32: nvalue, nstream, nmemory,
    nctrl>` and the value results come first.
    """
    op = term.op
    if op is None:
        return fallback
    attr = _attr(op, "operandSegmentSizes")
    if attr is None:
        return fallback
    try:
        return int(attr.get_values()[0])
    except (AttributeError, IndexError, TypeError, ValueError):
        return fallback


def interpret(
    gop,
    args: dict[int, object],
    memrefs: dict[int, list[object]],
    max_steps: int = DEFAULT_MAX_STEPS,
) -> ExecResult:
    """Execute one graph body.

    `args` and `memrefs` are keyed by function_type input index, exactly
    like loom-dfg-sim's --arg and --memref.
    """
    op = _raw(gop)
    sig = signature(gop)
    if not op.regions:
        raise Unsupported(f"graph '{sig.name}' has no body")
    blocks = list(op.regions[0].blocks)
    if not blocks:
        raise Unsupported(f"graph '{sig.name}' has an empty body")
    block = blocks[0]
    bargs = list(block.args)
    if len(bargs) != len(sig.arg_types) + 1:
        raise Unsupported(
            f"graph '{sig.name}' has {len(bargs)} block arguments for "
            f"{len(sig.arg_types)} function_type inputs"
        )

    ctx = _Ctx(_LINES.get(op, {}), max_steps)
    # Block argument 0 is the implicit control token, which carries no
    # data and no index. Binding it keeps graph.return's ctrl operand
    # readable without a special case.
    ctx.set(bargs[0], None)

    bufs: dict[int, _Buf] = {}
    for i, ty in enumerate(sig.arg_types):
        if ty.startswith("memref<"):
            if i not in memrefs:
                raise Trap(f"no memref fixture for argument {i} ('{ty}')")
            bufs[i] = _make_buf(ty, memrefs[i], i)
            ctx.set(bargs[i + 1], bufs[i])
        else:
            if i not in args:
                raise Trap(f"no value supplied for argument {i} ('{ty}')")
            ctx.set(bargs[i + 1], _coerce(ty, args[i], f"argument {i}"))

    term = _run_block(block, ctx)
    if term.name != "dataflow.graph.return":
        got = term.name or "no terminator"
        raise Unsupported(f"graph '{sig.name}' body ends in {got}")

    n = _value_result_count(term, len(sig.result_types))
    outputs: list[tuple[str, object]] = []
    for k in range(min(n, len(term.values))):
        ty = (
            sig.result_types[k]
            if k < len(sig.result_types)
            else str(term.op.operands[k].type)
        )
        outputs.append((ty, term.values[k]))
    memory = {i: [(b.elt, v) for v in b.data] for i, b in bufs.items()}
    return ExecResult(outputs=outputs, memory=memory)
