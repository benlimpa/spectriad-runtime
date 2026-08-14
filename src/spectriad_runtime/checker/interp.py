"""Concrete interpreter for the corpus MLIR subset.

Makes the output-spec predicates executable: `exec_equiv` and
`deps_preserved` are refuted by running the input and output modules
in the same seeded environment and comparing observable state (the
final contents of every memref argument plus the return value), and
`no_deps_between` is decided by a static per-nest footprint analysis.

The interpreted subset is exactly the dialect vocabulary of the corpus
inputs, the grammar-generated inputs, and the deliverable-2 binaries'
outputs: func.func over memref/f32/index arguments, affine.for with
constant, SSA, affine-map or `min`/`max` multi-result bounds and an
optional non-unit step, affine.parallel, affine.if over an affine_set,
affine.apply, affine.load/store at any affine subscript, arith
constants and f32 arithmetic, arith.index_cast (with real wrap-around
semantics, which is what makes truncation observable), memref.alloc
and memref.dealloc over optionally memory-space-qualified types,
scf.index_switch regions, and unstructured cf.br / cf.switch control
flow. Functions over tensors run through a separate
numpy-backed ONNX engine covering the GroupNorm decomposition
vocabulary (Constant, Reshape, NoValue, LayerNormalization,
GroupNormalization per the opset-21 standard, Mul, Add). Anything
else raises `Unsupported`, which the checker reports as an honestly
labeled STUB verdict rather than a guess.

Probe selection is boundary-driven by the spec's own values: for an
index argument the probes are the input's case values, their 32-bit
truncations (the collision the 2^32 boundary names), and one fresh
non-case value.

STANDING RULING (Ben, 2026-08-05): this subset must NEVER decide which
passes get a unit. A pass emitting something this file cannot execute
is a gap HERE, to be closed by extending this file or by writing an
ad-hoc post-condition that asserts the property without executing. The
affine machinery below was added under that ruling, after four MLIR
passes had been rejected purely for being unreadable here.

Two limitations are deliberate and must not be papered over:

- **affine.parallel runs in ONE deterministic (lexicographic) order,
  so it CANNOT WITNESS A RACE.** An unsound parallelization executes
  here exactly as the sequential nest did. Same class as the sim_equiv
  schedule limitation.
- **memref.dealloc is a no-op** and the buffer stays live, so a
  use-after-free reads stale data instead of trapping.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field


class Unsupported(Exception):
    """Construct outside the interpreted subset."""


class Trap(Exception):
    """Runtime semantic violation (e.g. an out-of-bounds access)."""

    def __init__(self, msg: str, line: int | None = None):
        super().__init__(msg)
        self.line = line


@dataclass
class MemRef:
    shape: list[int]
    data: list[float]

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


@dataclass
class RunResult:
    ret: object
    # Observable buffers by argument position: (position, name, data).
    buffers: list[tuple[int, str, list[float]]]
    # Output lines that stored into each observable buffer (by name).
    store_lines: dict[str, list[int]]
    # Lines of dispatch ops (cf.switch / scf.index_switch) executed.
    dispatch_lines: list[int]


# A memref type, optionally carrying a memory space (`memref<32xf32, 1>`,
# as -affine-data-copy-generate emits for its fast buffers). The memory
# space is captured and then ignored: the interpreter models one flat
# address space, which is sound for the copy-generation subset because
# every space-qualified buffer there is a function-local alloc. A pass
# that made two spaces alias would be outside this model.
MEMREF_T = re.compile(
    r"^memref<([0-9]+(?:x[0-9]+)*)xf32(?:\s*,\s*([^<>]+))?>$"
)
FUNC_RE = re.compile(r"func\.func\s+@[\w$]+\s*\(")
LABEL_RE = re.compile(r"^\^(\w+)(?:\((%[\w#]+):\s*[\w.]+\))?:")
# `affine.for` header, split into iv and the whole bound/step clause. The
# clause is parsed by `_parse_for_header` rather than by regex, because a
# bound may be a multi-result affine map application with nested parens
# (`to min #map1(%arg2)`), which no regex reads correctly.
FOR_RE = re.compile(r"^affine\.for\s+(%[\w#]+)\s*=\s*(.*\S)\s*\{\s*$")
PARALLEL_RE = re.compile(r"^affine\.parallel\s*\(")
AFFINE_IF_RE = re.compile(r"^affine\.if\s+(.*\S)\s*\{\s*$")
AFFINE_APPLY_RE = re.compile(r"^(%[\w#]+)\s*=\s*affine\.apply\s+(.*\S)\s*$")
AFFINE_YIELD_RE = re.compile(r"^affine\.yield\s*$")
ELSE_RE = re.compile(r"^\}\s*else\s*\{\s*$")
DEALLOC_RE = re.compile(r"^memref\.dealloc\s+(%[\w#]+)")
LOAD_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*affine\.load\s+(%[\w#]+)\s*\[([^\]]*)\]"
)
STORE_RE = re.compile(
    r"^affine\.store\s+(%[\w#]+|-?[\d.eE+]+)\s*,\s*(%[\w#]+)\s*\[([^\]]*)\]"
)
CONST_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*arith\.constant\s+(-?[\d][\w.+-]*)\s*:\s*(\w+)"
)
BINF_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*arith\.(addf|subf|mulf|divf)\s+(%[\w#]+)\s*,\s*(%[\w#]+)"
)
NEGF_RE = re.compile(r"^(%[\w#]+)\s*=\s*arith\.negf\s+(%[\w#]+)")
CAST_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*arith\.(index_cast|index_castui|trunci|extsi|extui)"
    r"\s+(%[\w#]+)\s*:\s*\w+\s+to\s+(\w+)"
)
ALLOC_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*memref\.alloc\(\)\s*(?:\{[^}]*\}\s*)?:\s*(memref<[^>]+>)"
)
INDEX_SWITCH_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*scf\.index_switch\s+(%[\w#]+)"
)
CASE_RE = re.compile(r"^case\s+(-?\d+)\s*\{")
DEFAULT_RE = re.compile(r"^default\s*\{")
YIELD_RE = re.compile(r"^scf\.yield\s+(%[\w#]+)")
BR_RE = re.compile(r"^cf\.br\s+\^(\w+)(?:\((%[\w#]+)\s*:\s*[\w.]+\))?")
SWITCH_RE = re.compile(r"^cf\.switch\s+(%[\w#]+)\s*:\s*(\w+)\s*,\s*\[")
RETURN_RE = re.compile(r"^(?:func\.)?return(?:\s+(%[\w#]+))?")

MAX_STEPS = 2_000_000


def _wrap(v: int, bits: int) -> int:
    m = 1 << bits
    v %= m
    return v - m if v >= m >> 1 else v


# --------------------------------------------------------------------------
# Affine expressions, maps and sets.
#
# Every affine construct in the interpreted subset -- loop bounds, load
# and store subscripts, `affine.apply`, `affine.parallel` bound groups and
# `affine.if` conditions -- is an affine expression over SSA values.  The
# three pieces below are a tokenizer, a recursive-descent parser matching
# MLIR's own two precedence levels, and an evaluator.
#
# Semantics follow MLIR's AffineExpr exactly: `floordiv` rounds toward
# negative infinity (Python `//` already does), `ceildiv` is its mirror,
# and `mod` is `a - (a floordiv b) * b`, which is Python `%` for a
# positive divisor.  These matter: tiling emits `ceildiv` in trip-count
# maps and normalization emits `* step + lb`, so getting the rounding
# wrong would make the oracle disagree with a correct compiler.
# --------------------------------------------------------------------------

_TOK_RE = re.compile(r"(%[\w#]+|[A-Za-z_][A-Za-z0-9_]*|\d+|==|>=|<=|[-+*(),:])")


def _tokenize(s: str) -> list[str]:
    toks, i = [], 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        m = _TOK_RE.match(s, i)
        if not m:
            raise Unsupported(f"affine expression: cannot tokenize {s[i:]!r}")
        toks.append(m.group(1))
        i = m.end()
    return toks


class _AffineParser:
    """MLIR's affine grammar: `+ -` low precedence, `* floordiv ceildiv
    mod` high precedence, both left-associative, unary minus binding at
    the operand level."""

    HIGH = ("*", "floordiv", "ceildiv", "mod")

    def __init__(self, toks: list[str]):
        self.t = toks
        self.i = 0

    def peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, expect: str | None = None) -> str:
        v = self.peek()
        if expect is not None and v != expect:
            raise Unsupported(
                f"affine expression: expected {expect!r}, got {v!r}"
            )
        if v is None:
            raise Unsupported("affine expression: unexpected end")
        self.i += 1
        return v

    def expr(self):
        node = self.high()
        while self.peek() in ("+", "-"):
            op = self.take()
            node = (op, node, self.high())
        return node

    def high(self):
        node = self.operand()
        while self.peek() in self.HIGH:
            op = self.take()
            node = (op, node, self.operand())
        return node

    def operand(self):
        tok = self.peek()
        if tok is None:
            raise Unsupported("affine expression: unexpected end")
        if tok == "-":
            self.take()
            return ("neg", self.operand())
        if tok == "(":
            self.take()
            node = self.expr()
            self.take(")")
            return node
        nxt = self.t[self.i + 1] if self.i + 1 < len(self.t) else None
        if tok in ("min", "max") and nxt == "(":
            self.take()
            self.take("(")
            args = [self.expr()]
            while self.peek() == ",":
                self.take()
                args.append(self.expr())
            self.take(")")
            return (tok, args)
        if tok == "symbol" and nxt == "(":
            # `symbol(%s)` marks an operand as a symbol rather than a
            # dim.  That distinction is a legality question for the
            # compiler; for evaluation the value is the same.
            self.take()
            self.take("(")
            node = self.expr()
            self.take(")")
            return node
        self.take()
        if re.fullmatch(r"\d+", tok):
            return ("const", int(tok))
        if tok.startswith("%") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
            return ("id", tok)
        raise Unsupported(f"affine expression: unexpected token {tok!r}")


def _parse_affine_expr(s: str):
    p = _AffineParser(_tokenize(s))
    node = p.expr()
    if p.peek() is not None:
        raise Unsupported(f"affine expression: trailing tokens in {s!r}")
    return node


def _eval_affine(node, lookup) -> int:
    k = node[0]
    if k == "const":
        return node[1]
    if k == "id":
        return int(lookup(node[1]))
    if k == "neg":
        return -_eval_affine(node[1], lookup)
    if k in ("min", "max"):
        vals = [_eval_affine(a, lookup) for a in node[1]]
        return min(vals) if k == "min" else max(vals)
    a = _eval_affine(node[1], lookup)
    b = _eval_affine(node[2], lookup)
    if k == "+":
        return a + b
    if k == "-":
        return a - b
    if k == "*":
        return a * b
    if b == 0:
        raise Trap(f"affine {k} by zero")
    if k == "floordiv":
        return a // b
    if k == "ceildiv":
        return -((-a) // b)
    if k == "mod":
        return a - (a // b) * b
    raise Unsupported(f"affine operator {k!r}")


def _split_top(s: str, sep: str = ",") -> list[str]:
    """Split on `sep` at bracket depth zero.

    `>` closes a bracket only when it is not the tail of the `->` arrow,
    so an inline `affine_map<(d0) -> (d0)>` nests correctly.
    """
    out: list[str] = []
    depth = 0
    cur: list[str] = []
    for i, ch in enumerate(s):
        if ch in "([<{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ">" and not (i and s[i - 1] == "-"):
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return [x.strip() for x in out]


def _strip_outer_parens(s: str) -> str:
    """Remove one enclosing paren pair, but only when the first `(`
    really is matched by the trailing `)`."""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return s
    depth = 0
    for i, ch in enumerate(s):
        depth += (ch == "(") - (ch == ")")
        if depth == 0:
            return s[1:-1].strip() if i == len(s) - 1 else s
    return s


@dataclass
class AffineMap:
    dims: list[str]
    syms: list[str]
    results: list[object]


@dataclass
class AffineSet:
    dims: list[str]
    syms: list[str]
    # (expression, is_equality): equality means `expr == 0`, otherwise
    # the constraint is `expr >= 0`.
    constraints: list[tuple[object, bool]] = field(default_factory=list)


def _parse_dim_sym_lists(lhs: str) -> tuple[list[str], list[str]]:
    m = re.match(r"^\s*\(([^)]*)\)\s*(?:\[([^\]]*)\])?\s*$", lhs)
    if not m:
        raise Unsupported(f"affine map/set operand list {lhs!r}")
    dims = [d.strip() for d in m.group(1).split(",") if d.strip()]
    syms = [s.strip() for s in (m.group(2) or "").split(",") if s.strip()]
    return dims, syms


def _parse_map_body(body: str) -> AffineMap:
    if "->" not in body:
        raise Unsupported(f"affine_map without '->': {body!r}")
    lhs, rhs = body.split("->", 1)
    dims, syms = _parse_dim_sym_lists(lhs)
    results = [
        _parse_affine_expr(r) for r in _split_top(_strip_outer_parens(rhs))
    ]
    return AffineMap(dims, syms, results)


def _parse_set_body(body: str) -> AffineSet:
    parts = _split_top(body, ":")
    if len(parts) != 2:
        raise Unsupported(f"affine_set body {body!r}")
    dims, syms = _parse_dim_sym_lists(parts[0])
    cons: list[tuple[object, bool]] = []
    for raw in _split_top(_strip_outer_parens(parts[1])):
        if not raw:
            continue
        if "==" in raw:
            expr, eq = raw.split("==", 1)[0], True
        elif ">=" in raw:
            expr, eq = raw.split(">=", 1)[0], False
        else:
            raise Unsupported(f"affine_set constraint {raw!r}")
        cons.append((_parse_affine_expr(expr), eq))
    return AffineSet(dims, syms, cons)


AFFINE_MAP_DECL_RE = re.compile(r"^\s*(#[\w$.]+)\s*=\s*affine_map<(.+)>\s*$")
AFFINE_SET_DECL_RE = re.compile(r"^\s*(#[\w$.]+)\s*=\s*affine_set<(.+)>\s*$")


def _parse_affine_attrs(text: str) -> tuple[dict, dict]:
    """Collect the `#map`/`#set` aliases declared in a module preamble."""
    maps: dict[str, AffineMap] = {}
    sets: dict[str, AffineSet] = {}
    for line in text.splitlines():
        m = AFFINE_MAP_DECL_RE.match(line)
        if m:
            maps[m.group(1)] = _parse_map_body(m.group(2))
            continue
        m = AFFINE_SET_DECL_RE.match(line)
        if m:
            sets[m.group(1)] = _parse_set_body(m.group(2))
    return maps, sets


