"""Value provenance: where does an operand actually come from?

Most constraints in the corpus check
that operations of the expected kinds and counts exist. They do not
check that those operations are WIRED to the right values, and the
mutation experiments made the cost concrete: swapping a loop's lower and
upper bound, or swapping a selection's true and false lanes, leaves
every count and every type intact, so nothing fires.

The primitive here is an ORIGIN TERM: a canonical string naming the
computation that produced a value, resolved through the def-use graph
and independent of SSA names. Two values in two different modules have
the same origin term when they were computed the same way from the same
roots. That makes cross-module comparison possible without matching
value names, which never survive a real transformation.

    %c1 = arith.constant 1 : i64        ->  const(1 : i64)
    %n  = arith.addi %iv, %c1 : i64     ->  arith.addi(arg0@scf.while, const(1 : i64))

Recursion stops at BLOCK ARGUMENTS, rendered as `arg<i>@<owning op>`.
That is deliberate. A block argument is where a value enters a region,
so it is exactly the right boundary: a function argument keeps its
identity across a transformation that preserves signatures, while a loop
body argument is honestly a DIFFERENT root in `scf.for` than it was in
`scf.while`, and the term says so. It also makes the walk terminate on
loop-carried cycles without a visited set.

`depth` bounds pathological nesting. An elided subterm prints as `...`,
which never compares equal to a resolved one, so a truncated comparison
fails closed instead of silently matching.
"""

from __future__ import annotations

from .ast import Ast, OpView, _real_name

import re

DEFAULT_DEPTH = 8

# `const(0 : i32)` and `const(0 : index)` name the same number. A pass
# that converts an induction type rewrites the literal's type without
# changing the value, so a provenance comparison across such a rewrite
# has to compare the number.
_INT_CONST = re.compile(r"const\((-?\d+) : (?:i\d+|index|si\d+|ui\d+)\)")


def untyped_ints(term: str) -> str:
    """Origin term with integer constant literals stripped of their type."""
    return _INT_CONST.sub(r"const(\1)", term)

# Attribute holding a constant's value, across the dialects in the corpus
# (arith.constant, llvm.mlir.constant, and generic-form equivalents).
_VALUE_KEYS = ("value",)


def _attr(op, key: str):
    v = op.properties.get(key)
    if v is None:
        v = op.attributes.get(key)
    return v


def _const_value(op) -> str | None:
    """The literal of a constant-like op, or None if it is not one."""
    if len(op.operands) != 0 or len(op.results) != 1:
        return None
    for key in _VALUE_KEYS:
        v = _attr(op, key)
        if v is not None:
            return str(v)
    return None


def origin(value, depth: int = DEFAULT_DEPTH) -> str:
    """Canonical origin term for one SSA value."""
    if depth <= 0:
        return "..."
    owner = value.owner
    # Block argument: a region boundary, and the natural root.
    if not hasattr(owner, "operands"):
        parent = owner.parent_op() if hasattr(owner, "parent_op") else None
        pname = _real_name(parent) if parent is not None else "?"
        return f"arg{getattr(value, 'index', '?')}@{pname}"
    lit = _const_value(owner)
    if lit is not None:
        return f"const({lit})"
    args = ",".join(origin(o, depth - 1) for o in owner.operands)
    name = _real_name(owner)
    if len(owner.results) > 1:
        return f"{name}#{value.index}({args})"
    return f"{name}({args})"


def operand_origins(
    view: OpView, count: int | None = None, depth: int = DEFAULT_DEPTH
) -> list[str]:
    """Origin terms of an operation's operands, in order.

    `count` takes a prefix, which is what comparing loop bounds across a
    rewrite needs: `scf.for` and `scf.forall` agree on lower bound, upper
    bound and step in the first three operand positions and then diverge
    on iteration arguments versus shared outputs.
    """
    ops = list(view.op.operands)
    if count is not None:
        ops = ops[:count]
    return [origin(o, depth) for o in ops]


