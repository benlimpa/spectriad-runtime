"""PTC evaluator: parse and evaluate trigger/rule constraints against
a pair of MLIR node trees.

Supported rule grammar:

  expr        := andexpr ('or' andexpr)*
  andexpr     := unary ('and' unary)*
  unary       := 'not' unary | factor
  factor      := 'if' '(' expr ')' 'then' '(' expr ')'
               | '(' expr ')'
               | funcall
               | comparison
  comparison  := value ('==' | '!=' | 'in') rhs
  value       := 'count' '(' rpath ')' | rpath | STRING | INT
  rhs         := value | '[' STRING (',' STRING)* ']'
  funcall     := NAME '(' rpath (',' rpath)* ')'
                 (multiset_eq, corresponding_iterations,
                  isolated_recomputation, and covers_store_footprint
                  are executable on the node trees; no_deps_between is
                  a static footprint analysis, and exec_equiv /
                  deps_preserved run the concrete interpreter over the
                  observed pair (checker/interp.py). A pair outside
                  the interpreted subset yields an honestly labeled
                  STUB verdict with the reason.)
  rpath       := ref ('.' ref)*
  ref         := '{' 'id' '=' STRING (',' 'pos' '=' STRING)? '}'

rpath resolution: a leading {id="in"} / {id="out"} selects the input
or output tree; any other leading id searches both. Each subsequent
ref matches descendants of the current match set (descendant, not
child, to keep the sketches forgiving).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import ast as ast_mod
from . import features, interp
from .mlir_parse import Node

EXEC_FUNCS = {
    "multiset_eq",
    "corresponding_iterations",
    "isolated_recomputation",
    "covers_store_footprint",
    "no_deps_between",
    "deps_preserved",
    "exec_equiv",
}


_INT_TEXT = re.compile(r"^-?\d+$")


def _canon_int(text: str) -> str:
    """Canonicalize an integer literal to its signed 64-bit reading.

    The same 64-bit value is printed differently on the two sides of an
    scf.index_switch lowering: `case -434` on the source op, and
    `18446744073709551182` on the target cf.switch, whose case values
    are i64 and print unsigned. Comparing the printed text calls that a
    disagreement when the bits are identical. Non-integer texts and
    values outside 64 bits are returned unchanged, so this only
    normalizes representation, never magnitude.
    """
    if not _INT_TEXT.match(text):
        return text
    v = int(text)
    if not -(1 << 63) <= v < (1 << 64):
        return text
    return str(((v + (1 << 63)) % (1 << 64)) - (1 << 63))


class PTCError(Exception):
    pass


@dataclass
class Verdict:
    status: str  # PASS | FAIL | ABSTAIN | STUB | NO_TRIGGER | ERROR
    detail: str = ""
    # Output lines a failing rule binds to, for UI highlighting.
    lines: list[int] = field(default_factory=list)
    # Condition/decision coverage of the rule's boolean nodes, populated
    # only when check_constraint(..., record_coverage=True). None means
    # recording was off.
    coverage: dict | None = None


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<lbrace>\{)|(?P<rbrace>\})|
        (?P<lparen>\()|(?P<rparen>\))|
        (?P<lbrack>\[)|(?P<rbrack>\])|
        (?P<dot>\.)|(?P<comma>,)|
        (?P<eq>==)|(?P<neq>!=)|(?P<assign>=)|
        (?P<le><=)|(?P<ge>>=)|(?P<lt><)|(?P<gt>>)|
        (?P<string>"(?:[^"\\]|\\.)*")|
        (?P<int>-?\d+)|
        (?P<name>[A-Za-z_][A-Za-z_0-9]*)
    )""",
    re.VERBOSE,
)


def tokenize(s: str) -> list[tuple[str, str]]:
    toks, i = [], 0
    while i < len(s):
        m = TOKEN_RE.match(s, i)
        if not m:
            if s[i:].strip():
                raise PTCError(f"cannot tokenize at: {s[i:i+20]!r}")
            break
        i = m.end()
        for kind, val in m.groupdict().items():
            if val is not None:
                toks.append((kind, val))
                break
    return toks


# --------------------------------------------------------------------------
# Parser (to a small AST of tuples)
# --------------------------------------------------------------------------