def _read_group(s: str, i: int, opens: str, closes: str) -> tuple[str, int]:
    """Read a balanced `opens`..`closes` group starting at s[i]."""
    if i >= len(s) or s[i] != opens:
        raise Unsupported(f"expected {opens!r} in {s[i:]!r}")
    depth = 0
    for k in range(i, len(s)):
        if s[k] == opens:
            depth += 1
        elif s[k] == closes:
            depth -= 1
            if depth == 0:
                return s[i + 1 : k], k + 1
    raise Unsupported(f"unbalanced {opens!r} in {s!r}")


def _parse_application(text: str):
    """`#map(%a, %b)[%s]` / `affine_map<...>(%a)` / `affine_set<...>(...)`.

    -> (definition_or_alias, dim_arg_texts, sym_arg_texts). The first
    element is the alias string when the application names one, or a
    parsed AffineMap/AffineSet when the map is written inline.
    """
    s = text.strip()
    if s.startswith("#"):
        m = re.match(r"^(#[\w$.]+)", s)
        head, i = m.group(1), m.end()
    elif s.startswith("affine_map<") or s.startswith("affine_set<"):
        kind = s[: s.index("<")]
        body, i = _read_group(s, s.index("<"), "<", ">")
        head = (
            _parse_map_body(body)
            if kind == "affine_map"
            else _parse_set_body(body)
        )
    else:
        raise Unsupported(f"not an affine map/set application: {text!r}")
    while i < len(s) and s[i].isspace():
        i += 1
    dimtext, i = _read_group(s, i, "(", ")")
    while i < len(s) and s[i].isspace():
        i += 1
    symtext = ""
    if i < len(s) and s[i] == "[":
        symtext, i = _read_group(s, i, "[", "]")
    if s[i:].strip():
        raise Unsupported(f"trailing text in application {text!r}")
    dims = [a for a in _split_top(dimtext) if a]
    syms = [a for a in _split_top(symtext) if a]
    return head, dims, syms