def result_origins(view: OpView, depth: int = DEFAULT_DEPTH) -> list[str]:
    return [origin(r, depth) for r in view.op.results]


def _props(op) -> str:
    """Sorted properties and attributes as a stable string.

    This is what makes a comparison-predicate change visible: the `sle`
    in `arith.cmpi sle` is a property, not an operand, so an operation
    whose guard was rewritten is not the operation that was there before.
    """
    items = {}
    for src in (op.properties, op.attributes):
        for k, v in src.items():
            items[str(k)] = str(v)
    return ",".join(f"{k}={items[k]}" for k in sorted(items))


def _canon_op(op, depth: int) -> str:
    args = ",".join(origin(o, depth) for o in op.operands)
    types = ",".join(str(r.type) for r in op.results)
    body = ""
    if op.regions:
        # Region contents are part of an operation's identity. Without
        # them a rewritten loop guard is invisible, because the predicate
        # of an `arith.cmpi` inside the body is not an operand or a
        # property of the enclosing loop.
        inner = []
        for region in op.regions:
            for block in region.blocks:
                for child in block.ops:
                    # Constant definitions are skipped. Their literal is
                    # already inlined into every consumer's origin term,
                    # so they carry no information here, and a pattern
                    # driver is free to hoist a loop-invariant constant
                    # out of a region it did not otherwise touch. Keeping
                    # them would report that hoist as a rewrite of the
                    # enclosing op, which it is not.
                    if _const_value(child) is not None:
                        continue
                    inner.append(_canon_op(child, depth))
        body = " {" + "; ".join(inner) + "}"
    return f"{_real_name(op)}({args}) -> [{types}] {{{_props(op)}}}{body}"


def canon(view: OpView, depth: int = DEFAULT_DEPTH) -> str:
    """Structural identity of one operation, modulo SSA naming.

    Name, operand origins, result types, properties, and the same for
    everything in its regions. Two operations with the same canonical
    form compute the same thing from the same roots, whatever their
    values are called.
    """
    return _canon_op(view.op, depth)


def canon_counts(ast: Ast, views: list[OpView], depth: int = DEFAULT_DEPTH):
    """Multiset of canonical forms, with a representative line each."""
    from collections import Counter

    counts: Counter = Counter()
    lines: dict[str, int] = {}
    for v in views:
        c = canon(v, depth)
        counts[c] += 1
        if v.line is not None:
            lines.setdefault(c, v.line)
    return counts, lines


def defining_op(value):
    """The operation that produced a value, or None for a block argument.

    Predicates run under a restricted builtin set with no `hasattr`, so
    the owner discrimination belongs here rather than in generated code.
    """
    owner = getattr(value, "owner", None)
    return owner if hasattr(owner, "operands") else None


def op_name(op) -> str:
    """Real op name of a RAW xdsl operation.

    Ad-hoc predicates get `OpView`s for the top-level walk but raw
    operations when they descend into regions themselves, and an
    unregistered generic-form op does not report its name through the
    ordinary attribute.
    """
    return _real_name(op)


def child_ops(op, region: int = 0, block: int = 0) -> list:
    """Raw operations directly inside one of an operation's regions."""
    if region >= len(op.regions):
        return []
    blocks = list(op.regions[region].blocks)
    if block >= len(blocks):
        return []
    return list(blocks[block].ops)


def entry_block(op, region: int = 0):
    """The first block of one of an operation's regions, or None."""
    if region >= len(op.regions):
        return None
    blocks = list(op.regions[region].blocks)
    return blocks[0] if blocks else None


def enclosing_symbol(view: OpView) -> str | None:
    """Name of the function-like operation an operation sits in.

    Scoping a provenance check to one function is what keeps a module of
    several independent test functions from comparing across them.
    """
    op = getattr(view, "op", view)  # accepts an OpView or a raw operation
    while op is not None:
        parent = op.parent_op() if hasattr(op, "parent_op") else None
        if parent is None:
            return None
        sym = _attr(parent, "sym_name")
        if sym is not None:
            return str(sym).strip('"')
        op = parent
    return None