class Parser:
    def __init__(self, toks: list[tuple[str, str]]):
        self.toks = toks
        self.i = 0

    def peek(self, k: int = 0):
        return self.toks[self.i + k] if self.i + k < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, kind: str):
        k, v = self.next()
        if k != kind:
            raise PTCError(f"expected {kind}, got {k} {v!r}")
        return v

    # expr := andexpr ('or' andexpr)*
    def expr(self):
        node = self.andexpr()
        while self.peek() == ("name", "or"):
            self.next()
            node = ("or", node, self.andexpr())
        return node

    def andexpr(self):
        node = self.unary()
        while self.peek() == ("name", "and"):
            self.next()
            node = ("and", node, self.unary())
        return node

    def unary(self):
        if self.peek() == ("name", "not"):
            self.next()
            return ("not", self.unary())
        return self.factor()

    def factor(self):
        k, v = self.peek()
        if (k, v) == ("name", "if"):
            self.next()
            self.expect("lparen")
            cond = self.expr()
            self.expect("rparen")
            if self.peek() != ("name", "then"):
                raise PTCError("expected 'then'")
            self.next()
            self.expect("lparen")
            body = self.expr()
            self.expect("rparen")
            return ("ifthen", cond, body)
        if k == "lparen":
            self.next()
            node = self.expr()
            self.expect("rparen")
            return node
        if k == "name" and v not in ("count",) and self.peek(1)[0] == "lparen":
            # funcall (built-in exec predicates, generic features,
            # adhoc python predicates, external oracles). A funcall
            # followed by a comparison operator is that comparison's
            # value-position lhs, not a boolean call.
            self.next()
            args = self._funcall_args()
            nk, nv = self.peek()
            if nk in ("eq", "neq") or (nk, nv) == ("name", "in"):
                return self.comparison(lhs=("callv", v, args))
            return ("call", v, args)
        return self.comparison()

    def _funcall_args(self):
        """Args are rpaths ({id="..."}) or STRINGs; may be empty."""
        self.expect("lparen")
        args = []
        while self.peek()[0] != "rparen":
            if self.peek()[0] == "string":
                args.append(("str", self.next()[1][1:-1]))
            else:
                args.append(self.rpath())
            if self.peek()[0] == "comma":
                self.next()
        self.expect("rparen")
        return args

    def comparison(self, lhs=None):
        if lhs is None:
            lhs = self.value()
        k, v = self.peek()
        if k in ("eq", "neq"):
            self.next()
            return ("cmp", "==" if k == "eq" else "!=", lhs, self.rhs())
        if (k, v) == ("name", "in"):
            self.next()
            return ("cmp", "in", lhs, self.rhs())
        return ("truthy", lhs)

    def rhs(self):
        if self.peek()[0] == "lbrack":
            self.next()
            items = [self.expect("string")]
            while self.peek()[0] == "comma":
                self.next()
                items.append(self.expect("string"))
            self.expect("rbrack")
            return ("list", [s[1:-1] for s in items])
        return self.value()

    def value(self):
        k, v = self.peek()
        if (k, v) == ("name", "count"):
            self.next()
            self.expect("lparen")
            rp = self.rpath()
            self.expect("rparen")
            return ("count", rp)
        if k == "name" and self.peek(1)[0] == "lparen":
            # value-position feature call, e.g. count_ops("out", "llvm.add")
            self.next()
            return ("callv", v, self._funcall_args())
        if k == "lbrace":
            return ("rpath", self.rpath())
        if k == "string":
            self.next()
            return ("str", v[1:-1])
        if k == "int":
            self.next()
            return ("int", int(v))
        raise PTCError(f"unexpected token {k} {v!r}")

    def rpath(self):
        refs = [self.ref()]
        while self.peek()[0] == "dot":
            self.next()
            refs.append(self.ref())
        return refs

    def ref(self):
        self.expect("lbrace")
        attrs = {}
        while True:
            key = self.expect("name")
            self.expect("assign")
            attrs[key] = self.expect("string")[1:-1]
            if self.peek()[0] == "comma":
                self.next()
                continue
            break
        self.expect("rbrace")
        return attrs


def parse_rule(rule: str):
    return Parser(tokenize(rule)).expr()


# --------------------------------------------------------------------------
# Stable node ids (pure function of the rule text)
# --------------------------------------------------------------------------

# Boolean-valued node kinds; the coverage recorder tracks their outcomes.
DECISION_KINDS = {"or", "and", "not", "ifthen", "truthy", "call", "cmp"}
# Value-position quantifier nodes whose rpath resolution can be vacuous.
QUANTIFIER_KINDS = {"count", "rpath"}