def _parse_func(text: str):
    """-> (args [(name, type)], body [(lineno, stripped)], first line)."""
    lines = text.splitlines()
    start = next(
        (i for i, ln in enumerate(lines) if FUNC_RE.search(ln)), None
    )
    if start is None:
        raise Unsupported("no func.func found")
    header = lines[start]
    j = start
    while "{" not in header:
        j += 1
        if j >= len(lines):
            raise Unsupported("unterminated func header")
        header += " " + lines[j]
    argtext = header[header.index("(") + 1 : header.rindex(")")]
    args = []
    for part in filter(None, (p.strip() for p in argtext.split(","))):
        m = re.match(r"(%[\w#]+)\s*:\s*(.+)$", part)
        if not m:
            raise Unsupported(f"argument {part!r}")
        args.append((m.group(1), m.group(2).strip()))
    body: list[tuple[int, str]] = []
    depth = header.count("{") - header.count("}")
    for k in range(j + 1, len(lines)):
        depth += lines[k].count("{") - lines[k].count("}")
        if depth <= 0:
            return args, body, start + 1
        body.append((k + 1, lines[k].strip()))
    raise Unsupported("unterminated func body")


def _split_blocks(body: list[tuple[int, str]]):
    """Split a flat func body into entry + labeled blocks (cf dialect)."""
    blocks: dict[str, list[tuple[int, str]]] = {"^entry": []}
    blockargs: dict[str, str | None] = {"^entry": None}
    cur, depth = "^entry", 0
    for lineno, s in body:
        if depth == 0:
            m = LABEL_RE.match(s)
            if m:
                cur = f"^{m.group(1)}"
                blocks[cur] = []
                blockargs[cur] = m.group(2)
                continue
        blocks[cur].append((lineno, s))
        depth += s.count("{") - s.count("}")
    return blocks, blockargs


