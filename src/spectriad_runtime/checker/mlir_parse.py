"""Lightweight structural MLIR parser for the PTC-subset checker.

This is NOT a full MLIR parser. It extracts the structure the specs in
the corpus reference, and emits a generic node tree whose node ids
match the semantic ids used in the paper's specification sketches
(index_switch, case_value, cf_switch, group_norm, scale_reshape, ...).
Replacing this with a real grammar (tree-sitter-mlir) plus an
id-aliasing layer is the documented upgrade path.

Every node carries the 1-based source line it was extracted from, so
a failing constraint can localize the lines it binds to in the
observed output (the UI highlights those, not hand-curated ones).

Node ids emitted:
  module            root
  op                every operation (text = full op name, e.g. "scf.for")
  scf_op            alias for ops in the scf dialect
  index_switch      scf.index_switch (children: case_value, case_region,
                    default_region)
  cf_switch         cf.switch (children: case_value, case_target,
                    default_target, flag_type)
  group_norm        onnx.GroupNormalization (children: num_groups,
                    channel_dim, scale_ssa)
  affine_for        top-level affine.for nests
  affine_loop_depth lexical nesting depth of each affine.for
  store_target      destination SSA value of each affine.store
  private_buf       memref.alloc (children: name, size, out_of_bounds)

Synthesized relative to the paired input (output trees only):
  fused_nest        the single output nest a pair of input sibling
                    nests became (correspondence-rule trigger)
  scale_reshape     onnx.Reshape whose first operand is the scale value
                    of a group_norm in the input (children: target_dim)
  orig_buf_use      a use, in this tree, of a buffer the input alloc'd
                    at a type this tree no longer allocs it at
                    (contraction check)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    text: str = ""
    line: int | None = None
    children: list["Node"] = field(default_factory=list)

    def add(self, id: str, text: str = "", line: int | None = None) -> "Node":
        n = Node(id, text, line)
        self.children.append(n)
        return n

    def descendants(self) -> list["Node"]:
        out = []
        stack = list(self.children)
        while stack:
            n = stack.pop(0)
            out.append(n)
            stack.extend(n.children)
        return out


# Op names are dialect-qualified (scf.for) except func-dialect ops in
# pretty form, which print bare: `return %0 : f32`, `call @f(...)`.
OP_RE = re.compile(
    r'(?:%[\w#]+(?:\s*,\s*%[\w#]+)*\s*=\s*)?"?([a-z_]+\.[\w.]+|return\b|call\b)"?'
)
CASE_RE = re.compile(r"^\s*case\s+(-?\d+)\b")
DEFAULT_BLOCK_RE = re.compile(r"^\s*default\s*\{")
SWITCH_CASE_RE = re.compile(r"(-?\d+)\s*:\s*(\^\w+)")
SWITCH_DEFAULT_RE = re.compile(r"default\s*:\s*(\^\w+)")
ALLOC_RE = re.compile(r"(%[\w#]+)\s*=\s*memref\.alloc\(\)\s*:\s*(memref<[^>]+>)")
STORE_RE = re.compile(r"affine\.store\s+[^,]+,\s*(%[\w#]+)\[([^]]+)\]")
LOAD_RE = re.compile(r"affine\.load\s+(%[\w#]+)\s*\[")


def _first_nonunit_dim(type_str: str) -> str | None:
    m = re.search(r"(?:tensor|memref)<([\dx?]+)", type_str)
    if not m:
        return None
    dims = m.group(1).split("x")
    for d in dims:
        if d.isdigit() and d != "1":
            return d
    return dims[0] if dims and dims[0].isdigit() else None


def _numel(type_str: str) -> int:
    """Total static element count of a tensor/memref type (unknown dims
    treated as 1)."""
    m = re.search(r"(?:tensor|memref)<([\dx?]+)", type_str)
    if not m:
        return 0
    n = 1
    for d in m.group(1).split("x"):
        if d.isdigit():
            n *= int(d)
    return n


def _func_header(text: str) -> str:
    """The func.func signature substring (up to its opening brace)."""
    m = re.search(r"func\.func\b.*?\{", text, re.DOTALL)
    return m.group(0) if m else ""


def parse(text: str, paired_input: str | None = None) -> Node:
    """Parse MLIR text into a semantic node tree.

    paired_input: the input-side MLIR text, needed for output-tree
    nodes synthesized relative to the input (fused_nest,
    scale_reshape, orig_buf_use).
    """
    root = Node("module")
    lines = text.splitlines()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        m = (
            OP_RE.match(stripped)
            if stripped and not stripped.startswith("//")
            else None
        )
        opname = m.group(1) if m else None

        if opname == "scf.index_switch":
            n = root.add("index_switch", opname, i + 1)
            root.add("op", opname, i + 1)
            root.add("scf_op", opname, i + 1)
            # Consume the case/default region blocks that follow.
            j, depth = i + 1, 0
            while j < len(lines):
                s = lines[j]
                if depth == 0:
                    cm = CASE_RE.match(s)
                    if cm:
                        n.add("case_value", cm.group(1), j + 1)
                        n.add("case_region", cm.group(1), j + 1)
                    elif DEFAULT_BLOCK_RE.match(s):
                        n.add("default_region", "default", j + 1)
                    elif s.strip():
                        break  # first non-case line after the regions
                depth += s.count("{") - s.count("}")
                j += 1
            i = j
            continue

        if opname == "cf.switch":
            n = root.add("cf_switch", opname, i + 1)
            root.add("op", opname, i + 1)
            tm = re.search(r":\s*(\w+)\s*,", stripped)
            if tm:
                n.add("flag_type", tm.group(1), i + 1)
            # The case list may span several lines up to the closing ].
            buf, j = stripped, i
            while "]" not in buf and j + 1 < len(lines):
                j += 1
                buf += " " + lines[j].strip()
            # Per-line scan first so each case keeps its own line; fall
            # back to the joined text for cases split across lines.
            found = False
            for k in range(i, j + 1):
                for val, tgt in SWITCH_CASE_RE.findall(lines[k]):
                    n.add("case_value", val, k + 1)
                    n.add("case_target", tgt, k + 1)
                    found = True
                dm = SWITCH_DEFAULT_RE.search(lines[k])
                if dm:
                    n.add("default_target", dm.group(1), k + 1)
            if not found:
                for val, tgt in SWITCH_CASE_RE.findall(buf):
                    n.add("case_value", val, i + 1)
                    n.add("case_target", tgt, i + 1)
            i = j + 1
            continue

        if opname == "onnx.GroupNormalization":
            n = root.add("group_norm", opname, i + 1)
            root.add("op", opname, i + 1)
            gm = re.search(r"num_groups\s*=\s*(\d+)", stripped)
            if gm:
                n.add("num_groups", gm.group(1), i + 1)
            # channel_dim = element count of the scale operand type (the
            # second tensor type on the line): C for a per-channel scale.
            # Compared against the decomposition's scale_reshape
            # target_dim (also an element count) to test granularity.
            types = re.findall(r"tensor<[^>]+>", stripped)
            if len(types) >= 2:
                n.add("channel_dim", str(_numel(types[1])), i + 1)
            args = re.search(r"\(\s*(%[\w#]+)\s*,\s*(%[\w#]+)", stripped)
            if args:
                n.add("scale_ssa", args.group(2), i + 1)
            i += 1
            continue

        if opname:
            root.add("op", opname, i + 1)
            if opname.startswith("scf."):
                root.add("scf_op", opname, i + 1)
            if opname == "memref.alloc":
                am = ALLOC_RE.search(stripped)
                if am:
                    b = root.add("private_buf", am.group(2), i + 1)
                    b.add("name", am.group(1), i + 1)
                    d = _first_nonunit_dim(am.group(2))
                    b.add("size", d if d else "?", i + 1)
        sm = STORE_RE.search(stripped)
        if sm:
            root.add("store_target", sm.group(1), i + 1)
        i += 1

    # Record affine-loop nesting depth. Absolute depth differs with
    # wrapping (module/func), so top-level nests are those at the
    # minimum depth, and the correspondence rule compares depth spreads.
    depth = 0
    affine_fors: list[tuple[int, int]] = []
    for lineno, line in enumerate(lines, start=1):
        if line.strip().startswith("affine.for"):
            affine_fors.append((depth, lineno))
            root.add("affine_loop_depth", str(depth), lineno)
        depth += line.count("{") - line.count("}")
    if affine_fors:
        min_depth = min(d for d, _ in affine_fors)
        for d, lineno in affine_fors:
            if d == min_depth:
                root.add("affine_for", "affine.for", lineno)

    # Check statically indexed accesses against allocated memref shapes.
    private_by_name = {
        next(c.text for c in b.children if c.id == "name"): b
        for b in root.descendants()
        if b.id == "private_buf"
    }
    for lineno, line in enumerate(lines, start=1):
        sm = STORE_RE.search(line)
        if not sm or sm.group(1) not in private_by_name:
            continue
        buf = private_by_name[sm.group(1)]
        dims_match = re.match(
            r"memref<((?:\d+|\?)(?:x(?:\d+|\?))*)x", buf.text
        )
        raw_indices = [s.strip() for s in sm.group(2).split(",")]
        if not dims_match or not all(i.isdigit() for i in raw_indices):
            continue
        dims = dims_match.group(1).split("x")
        if len(dims) == len(raw_indices) and any(
            dim.isdigit() and int(index) >= int(dim)
            for index, dim in zip(raw_indices, dims)
        ):
            buf.add("out_of_bounds", sm.group(0), lineno)

    # Record whether each allocated buffer's first affine access is a
    # load or a store (a private slice read before initialization is
    # the #48703 signature).
    first_seen: set[str] = set()
    for lineno, line in enumerate(lines, start=1):
        for kind, m in (
            ("store", STORE_RE.search(line)),
            ("load", LOAD_RE.search(line)),
        ):
            if (
                m
                and m.group(1) in private_by_name
                and m.group(1) not in first_seen
            ):
                first_seen.add(m.group(1))
                private_by_name[m.group(1)].add("first_access", kind, lineno)

    if paired_input is not None:
        _synthesize_relative(root, text, paired_input)

    return root


def _synthesize_relative(root: Node, text: str, paired_input: str) -> None:
    in_root = parse(paired_input)

    # A pair of input sibling nests becoming one output nest identifies
    # the output fusion site used as the correspondence-rule trigger.
    in_top = [n for n in in_root.descendants() if n.id == "affine_for"]
    out_top = [n for n in root.descendants() if n.id == "affine_for"]
    if len(in_top) >= 2 and len(out_top) == 1:
        root.add("fused_nest", "affine.for", out_top[0].line)

    # scale_reshape: the op that shapes the scale operand for the
    # decomposition's normalization. The scale is the transform's SECOND
    # function argument (signature: input, scale, bias); onnx-mlir
    # renames SSA values across the rewrite, so match positionally, not
    # by the input's scale name. A per-channel (correct) decomposition
    # shapes scale to a tensor of C elements (onnx.Reshape to
    # [NG, C/NG, 1...]); a per-group (buggy, #2928) one shapes it to
    # num_groups elements (onnx.Unsqueeze to [NG, 1...]). target_dim is
    # that element count, so it equals channel_dim (C) iff per-channel.
    out_args = re.findall(r"(%[\w#]+)\s*:\s*tensor<[^>]+>", _func_header(text))
    scale_arg = out_args[1] if len(out_args) >= 2 else None
    if scale_arg:
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = re.search(
                r'"onnx\.(Reshape|Unsqueeze)"\(\s*(%[\w#]+)', line
            )
            if m and m.group(2) == scale_arg:
                rn = root.add("scale_reshape", f"onnx.{m.group(1)}", lineno)
                rtypes = re.findall(r"->\s*(tensor<[^>]+>)", line)
                if rtypes:
                    rn.add("target_dim", str(_numel(rtypes[0])), lineno)
                break

    # orig_buf_use: a use of a buffer that the input allocated at a
    # type this tree no longer allocates it at. Tracked by (SSA name,
    # type) so an unrelated value of the same type (e.g. a function
    # argument) does not count.
    in_allocs = set(ALLOC_RE.findall(paired_input))
    out_allocs = set(ALLOC_RE.findall(text))
    for name, ty in in_allocs - out_allocs:
        for lineno, line in enumerate(text.splitlines(), start=1):
            s = line.strip()
            if name in s and ty in s and not ALLOC_RE.search(s):
                root.add("orig_buf_use", f"{name} : {ty}", lineno)