def _child_asts(ast):
    """Ordered sub-AST children by tuple child position. Only nodes that
    themselves carry a kind (never rpath ref lists or call args) count,
    so paths stay a pure function of the rule text."""
    kind = ast[0]
    if kind in ("or", "and", "ifthen"):
        return [ast[1], ast[2]]
    if kind == "not":
        return [ast[1]]
    if kind == "truthy":
        return [ast[1]]
    if kind == "cmp":
        return [ast[2], ast[3]]  # lhs, rhs (op at index 1 is not a node)
    return []  # count/rpath/callv/call/str/int: leaves for pathing


def _walk(ast, path="r"):
    """Yield (path, ast) pre-order, path ids as in the module docstring:
    root "r", child i of a node at "p" is "p.i"."""
    yield path, ast
    for i, child in enumerate(_child_asts(ast)):
        yield from _walk(child, f"{path}.{i}")


def _node_id(path: str, ast) -> str:
    return f"{path}:{ast[0]}"


def decision_nodes(rule_text: str) -> list[str]:
    """Ids of every boolean-valued node in the rule, pre-order."""
    ast = parse_rule(rule_text)
    return [
        _node_id(p, a) for p, a in _walk(ast) if a[0] in DECISION_KINDS
    ]


def quantifier_nodes(rule_text: str) -> list[str]:
    """Ids of every count/rpath value node in the rule, pre-order."""
    ast = parse_rule(rule_text)
    return [
        _node_id(p, a) for p, a in _walk(ast) if a[0] in QUANTIFIER_KINDS
    ]


# --------------------------------------------------------------------------
# Evaluator
# --------------------------------------------------------------------------


class _Stub(Exception):
    """A value-position feature could not run (unparseable side, no
    oracle configured): the whole check is honestly a STUB."""


class _Abstain(Exception):
    """An ad-hoc predicate returned None: it CAN run here but declines
    to assert, because the pair is outside the space its source column
    covers. Distinct from PASS, which claims conformance, and from
    STUB, which means the check could not execute at all."""