def _split_top_kw(s: str, kw: str) -> tuple[str, str] | None:
    """Split around the first ` kw ` occurring at bracket depth zero."""
    target = f" {kw} "
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([<{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ">" and not (i and s[i - 1] == "-"):
            depth -= 1
        if depth == 0 and s.startswith(target, i):
            return s[:i], s[i + len(target) :]
    return None


def _parse_for_header(clause: str, line: int) -> tuple[str, str, int]:
    """`0 to 32 step 4` / `#map(%a) to min #map1(%a)` -> (lb, ub, step)."""
    if "iter_args" in clause:
        raise Unsupported(f"affine.for with iter_args (line {line})")
    split = _split_top_kw(clause, "to")
    if split is None:
        raise Unsupported(f"affine.for bounds {clause!r} (line {line})")
    lb, rest = split
    step = 1
    stepsplit = _split_top_kw(rest, "step")
    if stepsplit is not None:
        rest, steptext = stepsplit
        if not re.fullmatch(r"\d+", steptext.strip()):
            raise Unsupported(f"affine.for step {steptext!r} (line {line})")
        step = int(steptext)
        if step <= 0:
            raise Unsupported(f"affine.for non-positive step (line {line})")
    return lb.strip(), rest.strip(), step


def _parse_parallel_header(s: str, line: int):
    """`affine.parallel (%i, %j) = (0, 0) to (10, 10) step (2, 2) {`."""
    if "reduce" in s:
        raise Unsupported(f"affine.parallel with reductions (line {line})")
    i = len("affine.parallel")

    def skip(j: int) -> int:
        while j < len(s) and s[j].isspace():
            j += 1
        return j

    def word(j: int, w: str) -> int:
        j = skip(j)
        if not s.startswith(w, j):
            raise Unsupported(f"affine.parallel: expected {w!r} (line {line})")
        return j + len(w)

    ivtext, i = _read_group(s, skip(i), "(", ")")
    i = word(i, "=")
    lbtext, i = _read_group(s, skip(i), "(", ")")
    i = word(i, "to")
    ubtext, i = _read_group(s, skip(i), "(", ")")
    steps_text = None
    j = skip(i)
    if s.startswith("step", j):
        steps_text, i = _read_group(s, skip(j + 4), "(", ")")
    if skip(i) != len(s) - 1 or s[-1] != "{":
        raise Unsupported(f"affine.parallel header {s!r} (line {line})")
    ivs = [v for v in _split_top(ivtext) if v]
    lbs = [v for v in _split_top(lbtext) if v]
    ubs = [v for v in _split_top(ubtext) if v]
    steps = (
        [int(v) for v in _split_top(steps_text) if v]
        if steps_text is not None
        else [1] * len(ivs)
    )
    if not (len(ivs) == len(lbs) == len(ubs) == len(steps)):
        raise Unsupported(f"affine.parallel arity mismatch (line {line})")
    for v in ivs:
        if not re.fullmatch(r"%[\w#]+", v):
            raise Unsupported(f"affine.parallel iv {v!r} (line {line})")
    if any(st <= 0 for st in steps):
        raise Unsupported(f"affine.parallel non-positive step (line {line})")
    return ivs, lbs, ubs, steps


def _matching_close(items: list[tuple[int, str]], i: int) -> int:
    depth = 0
    for k in range(i, len(items)):
        depth += items[k][1].count("{") - items[k][1].count("}")
        if depth == 0:
            return k
    raise Unsupported("unbalanced braces")


class _Exec:
    def __init__(
        self,
        env: dict,
        observable: set[str],
        maps: dict | None = None,
        sets: dict | None = None,
    ):
        self.env = env
        self.observable = observable
        self.maps = maps or {}
        self.sets = sets or {}
        self.store_lines: dict[str, list[int]] = {}
        self.dispatch_lines: list[int] = []
        self.steps = 0

    def value(self, name: str, line: int):
        if name not in self.env:
            raise Unsupported(f"undefined value {name} (line {line})")
        return self.env[name]

    # -- affine evaluation -------------------------------------------------

    def _lookup(self, line: int):
        def look(name: str) -> int:
            if not name.startswith("%"):
                raise Unsupported(
                    f"bare identifier {name!r} outside a map body (line {line})"
                )
            return int(self.value(name, line))

        return look

    def eval_expr(self, text: str, line: int) -> int:
        """Evaluate an affine expression whose leaves are SSA values."""
        return _eval_affine(_parse_affine_expr(text), self._lookup(line))

    def _resolve_map(self, head, line):
        if isinstance(head, str):
            if head not in self.maps:
                raise Unsupported(f"unknown affine map {head} (line {line})")
            return self.maps[head]
        return head

    def _resolve_set(self, head, line):
        if isinstance(head, str):
            if head not in self.sets:
                raise Unsupported(f"unknown affine set {head} (line {line})")
            return self.sets[head]
        return head

    def _bind(self, defn, dimargs, symargs, line):
        """Bind a map/set's dim and symbol names to concrete values."""
        if len(dimargs) != len(defn.dims) or len(symargs) != len(defn.syms):
            raise Unsupported(
                f"affine application arity mismatch (line {line})"
            )
        vals = {}
        for name, arg in zip(defn.dims + defn.syms, dimargs + symargs):
            vals[name] = self.eval_expr(arg, line)

        def look(name: str) -> int:
            if name in vals:
                return vals[name]
            if name.startswith("%"):
                return int(self.value(name, line))
            raise Unsupported(f"unbound affine identifier {name!r} (line {line})")

        return look

    def apply_map(self, text: str, line: int) -> list[int]:
        head, dimargs, symargs = _parse_application(text)
        defn = self._resolve_map(head, line)
        look = self._bind(defn, dimargs, symargs, line)
        return [_eval_affine(r, look) for r in defn.results]

    def eval_set(self, text: str, line: int) -> bool:
        head, dimargs, symargs = _parse_application(text)
        defn = self._resolve_set(head, line)
        look = self._bind(defn, dimargs, symargs, line)
        for expr, is_eq in defn.constraints:
            v = _eval_affine(expr, look)
            if (v != 0) if is_eq else (v < 0):
                return False
        return True

    def eval_group(self, text: str, line: int) -> int:
        """One element of an `affine.parallel` bound group.

        The AffineParallelOp printer inlines multi-expression groups as
        `min(e1, e2)` / `max(e1, e2)` rather than as a named map, so the
        expression parser handles them directly; a named map is still
        accepted for robustness.
        """
        s = text.strip()
        if s.startswith("#") or s.startswith("affine_map<"):
            vals = self.apply_map(s, line)
            if len(vals) != 1:
                raise Unsupported(
                    f"multi-result affine.parallel bound map (line {line})"
                )
            return vals[0]
        return self.eval_expr(s, line)

    def eval_bound(self, text: str, line: int, want: str) -> int:
        """A loop bound: a constant, an SSA value, or a (min/max) map."""
        s = text.strip()
        agg = None
        if s.startswith("min ") or s.startswith("min#"):
            agg, s = "min", s[3:].strip()
        elif s.startswith("max ") or s.startswith("max#"):
            agg, s = "max", s[3:].strip()
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        if re.fullmatch(r"%[\w#]+", s):
            return int(self.value(s, line))
        vals = self.apply_map(s, line)
        if not vals:
            raise Unsupported(f"empty bound map (line {line})")
        if len(vals) == 1:
            return vals[0]
        if agg is None:
            # MLIR requires the keyword for a multi-result bound; refusing
            # to guess is the honest behavior.
            raise Unsupported(
                f"multi-result {want} bound without min/max (line {line})"
            )
        return min(vals) if agg == "min" else max(vals)

    def indices(self, raw: str, line: int) -> list[int]:
        out = []
        for part in filter(None, (p.strip() for p in _split_top(raw))):
            if re.fullmatch(r"-?\d+", part):
                out.append(int(part))
            elif re.fullmatch(r"%[\w#]+", part):
                out.append(int(self.value(part, line)))
            else:
                # An affine subscript: `%i + 1`, `%i * 4 + %j`,
                # `symbol(%s)`, `#map(%i)` ...
                if part.startswith("#") or part.startswith("affine_map<"):
                    vals = self.apply_map(part, line)
                    if len(vals) != 1:
                        raise Unsupported(
                            f"multi-result subscript map (line {line})"
                        )
                    out.append(vals[0])
                else:
                    out.append(self.eval_expr(part, line))
        return out

    def run_lines(self, items: list[tuple[int, str]]):
        """-> ('done', None) | ('return', v) | ('br', label, v) | ('yield', v)"""
        i = 0
        while i < len(items):
            self.steps += 1
            if self.steps > MAX_STEPS:
                raise Unsupported("step limit exceeded")
            lineno, s = items[i]
            if not s or s.startswith("//") or s in ("}", "module {"):
                i += 1
                continue

            m = FOR_RE.match(s)
            if m:
                end = _matching_close(items, i)
                iv = m.group(1)
                lbtext, ubtext, step = _parse_for_header(m.group(2), lineno)
                lo = self.eval_bound(lbtext, lineno, "lower")
                hi = self.eval_bound(ubtext, lineno, "upper")
                for v in range(lo, hi, step):
                    self.env[iv] = v
                    act = self.run_lines(items[i + 1 : end])
                    if act[0] != "done":
                        raise Unsupported("control flow escaping affine.for")
                i = end + 1
                continue

            if PARALLEL_RE.match(s):
                end = _matching_close(items, i)
                ivs, lbs, ubs, steps = _parse_parallel_header(s, lineno)
                lo = [self.eval_group(t, lineno) for t in lbs]
                hi = [self.eval_group(t, lineno) for t in ubs]
                # DETERMINISTIC ORDER, DELIBERATELY.  affine.parallel says
                # the iterations MAY run concurrently; this executes them
                # in lexicographic order.  That is a sound choice for a
                # race-free nest and it CANNOT WITNESS A RACE: a body with
                # a loop-carried dependence executes here exactly as the
                # sequential nest did, so `exec_equiv` would report the
                # pair equivalent even though the parallelization is
                # unsound.  Detecting an illegal parallelization needs a
                # dependence check, not this interpreter.
                def sweep(d: int):
                    if d == len(ivs):
                        act = self.run_lines(items[i + 1 : end])
                        if act[0] not in ("done", "yield"):
                            raise Unsupported(
                                "control flow escaping affine.parallel"
                            )
                        return
                    for v in range(lo[d], hi[d], steps[d]):
                        self.env[ivs[d]] = v
                        sweep(d + 1)

                sweep(0)
                i = end + 1
                continue

            m = AFFINE_IF_RE.match(s)
            if m:
                end = _matching_close(items, i)
                then_end, else_start = end, None
                depth = 1
                for k in range(i + 1, end + 1):
                    if depth == 1 and ELSE_RE.match(items[k][1]):
                        then_end, else_start = k, k + 1
                        break
                    depth += items[k][1].count("{") - items[k][1].count("}")
                taken = self.eval_set(m.group(1), lineno)
                if taken:
                    act = self.run_lines(items[i + 1 : then_end])
                elif else_start is not None:
                    act = self.run_lines(items[else_start:end])
                else:
                    act = ("done", None)
                if act[0] not in ("done", "yield"):
                    raise Unsupported("control flow escaping affine.if")
                i = end + 1
                continue

            m = AFFINE_APPLY_RE.match(s)
            if m:
                vals = self.apply_map(m.group(2), lineno)
                if len(vals) != 1:
                    raise Unsupported(
                        f"affine.apply of a multi-result map (line {lineno})"
                    )
                self.env[m.group(1)] = vals[0]
                i += 1
                continue

            if AFFINE_YIELD_RE.match(s):
                # The bare terminator of an affine.for/parallel/if region.
                # A value-carrying `affine.yield %v` belongs to a reduction
                # or an iter_args loop, neither of which is interpreted, so
                # it is deliberately NOT matched here.
                i += 1
                continue

            if DEALLOC_RE.match(s):
                # Freeing a buffer is not observable in this model. The
                # allocation stays live in `env` so a use-after-free would
                # read stale data rather than trap -- recorded as a gap.
                i += 1
                continue

            m = INDEX_SWITCH_RE.match(s)
            if m:
                self.dispatch_lines.append(lineno)
                res_name, flag = m.group(1), int(self.value(m.group(2), lineno))
                j = i + 1
                regions: list[tuple[int | None, int, int]] = []
                while j < len(items):
                    cs = items[j][1]
                    cm, dm = CASE_RE.match(cs), DEFAULT_RE.match(cs)
                    if not (cm or dm):
                        break
                    end = _matching_close(items, j)
                    regions.append(
                        (int(cm.group(1)) if cm else None, j + 1, end)
                    )
                    j = end + 1
                chosen = next(
                    (r for r in regions if r[0] == flag),
                    next((r for r in regions if r[0] is None), None),
                )
                if chosen is None:
                    raise Trap("index_switch matched no region", lineno)
                act = self.run_lines(items[chosen[1] : chosen[2]])
                if act[0] != "yield":
                    raise Unsupported("index_switch region did not yield")
                self.env[res_name] = act[1]
                i = j
                continue

            m = SWITCH_RE.match(s)
            if m:
                self.dispatch_lines.append(lineno)
                flag = int(self.value(m.group(1), lineno))
                buf, j = s, i
                while "]" not in buf and j + 1 < len(items):
                    j += 1
                    buf += " " + items[j][1]
                entries = re.findall(r"(-?\d+)\s*:\s*(\^\w+)", buf)
                dm = re.search(r"default\s*:\s*(\^\w+)", buf)
                # cf.switch compares fixed-width integers, and MLIR
                # prints its case values unsigned: a negative source case
                # value appears here as its 2^64 complement. Both sides
                # are wrapped to the declared width so the comparison is
                # on values, not on spelling.
                bits = 64
                if m.group(2).startswith("i") and m.group(2)[1:].isdigit():
                    bits = int(m.group(2)[1:])
                for val, tgt in entries:
                    if _wrap(int(val), bits) == _wrap(flag, bits):
                        return ("br", tgt, None)
                if not dm:
                    raise Trap("cf.switch matched no case", lineno)
                return ("br", dm.group(1), None)

            m = YIELD_RE.match(s)
            if m:
                return ("yield", self.value(m.group(1), lineno))

            m = BR_RE.match(s)
            if m:
                arg = self.value(m.group(2), lineno) if m.group(2) else None
                return ("br", f"^{m.group(1)}", arg)

            m = RETURN_RE.match(s)
            if m:
                return (
                    "return",
                    self.value(m.group(1), lineno) if m.group(1) else None,
                )

            m = LOAD_RE.match(s)
            if m:
                ref = self.value(m.group(2), lineno)
                if not isinstance(ref, MemRef):
                    raise Unsupported(f"load from non-memref (line {lineno})")
                self.env[m.group(1)] = ref.data[
                    ref.offset(self.indices(m.group(3), lineno), lineno)
                ]
                i += 1
                continue

            m = STORE_RE.match(s)
            if m:
                ref = self.value(m.group(2), lineno)
                if not isinstance(ref, MemRef):
                    raise Unsupported(f"store to non-memref (line {lineno})")
                val = (
                    self.value(m.group(1), lineno)
                    if m.group(1).startswith("%")
                    else float(m.group(1))
                )
                ref.data[
                    ref.offset(self.indices(m.group(3), lineno), lineno)
                ] = float(val)
                if m.group(2) in self.observable:
                    self.store_lines.setdefault(m.group(2), []).append(lineno)
                i += 1
                continue

            m = CONST_RE.match(s)
            if m:
                raw, ty = m.group(2), m.group(3)
                self.env[m.group(1)] = (
                    int(raw) if re.fullmatch(r"-?\d+", raw) else float(raw)
                )
                i += 1
                continue

            m = BINF_RE.match(s)
            if m:
                a = float(self.value(m.group(3), lineno))
                b = float(self.value(m.group(4), lineno))
                op = m.group(2)
                self.env[m.group(1)] = (
                    a + b if op == "addf"
                    else a - b if op == "subf"
                    else a * b if op == "mulf"
                    else a / b
                )
                i += 1
                continue

            m = NEGF_RE.match(s)
            if m:
                self.env[m.group(1)] = -float(self.value(m.group(2), lineno))
                i += 1
                continue

            m = CAST_RE.match(s)
            if m:
                v = int(self.value(m.group(3), lineno))
                target = m.group(4)
                bits = int(target[1:]) if target.startswith("i") else 64
                self.env[m.group(1)] = _wrap(v, bits)
                i += 1
                continue

            m = ALLOC_RE.match(s)
            if m:
                tm = MEMREF_T.match(m.group(2))
                if not tm:
                    raise Unsupported(f"alloc type {m.group(2)!r}")
                shape = [int(d) for d in tm.group(1).split("x")]
                n = 1
                for d in shape:
                    n *= d
                # Deterministic sentinel fill: an uninitialized read is
                # observable, identically in the in and out runs.
                self.env[m.group(1)] = MemRef(
                    shape, [7.5 + 0.001 * k for k in range(n)]
                )
                i += 1
                continue

            raise Unsupported(f"op not interpreted: {s.split(' ')[0]!r} (line {lineno})")
        return ("done", None)


def run(
    text: str, seed: int = 0, index_values: list[int] | None = None
) -> RunResult:
    """Execute the module's function on a seeded environment."""
    args, body, _ = _parse_func(text)
    rng = random.Random(seed)
    env: dict = {}
    observable: list[tuple[int, str, MemRef]] = []
    idx_iter = iter(index_values or [])
    for pos, (name, ty) in enumerate(args):
        tm = MEMREF_T.match(ty)
        if tm:
            shape = [int(d) for d in tm.group(1).split("x")]
            n = 1
            for d in shape:
                n *= d
            ref = MemRef(shape, [rng.uniform(-4.0, 4.0) for _ in range(n)])
            env[name] = ref
            observable.append((pos, name, ref))
        elif ty == "f32":
            env[name] = rng.uniform(-4.0, 4.0)
        elif ty in ("index", "i32", "i64"):
            env[name] = next(idx_iter, 0)
        else:
            raise Unsupported(f"argument type {ty!r}")

    maps, sets = _parse_affine_attrs(text)
    ex = _Exec(env, {name for _, name, _ in observable}, maps, sets)
    blocks, blockargs = _split_blocks(body)
    act = ex.run_lines(blocks["^entry"])
    hops = 0
    while act[0] == "br":
        hops += 1
        if hops > 10_000:
            raise Unsupported("branch limit exceeded")
        _, label, argval = act
        if label not in blocks:
            raise Unsupported(f"branch to unknown block {label}")
        if blockargs.get(label) and argval is not None:
            ex.env[blockargs[label]] = argval
        act = ex.run_lines(blocks[label])
    ret = act[1] if act[0] == "return" else None
    return RunResult(
        ret=ret,
        buffers=[(pos, name, list(ref.data)) for pos, name, ref in observable],
        store_lines=ex.store_lines,
        dispatch_lines=ex.dispatch_lines,
    )


# --------------------------------------------------------------------------
# ONNX tensor engine (numpy-backed): the GroupNorm decomposition subset.
# --------------------------------------------------------------------------

TENSOR_T = re.compile(r"^tensor<([0-9]+(?:x[0-9]+)*)xf32>$")
# Generic onnx op, possibly multi-result, with either <{...}> or {...}
# attributes: `%a, %b = "onnx.Op"(args) <{attrs}> : type`. This is the
# form the real onnx-mlir-opt emits for everything except Constant.
ONNX_OP_RE = re.compile(
    r'^((?:%[\w#]+)(?:\s*,\s*%[\w#]+)*)\s*=\s*"onnx\.(\w+)"\((.*?)\)'
    r"\s*(?:<\{(.*?)\}>|\{(.*?)\})?\s*:"
)
# onnx-mlir prints Constant in pretty form: `%c = onnx.Constant dense<..>
# : tensor<..>`. The dense payload is either a scalar splat (`dense<2>`)
# or an array (`dense<[2, -1]>`).
ONNX_CONST_RE = re.compile(
    r"^(%[\w#]+)\s*=\s*onnx\.Constant\s+dense<(.+?)>\s*:\s*tensor<([^>]*)>"
)


def _is_tensor_func(text: str) -> bool:
    try:
        args, _, _ = _parse_func(text)
    except Unsupported:
        return False
    return any(TENSOR_T.match(ty) or ty == "none" for _, ty in args)


def _tensor_shape(ty: str, line: int | None):
    m = TENSOR_T.match(ty.strip())
    if not m:
        raise Unsupported(f"tensor type {ty!r} (line {line})")
    return [int(d) for d in m.group(1).split("x")]


def _type_numel(tystr: str) -> int:
    """Element count of an inner tensor type body like '2xi64' or 'i64'."""
    dims = [p for p in tystr.split("x") if p and p[0].isdigit()]
    n = 1
    for d in dims:
        n *= int(d)
    return n


def _result_fshape(line: str) -> list[int] | None:
    """Static shape of an op's first f32 result type (`-> tensor<..xf32>`).

    In typed MLIR the result type is authoritative: onnx-mlir lowers to
    it, and it is what shape inference already resolved. So Reshape /
    Unsqueeze honor this over their (sometimes inconsistent) runtime
    shape operand -- e.g. the real fixed GroupNorm decomposition emits a
    scale Reshape whose shape operand is [NG, NG, 1] but whose result
    type is the correct [NG, C/NG, 1] (they coincide only when C = NG**2,
    as in the c4-g2 example).
    """
    m = re.search(r"->\s*\(?\s*tensor<([0-9x]+)xf32>", line)
    if not m:
        return None
    return [int(d) for d in m.group(1).split("x") if d.isdigit()]


def _run_onnx(text: str, seed: int):
    """Execute a tensor-typed function; returns (array, producing line).

    Covers the onnx op vocabulary of the GroupNorm decomposition as the
    real onnx-mlir-opt emits it: Constant (scalar/array), Shape, Concat,
    Reshape (runtime target, -1 inference), Unsqueeze, multi-result
    LayerNormalization, plus the GroupNormalization reference on the
    input side. Anything else raises Unsupported (honest STUB upstream).
    """
    import numpy as np

    args, body, _ = _parse_func(text)
    rng = random.Random(seed)
    env: dict = {}
    for name, ty in args:
        shape = _tensor_shape(ty, None)
        n = 1
        for d in shape:
            n *= d
        env[name] = np.array(
            [rng.uniform(-4.0, 4.0) for _ in range(n)], dtype=np.float64
        ).reshape(shape)
    lines_of: dict[str, int] = {}

    def val(name: str, line: int):
        if name not in env:
            raise Unsupported(f"undefined value {name} (line {line})")
        return env[name]

    for lineno, s in body:
        if not s or s.startswith("//") or s in ("}", "module {"):
            continue

        m = RETURN_RE.match(s)
        if m:
            if not m.group(1):
                raise Unsupported(f"tensor func returns nothing (line {lineno})")
            return val(m.group(1), lineno), lines_of.get(m.group(1), lineno)

        cm = ONNX_CONST_RE.match(s)
        if cm:
            res, dense, tystr = cm.groups()
            dense = dense.strip()
            if dense.startswith("["):
                vals = [int(x) for x in dense[1:-1].split(",") if x.strip()]
            else:
                vals = [int(dense)] * _type_numel(tystr)
            env[res] = np.array(vals, dtype=np.int64)
            lines_of[res] = lineno
            continue

        m = ONNX_OP_RE.match(s)
        if not m:
            raise Unsupported(f"op not interpreted: {s.split(' ')[0]!r} (line {lineno})")
        results_raw, op, rawargs, attrs1, attrs2 = m.groups()
        res = results_raw.split(",")[0].strip()  # primary result (e.g. Y)
        attrs = attrs1 or attrs2 or ""
        opargs = [a.strip() for a in rawargs.split(",") if a.strip()]
        lines_of[res] = lineno

        if op == "Constant":
            dm = re.search(r"dense<\[?([^\]>]*)\]?>", s)
            if not dm:
                raise Unsupported(f"non-array onnx.Constant (line {lineno})")
            env[res] = np.array(
                [int(x) for x in dm.group(1).split(",") if x.strip()],
                dtype=np.int64,
            )
        elif op == "NoValue":
            env[res] = None
        elif op == "Shape":
            x = val(opargs[0], lineno)
            sm = re.search(r"start\s*=\s*(-?\d+)", attrs)
            em = re.search(r"end\s*=\s*(-?\d+)", attrs)
            start = int(sm.group(1)) if sm else 0
            end = int(em.group(1)) if em else x.ndim
            env[res] = np.array(x.shape[start:end], dtype=np.int64)
        elif op == "Concat":
            am = re.search(r"axis\s*=\s*(-?\d+)", attrs)
            axis = int(am.group(1)) if am else 0
            env[res] = np.concatenate(
                [np.atleast_1d(val(a, lineno)) for a in opargs], axis=axis
            )
        elif op in ("Reshape", "Unsqueeze"):
            # Both reshape the data; the authoritative target is the
            # declared f32 result type (see _result_fshape). A count
            # mismatch means the op is malformed for this input -- the
            # buggy GroupNorm build's per-group Unsqueeze declares
            # [NG, 1, 1] (num_groups elements) for a C-element scale.
            data = val(opargs[0], lineno)
            rshape = _result_fshape(s)
            if rshape is None:  # fall back to the runtime shape operand
                rshape = [
                    int(x) for x in np.atleast_1d(val(opargs[1], lineno))
                ]
            known = [d for d in rshape if d >= 0]
            prod = 1
            for d in known:
                prod *= d
            if -1 not in rshape and prod != data.size:
                raise Trap(
                    f"{op.lower()} of {data.size} elements to result shape"
                    f" {rshape} (num_groups vs channel mismatch)",
                    lineno,
                )
            env[res] = data.reshape(rshape)
        elif op in ("Mul", "Add"):
            a, b = val(opargs[0], lineno), val(opargs[1], lineno)
            try:
                env[res] = a * b if op == "Mul" else a + b
            except ValueError:
                raise Trap(f"operands not broadcastable (line {lineno})", lineno)
        elif op == "LayerNormalization":
            x = val(opargs[0], lineno)
            am = re.search(r"axis\s*=\s*(-?\d+)", attrs)
            em = re.search(r"epsilon\s*=\s*([\d.eE+-]+)", attrs)
            axis = int(am.group(1)) if am else -1
            if axis < 0:
                axis += x.ndim
            eps = float(em.group(1)) if em else 1e-5
            axes = tuple(range(axis, x.ndim))
            mean = x.mean(axis=axes, keepdims=True)
            var = x.var(axis=axes, keepdims=True)
            y = (x - mean) / np.sqrt(var + eps)
            scale = val(opargs[1], lineno) if len(opargs) > 1 else None
            bias = val(opargs[2], lineno) if len(opargs) > 2 else None
            try:
                if scale is not None:
                    y = y * scale
                if bias is not None:
                    y = y + bias
            except ValueError:
                raise Trap(
                    "scale/bias not broadcastable to the normalized shape"
                    f" (line {lineno})",
                    lineno,
                )
            env[res] = y
        elif op == "GroupNormalization":
            # ONNX opset-21 reference semantics: statistics per group,
            # scale and bias applied per channel (shape (C)).
            x = val(opargs[0], lineno)
            scale, bias = val(opargs[1], lineno), val(opargs[2], lineno)
            gm = re.search(r"num_groups\s*=\s*(\d+)", attrs)
            em = re.search(r"epsilon\s*=\s*([\d.eE+-]+)", attrs)
            if not gm:
                raise Unsupported(f"GroupNormalization without num_groups (line {lineno})")
            g, eps = int(gm.group(1)), float(em.group(1)) if em else 1e-5
            n, c = x.shape[0], x.shape[1]
            if c % g or scale.size != c or bias.size != c:
                raise Trap(
                    f"scale/bias size {scale.size} does not match channel"
                    f" count {c} (num_groups {g})",
                    lineno,
                )
            xg = x.reshape(n, g, -1)
            mean = xg.mean(axis=2, keepdims=True)
            var = xg.var(axis=2, keepdims=True)
            xhat = ((xg - mean) / np.sqrt(var + eps)).reshape(x.shape)
            bshape = [1, c] + [1] * (x.ndim - 2)
            env[res] = xhat * scale.reshape(bshape) + bias.reshape(bshape)
        else:
            raise Unsupported(f"onnx.{op} not interpreted (line {lineno})")
    raise Unsupported("tensor func has no return")


def _equivalent_onnx(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    import numpy as np

    runs = 0
    for seed in (11, 12):
        try:
            a, _ = _run_onnx(in_text, seed)
        except Trap as t:
            raise Unsupported(f"input module traps: {t}")
        try:
            b, out_line = _run_onnx(out_text, seed)
        except Trap as t:
            return False, f"output traps ({t}) on seed {seed}", (
                [t.line] if t.line else []
            )
        runs += 1
        if a.shape != b.shape or not np.allclose(a, b, rtol=1e-5, atol=1e-6):
            return (
                False,
                f"returned tensor differs on seed {seed}",
                [out_line],
            )
    return True, f"observably equivalent on {runs} concrete runs", []


def _probes(in_text: str) -> list[list[int]]:
    """Boundary-driven probe values for the input's index arguments.

    The probes come from the spec side of the pair: the input's own
    case values, each value's 32-bit truncation (the collision the
    2^32 boundary names), and one fresh non-case value.
    """
    args, _, _ = _parse_func(in_text)
    n_index = sum(1 for _, ty in args if ty in ("index", "i32", "i64"))
    if n_index == 0:
        return [[]]
    cases = [int(v) for v in re.findall(r"^\s*case\s+(-?\d+)", in_text, re.M)]
    values: list[int] = []
    for v in cases:
        for cand in (v, _wrap(v, 32) % (1 << 32)):
            if cand not in values:
                values.append(cand)
    fresh = (max(cases) if cases else 0) + 7
    values.append(fresh)
    return [[v] * n_index for v in values]


def equivalent(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    """Concretely compare observable behavior of an input/output pair.

    -> (equal, detail, blamed output lines). Raises Unsupported when
    either module leaves the interpreted subset.
    """
    if _is_tensor_func(in_text):
        return _equivalent_onnx(in_text, out_text)
    probes = _probes(in_text)
    runs = 0
    for seed in (11, 12):
        for iv in probes:
            try:
                a = run(in_text, seed, iv)
            except Trap as t:
                raise Unsupported(f"input module traps: {t}")
            try:
                b = run(out_text, seed, iv)
            except Trap as t:
                return (
                    False,
                    f"output traps ({t}) on seed {seed}"
                    + (f", index args {iv}" if iv else ""),
                    [t.line] if t.line else [],
                )
            runs += 1
            probe_desc = f"seed {seed}" + (f", index args {iv}" if iv else "")
            ra, rb = a.ret, b.ret
            if (ra is None) != (rb is None) or (
                ra is not None and abs(float(ra) - float(rb)) > 1e-9
            ):
                return (
                    False,
                    f"return value differs on {probe_desc}: {ra} vs {rb}",
                    sorted(set(b.dispatch_lines)),
                )
            for (pos, name_a, da), (_, name_b, db) in zip(
                a.buffers, b.buffers
            ):
                if len(da) != len(db) or any(
                    abs(x - y) > 1e-6 * max(1.0, abs(x)) for x, y in zip(da, db)
                ):
                    return (
                        False,
                        f"memref argument {pos} ({name_b}) differs on"
                        f" {probe_desc}",
                        sorted(set(b.store_lines.get(name_b, []))),
                    )
    return True, f"observably equivalent on {runs} concrete runs", []


def nest_footprints(text: str) -> list[dict]:
    """Static read/write footprints of each top-level affine nest."""
    _, body, _ = _parse_func(text)
    nests = []
    depth = 0
    current: dict | None = None
    for lineno, s in body:
        if depth == 0 and FOR_RE.match(s):
            current = {"reads": set(), "writes": set(), "line": lineno}
            nests.append(current)
        if current is not None:
            lm = re.search(r"affine\.load\s+(%[\w#]+)\s*\[", s)
            if lm:
                current["reads"].add(lm.group(1))
            sm = re.search(r"affine\.store\s+[^,]+,\s*(%[\w#]+)\s*\[", s)
            if sm:
                current["writes"].add(sm.group(1))
        depth += s.count("{") - s.count("}")
        if depth == 0:
            current = None
    return nests


def no_deps_between(text: str) -> tuple[bool, str]:
    """No memref dependence between any two top-level affine nests.

    Memref-granularity (no index analysis): a dependence exists when
    one nest writes a memref another nest reads or writes.
    """
    nests = nest_footprints(text)
    for i in range(len(nests)):
        for j in range(i + 1, len(nests)):
            a, b = nests[i], nests[j]
            conflicts = (
                (a["writes"] & (b["reads"] | b["writes"]))
                | (b["writes"] & a["reads"])
            )
            if conflicts:
                return (
                    False,
                    f"nests at input lines {a['line']} and {b['line']} share"
                    f" dependences through {', '.join(sorted(conflicts))}",
                )
    return True, f"no memref dependences among {len(nests)} input nests"
