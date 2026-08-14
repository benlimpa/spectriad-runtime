"""Shared MLIR AST layer over xdsl (phase 1 of the Loom plan).

One real op/region/block/value AST per side of an observed pair, so
generic predicates (checker/features.py) and agent-written ad-hoc
predicates (checker/adhoc.py) never re-implement parsing. xdsl's
bundled dialects cover the pretty forms of llvm/arith/func/scf/cf/
math/memref; anything else (e.g. Loom's dataflow/fabric dialects)
parses in GENERIC form via allow_unregistered — the runner requests
`--mlir-print-op-generic` output for such units.

xdsl does not record source locations when parsing, so lines are
assigned afterwards by matching each op (in walk order) to the next
plausible text line — same fidelity as checker/mlir_parse.py, which
stays in place for the six legacy units' node-id vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from xdsl.context import Context
from xdsl.dialects import get_all_dialects
from xdsl.dialects.builtin import UnregisteredOp
from xdsl.parser import Parser as XdslParser


class AstError(Exception):
    """The text does not parse; callers surface an honest STUB/ERROR."""


@dataclass
class OpView:
    """One operation, line-annotated and name-normalized."""

    name: str  # full op name, e.g. "arith.addi" (real name for unregistered ops)
    line: int | None  # 1-based source line, None when unmatched
    op: object  # the underlying xdsl operation
    parent_names: list[str] = field(default_factory=list)  # enclosing op names, outermost first

    @property
    def dialect(self) -> str:
        return self.name.split(".", 1)[0]

    @property
    def operand_types(self) -> list[str]:
        return [str(v.type) for v in self.op.operands]

    @property
    def result_types(self) -> list[str]:
        return [str(r.type) for r in self.op.results]

    def prop(self, key: str):
        """Property or attribute value (xdsl attr object), or None."""
        v = self.op.properties.get(key)
        if v is None:
            v = self.op.attributes.get(key)
        return v

    def prop_str(self, key: str) -> str | None:
        v = self.prop(key)
        return None if v is None else str(v)


@dataclass
class Ast:
    """One parsed module side."""

    text: str
    module: object  # xdsl builtin.module op
    ops: list[OpView]  # every op incl. the module wrapper, walk order

    def body_ops(self) -> list[OpView]:
        """Ops except the outer builtin.module wrapper."""
        return [o for o in self.ops if o.name != "builtin.module"]


@dataclass
class AstPair:
    input: Ast
    output: Ast


def _real_name(op) -> str:
    if isinstance(op, UnregisteredOp):
        # generic-form op of a dialect xdsl doesn't know
        return op.op_name.data
    return op.name


# func-dialect ops pretty-print without their dialect prefix.
_BARE = {"func.return": "return", "func.call": "call", "builtin.module": "module"}


def _line_candidates(name: str) -> list[str]:
    cands = [name]
    if name in _BARE:
        cands.append(_BARE[name])
    return cands


def _assign_lines(ops: list[OpView], text: str) -> None:
    """Match ops (walk order) to source lines by scanning forward.

    Walk order and textual order agree for MLIR's nested-region
    syntax; each op consumes the first not-yet-claimed line at or
    after the previous op's line that mentions its name.
    """
    lines = text.splitlines()
    cursor = 0
    for view in ops:
        cands = _line_candidates(view.name)
        for i in range(cursor, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("//"):
                continue
            if any(
                c in stripped or f'"{c}"' in stripped for c in cands
            ):
                view.line = i + 1
                # Printed op order equals walk order, one op per line:
                # the next op always starts strictly below this one.
                cursor = i + 1
                break
        # Ops synthesized by the printer or spanning-form mismatches
        # keep line=None rather than a wrong guess.


_CTX_DIALECTS = None


def _context() -> Context:
    global _CTX_DIALECTS
    if _CTX_DIALECTS is None:
        _CTX_DIALECTS = list(get_all_dialects().items())
    ctx = Context(allow_unregistered=True)
    for name, factory in _CTX_DIALECTS:
        ctx.register_dialect(name, factory)
    return ctx


def parse(text: str) -> Ast:
    """Parse one module (pretty or generic form) into an Ast."""
    try:
        module = XdslParser(_context(), text).parse_module()
    except Exception as e:  # xdsl raises several error types
        raise AstError(f"xdsl cannot parse this MLIR: {e}") from e
    views: list[OpView] = []
    stack_names: dict[int, list[str]] = {}

    def walk(op, parents: list[str]):
        view = OpView(name=_real_name(op), line=None, op=op, parent_names=list(parents))
        views.append(view)
        for region in op.regions:
            for block in region.blocks:
                for child in block.ops:
                    walk(child, parents + [view.name])

    walk(module, [])
    _assign_lines(views, text)
    return Ast(text=text, module=module, ops=views)


def parse_pair(in_text: str, out_text: str) -> AstPair:
    return AstPair(input=parse(in_text), output=parse(out_text))