class Evaluator:
    def __init__(
        self,
        in_tree: Node,
        out_tree: Node,
        in_text: str = "",
        out_text: str = "",
        constraint: dict | None = None,
    ):
        self.in_tree = in_tree
        self.out_tree = out_tree
        self.in_text = in_text
        self.out_text = out_text
        self.constraint = constraint or {}
        self._ast_pair = None  # lazy xdsl AstPair for feature calls
        self.stubbed: list[str] = []
        # Reasons ad-hoc predicates gave for declining to assert here.
        self.abstained: list[str] = []
        # Every node a rule resolved or an executable predicate blamed;
        # check_constraint keeps the output-tree ones for localization.
        self.touched: list[Node] = []
        # Output line numbers and prose notes contributed by the
        # concrete-execution predicates (they blame lines directly,
        # not through parse-tree nodes).
        self.extra_lines: list[int] = []
        self.notes: list[str] = []
        # Coverage recorder; None unless check_constraint turns it on.
        # Recording is a side effect only: it never alters a verdict,
        # note, blamed line, or evaluation order.
        self._rec: dict | None = None

    def start_recording(self) -> dict:
        self._rec = {"conditions": {}, "vacuous": {}, "adhoc_taken": []}
        return self._rec

    def _record_bool(self, path: str, kind: str, val: bool) -> None:
        if self._rec is None:
            return
        slot = self._rec["conditions"].setdefault(
            f"{path}:{kind}", {"T": 0, "F": 0}
        )
        slot["T" if val else "F"] += 1

    def _record_quant(self, path: str, kind: str, matched: int) -> None:
        # Max parse nodes the rpath resolved to across evaluations of
        # this node; 0 records a vacuous evaluation.
        if self._rec is None:
            return
        nid = f"{path}:{kind}"
        self._rec["vacuous"][nid] = max(
            self._rec["vacuous"].get(nid, 0), matched
        )

    def resolve(self, refs: list[dict], scope: list[Node] | None = None) -> list[Node]:
        first = refs[0]["id"]
        if scope is None:
            if first == "in":
                nodes, refs = [self.in_tree], refs[1:]
            elif first == "out":
                nodes, refs = [self.out_tree], refs[1:]
            else:
                nodes = [self.in_tree, self.out_tree]
        else:
            nodes = scope
        for ref in refs:
            matched: list[Node] = []
            for n in nodes:
                pool = [n] if n.id == ref["id"] else []
                pool += [d for d in n.descendants() if d.id == ref["id"]]
                matched.extend(pool)
            if "pos" in ref and ref["pos"] not in ("any",):
                idx = int(ref["pos"])
                matched = [matched[idx]] if -len(matched) <= idx < len(matched) else []
            # de-dup while keeping order
            seen: set[int] = set()
            nodes = [m for m in matched if not (id(m) in seen or seen.add(id(m)))]
        self.touched.extend(nodes)
        return nodes

    def texts(self, refs: list[dict]) -> list[str]:
        return [n.text for n in self.resolve(refs)]

    def _feature_call(self, name: str, args):
        """Dispatch a generic-feature / adhoc / oracle funcall.

        Raises _Stub when the call cannot run here; the caller decides
        whether that is non-refuting (bool position) or makes the
        whole verdict a STUB (value position).
        """
        from . import adhoc as adhoc_mod
        from . import oracles

        strs = [a[1] for a in args if isinstance(a, tuple) and a[0] == "str"]
        if len(strs) != len(args):
            raise PTCError(f"{name}() takes string arguments only")
        if name == "adhoc":
            code = self.constraint.get("check_code")
            if not code:
                raise PTCError("adhoc(...) rule without check_code")
            try:
                if self._rec is not None:
                    # coverage=True asks adhoc.run for the taken branch ids
                    # (4-tuple); fall back to the 3-arg form when adhoc.py
                    # is the old version that lacks the kwarg.
                    try:
                        ok, note, lines, taken = adhoc_mod.run(
                            code, self.in_text, self.out_text, coverage=True
                        )
                    except TypeError:
                        ok, note, lines = adhoc_mod.run(
                            code, self.in_text, self.out_text
                        )
                        taken = []
                    self._rec["adhoc_taken"].extend(taken)
                else:
                    ok, note, lines = adhoc_mod.run(
                        code, self.in_text, self.out_text
                    )
            except adhoc_mod.AdhocError as e:
                raise PTCError(str(e))
            if ok is None:
                self.abstained.append(note or "predicate declined to assert")
                raise _Abstain(name)
            return features.FeatureResult(ok, lines, note)
        if name in oracles.NAMES:
            try:
                ok, note, lines = oracles.run(name, self.in_text, self.out_text)
            except oracles.Unavailable as e:
                self.stubbed.append(f"{name} ({e})")
                raise _Stub(name)
            return features.FeatureResult(ok, lines, note)
        try:
            pair = self._pair()
        except ast_mod.AstError as e:
            self.stubbed.append(f"{name} ({e})")
            raise _Stub(name)
        try:
            return features.REGISTRY[name](pair, *strs)
        except TypeError as e:
            raise PTCError(f"{name}(): {e}")
        except features.FeatureError as e:
            raise PTCError(str(e))

    def _pair(self):
        if self._ast_pair is None:
            self._ast_pair = ast_mod.parse_pair(self.in_text, self.out_text)
        return self._ast_pair

    def eval_value(self, ast, path: str = "r"):
        kind = ast[0]
        if kind == "count":
            n = len(self.resolve(ast[1]))
            self._record_quant(path, "count", n)
            return n
        if kind == "callv":
            # value position: a stub here makes the verdict a STUB
            res = self._feature_call(ast[1], ast[2])
            if res.note:
                self.notes.append(res.note)
            self._callv_results = getattr(self, "_callv_results", [])
            self._callv_results.append(res)
            return res.value
        if kind == "rpath":
            ts = self.texts(ast[1])
            self._record_quant(path, "rpath", len(ts))
            return ts[0] if len(ts) == 1 else ts
        if kind in ("str",):
            return ast[1]
        if kind == "int":
            return ast[1]
        raise PTCError(f"bad value {ast!r}")

    def eval(self, ast, path: str = "r") -> bool:
        # Record each boolean node's outcome after it is computed; a
        # short-circuited subexpression is simply never visited, so it
        # leaves no record.
        val = self._eval_bool(ast, path)
        self._record_bool(path, ast[0], val)
        return val

    def _eval_bool(self, ast, path: str) -> bool:
        kind = ast[0]
        if kind == "or":
            return self.eval(ast[1], path + ".0") or self.eval(ast[2], path + ".1")
        if kind == "and":
            return self.eval(ast[1], path + ".0") and self.eval(ast[2], path + ".1")
        if kind == "not":
            return not self.eval(ast[1], path + ".0")
        if kind == "ifthen":
            return (not self.eval(ast[1], path + ".0")) or self.eval(
                ast[2], path + ".1"
            )
        if kind == "truthy":
            v = self.eval_value(ast[1], path + ".0")
            return bool(v)
        if kind == "call":
            name, args = ast[1], ast[2]
            from . import oracles

            if name in features.REGISTRY or name == "adhoc" or name in oracles.NAMES:
                try:
                    res = self._feature_call(name, args)
                except _Stub:
                    return True  # bool position: stub is non-refuting
                if res.note:
                    self.notes.append(res.note)
                if not res.value:
                    self.extra_lines.extend(res.lines)
                return bool(res.value)
            if name == "no_deps_between":
                # Static memref-granularity footprint analysis over the
                # input's top-level nests (the rule's arg ids name the
                # nests symbolically; the analysis checks every pair).
                try:
                    ok, note = interp.no_deps_between(self.in_text)
                except interp.Unsupported as e:
                    self.stubbed.append(f"{name} ({e})")
                    return True
                self.notes.append(note)
                return ok
            if name in ("deps_preserved", "exec_equiv"):
                # Concrete execution: run both modules on the same
                # seeded environment and compare observable state. A
                # difference refutes the claim (a violated dependence
                # is observable as a changed value); equality is
                # evidence on the probed runs, not proof.
                try:
                    ok, note, lines = interp.equivalent(
                        self.in_text, self.out_text
                    )
                except interp.Unsupported as e:
                    self.stubbed.append(f"{name} ({e})")
                    return True
                self.notes.append(note)
                if not ok:
                    self.extra_lines.extend(lines)
                return ok
            if name == "multiset_eq":
                a = sorted(_canon_int(t) for t in self.texts(args[0]))
                b = sorted(_canon_int(t) for t in self.texts(args[1]))
                return a == b
            if name == "corresponding_iterations":
                # A same-domain fusion must not introduce another loop
                # level. The parser records lexical affine-loop depth;
                # depth SPREADS are compared (absolute depth shifts
                # with module/func wrapping). This separates #61820's
                # nested re-execution from same-depth fusion.
                in_depths = [
                    int(n.text)
                    for n in self.in_tree.descendants()
                    if n.id == "affine_loop_depth"
                ]
                out_nodes = [
                    n
                    for n in self.out_tree.descendants()
                    if n.id == "affine_loop_depth"
                ]
                if not (in_depths and out_nodes):
                    return False
                in_spread = max(in_depths) - min(in_depths)
                out_min = min(int(n.text) for n in out_nodes)
                deeper = [
                    n
                    for n in out_nodes
                    if int(n.text) - out_min > in_spread
                ]
                self.touched.extend(deeper)
                return not deeper
            if name == "isolated_recomputation":
                # The recomputed slice must be data-isolated: existing
                # observable buffers must not gain another static store
                # site, and a private buffer must be initialized
                # (stored) before it is read. The buggy #48703
                # replacement violates the latter by redirecting the
                # slice's source load into the fresh private buffer.
                def counts(nodes):
                    result = {}
                    for n in nodes:
                        if n.id == "store_target":
                            result[n.text] = result.get(n.text, 0) + 1
                    return result

                out_stores = [
                    n
                    for n in self.out_tree.descendants()
                    if n.id == "store_target"
                ]
                before = counts(self.in_tree.descendants())
                after = counts(out_stores)
                dup_targets = {
                    t for t, c in before.items() if after.get(t, 0) > c
                }
                self.touched.extend(
                    n for n in out_stores if n.text in dup_targets
                )
                read_before_init = [
                    n
                    for b in self.out_tree.descendants()
                    if b.id == "private_buf"
                    for n in b.children
                    if n.id == "first_access" and n.text == "load"
                ]
                self.touched.extend(read_before_init)
                return not dup_targets and not read_before_init
            if name == "covers_store_footprint":
                buffers = self.resolve(args[0])
                oob = [
                    n
                    for b in buffers
                    for n in b.descendants()
                    if n.id == "out_of_bounds"
                ]
                self.touched.extend(oob)
                return bool(buffers) and not oob
            raise PTCError(f"unknown function {name}")
        if kind == "cmp":
            op, lhs, rhs = ast[1], ast[2], ast[3]
            mark = len(getattr(self, "_callv_results", []))
            result = self._eval_cmp(ast, path)
            if not result:
                # blame the lines of any feature values in this comparison
                for res in getattr(self, "_callv_results", [])[mark:]:
                    self.extra_lines.extend(res.lines)
            return result
        raise PTCError(f"bad ast {ast!r}")

    def _eval_cmp(self, ast, path: str = "r") -> bool:
        op, lhs, rhs = ast[1], ast[2], ast[3]
        lv = self.eval_value(lhs, path + ".0")
        if rhs[0] == "list":
            if op == "in":
                return str(lv) in rhs[1]
            raise PTCError("list rhs requires 'in'")
        rv = self.eval_value(rhs, path + ".1")
        # numeric comparison when both sides look numeric
        try:
            lv2, rv2 = float(str(lv)), float(str(rv))
            lv, rv = lv2, rv2
        except (TypeError, ValueError):
            lv, rv = str(lv), str(rv)
        if op == "==":
            return lv == rv
        if op == "!=":
            return lv != rv
        raise PTCError(f"bad cmp op {op}")


def check_constraint(
    constraint: dict, in_text: str, out_text: str, record_coverage: bool = False
) -> Verdict:
    """Evaluate one {trigger, rule} constraint on an input/output pair.

    With record_coverage the returned Verdict.coverage records which
    boolean nodes were evaluated (short-circuit aware) and with which
    outcomes, plus quantifier vacuity and adhoc branch ids. Recording is
    a pure side effect: the status/detail/lines are identical either way.
    """
    from .mlir_parse import parse

    ev = None
    triggers = None

    def _cov(sites: int) -> dict:
        rec = ev._rec if ev is not None else None
        if rec is None:
            rec = {"conditions": {}, "vacuous": {}, "adhoc_taken": []}
        abstained = bool(ev is not None and ev.abstained)
        return {
            # An abstaining predicate is NOT exercised: it matched a
            # trigger site and then said nothing about the pair. Counting
            # it as triggered is what let a scoped predicate read as
            # fully covered while asserting on a third of the campaign.
            "triggered": sites > 0 and not abstained,
            "abstained": abstained,
            "trigger_sites": sites,
            "conditions": rec["conditions"],
            "vacuous": rec["vacuous"],
            "adhoc_taken": rec["adhoc_taken"],
        }

    def _attach(v: Verdict, sites: int) -> Verdict:
        if record_coverage:
            v.coverage = _cov(sites)
        return v

    try:
        in_tree = parse(in_text, paired_input=None)
        out_tree = parse(out_text, paired_input=in_text)
        ev = Evaluator(in_tree, out_tree, in_text, out_text, constraint)
        if record_coverage:
            ev.start_recording()

        trigger_refs = Parser(tokenize(constraint["trigger"])).rpath()
        # {id="out"} / {id="pair"} style triggers scope the whole pair
        if trigger_refs[0]["id"] in ("in", "out", "pair"):
            triggers = [None]
        else:
            triggers = ev.resolve(trigger_refs)
            if not triggers:
                return _attach(
                    Verdict("NO_TRIGGER", "trigger path matched no node"), 0
                )

        ast = parse_rule(constraint["rule"])
        results = []
        try:
            for _t in triggers:
                results.append(ev.eval(ast))
        except _Stub:
            pass  # a value-position feature stubbed: verdict below
        except _Abstain:
            pass  # predicate declined to assert: verdict below
        sites = len(triggers)
        if ev.abstained:
            # Checked before STUB: the predicate ran fine, it just does
            # not cover this pair. Never a pass, so a scoped predicate
            # cannot read as exercised on inputs it says nothing about.
            return _attach(
                Verdict(
                    "ABSTAIN",
                    f"declines to assert: {'; '.join(dict.fromkeys(ev.abstained))}",
                ),
                sites,
            )
        if ev.stubbed:
            return _attach(
                Verdict(
                    "STUB",
                    f"not executable here: {', '.join(sorted(set(ev.stubbed)))}",
                ),
                sites,
            )
        notes = "; ".join(dict.fromkeys(ev.notes))
        if all(results):
            detail = f"holds at {len(results)} trigger site(s)"
            if notes:
                detail += f" ({notes})"
            return _attach(Verdict("PASS", detail), sites)
        failed = len([r for r in results if not r])
        out_ids = {id(n) for n in out_tree.descendants()}
        lines = sorted(
            {
                n.line
                for n in ev.touched
                if id(n) in out_ids and n.line is not None
            }
            | set(ev.extra_lines)
        )
        detail = f"violated at {failed} trigger site(s)"
        if notes:
            detail += f": {notes}"
        if lines:
            detail += f"; output lines {', '.join(map(str, lines))}"
        return _attach(Verdict("FAIL", detail, lines), sites)
    except PTCError as e:
        sites = len(triggers) if triggers is not None else 0
        return _attach(Verdict("ERROR", str(e)), sites)
