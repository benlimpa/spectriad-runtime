"""External oracles: checks that shell out to real toolchain binaries.

Configured like the runners, via command-prefix env vars (unset ->
the oracle reports Unavailable and the verdict is an honest STUB):

  SPECTRIAD_UPSTREAM_MLIR_OPT  upstream mlir-opt from the SAME LLVM
                               revision the subject compiler builds
                               against (for Loom: its LLVM submodule
                               build)
  SPECTRIAD_LOOM_DFG_SIM       loom-dfg-sim (dataflow simulator)

roundtrip_equiv — for a RAISING pass, lower
the raised output back with upstream mlir-opt, canonicalize both
sides with the same upstream binary, and diff. Residual differences
listed in _KNOWN_EQUIV (libm call <-> llvm intrinsic — exactly the
pass's libm-recognition semantics) are filtered; anything else FAILs
with the offending round-tripped lines mapped back to output lines
by op name.

sim_equiv — differential execution for Loom graph-lowering passes. The two
sides of such a pair cannot run on one engine: the input still holds
structured control flow, which Loom's simulator refuses, so it runs on
our own reference interpreter, and the lowered graph runs on Loom's
simulator, which is the only implementation of its token model. See
checker/simequiv.py for the method and checker/dfgsim.py for the CLI
contract.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time

TIMEOUT_S = 60

# name-normalized equivalences left over by a correct round-trip:
# (llvm dialect form, upstream-lowered form). Two shapes:
# 1. libm call <-> llvm intrinsic (math-to-llvm lowered it);
# 2. libm call <-> the math op ITSELF: math ops with no LLVM
#    intrinsic (math.erf, ...) survive the lowering unconverted.
#    Re-lowering them via MathToLibm is NOT an option on raised
#    modules — the extern stays llvm.func (phase-0 finding) and
#    MathToLibm's func.call cannot reference it (verifier error,
#    found by the harness gate at seed 9207 on agent-widened specs).
_LIBM_RE = re.compile(
    r"\bllvm\.call @(fabsf?|sinf?|cosf?|tanf?|sinhf?|coshf?|"
    r"tanhf?|expf?|exp2f?|expm1f?|logf?|log2f?|log10f?|"
    r"log1pf?|floorf?|ceilf?|roundf?|truncf?|rintf?|"
    r"nearbyintf?|sqrtf?|erff?)\b"
)
_KNOWN_EQUIV = [
    (_LIBM_RE, re.compile(r"\bllvm\.intr\.\w+")),
    (_LIBM_RE, re.compile(r"\bmath\.\w+")),
]


class Unavailable(Exception):
    """Oracle not configured/usable here: honest STUB, not a verdict."""


def _cmd(env_var: str) -> list[str]:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        raise Unavailable(f"{env_var} not configured")
    return shlex.split(raw)


def _pipe(cmd: list[str], text: str, label: str) -> str:
    # ssh-wrapped oracles fire many sessions in quick succession; a
    # throttled connection exits 255 and must not poison a verdict as
    # a STUB. Retry transport-level failures; real tool errors (any
    # other exit code) surface immediately.
    last = ""
    for attempt in range(3):
        try:
            proc = subprocess.run(
                cmd, input=text, capture_output=True, text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise Unavailable(f"{label} timed out after {TIMEOUT_S}s")
        except OSError as e:
            raise Unavailable(f"{label} failed to launch: {e}")
        if proc.returncode == 0:
            return proc.stdout
        last = f"{label} exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        if proc.returncode != 255:
            break
        time.sleep(1.5 * (attempt + 1))
    raise Unavailable(last)


def _norm_lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]


def _equivalent_lines(a: str, b: str) -> bool:
    for llvm_re, lowered_re in _KNOWN_EQUIV:
        if llvm_re.search(a) and lowered_re.search(b):
            return True
        if llvm_re.search(b) and lowered_re.search(a):
            return True
    return False


def roundtrip_equiv(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    opt = _cmd("SPECTRIAD_UPSTREAM_MLIR_OPT")
    lowered = _pipe(
        opt
        + [
            "--convert-math-to-llvm",
            "--convert-arith-to-llvm",
            "--convert-func-to-llvm",
            "--reconcile-unrealized-casts",
            "-",
        ],
        out_text,
        "upstream lowering of the raised output",
    )
    orig_norm = _pipe(opt + ["--canonicalize", "-"], in_text, "canonicalize(input)")
    rt_norm = _pipe(opt + ["--canonicalize", "-"], lowered, "canonicalize(round-trip)")

    a, b = _norm_lines(orig_norm), _norm_lines(rt_norm)
    residues = [
        (la, lb)
        for la, lb in zip(a, b)
        if la != lb and not _equivalent_lines(la, lb)
    ]
    if len(a) != len(b):
        residues.append((f"<{len(a)} lines>", f"<{len(b)} lines>"))
    if not residues:
        note = (
            "round-trip via upstream mlir-opt reproduces the input "
            "(modulo known libm/intrinsic equivalences)"
        )
        return True, note, []

    # Map residual round-trip lines back to output lines by op name.
    blame: list[int] = []
    out_lines = out_text.splitlines()
    for la, lb in residues:
        m = re.search(r"\b([a-z_]+\.[\w.]+)\b", lb) or re.search(
            r"\b([a-z_]+\.[\w.]+)\b", la
        )
        if not m:
            continue
        for i, ol in enumerate(out_lines):
            if m.group(1) in ol:
                blame.append(i + 1)
                break
    note = "round-trip diverges: " + "; ".join(
        f"{la!r} vs {lb!r}" for la, lb in residues[:3]
    )
    return False, note[:600], sorted(set(blame))


def sim_equiv(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    # Imported lazily: simequiv imports this module for Unavailable, and
    # it pulls in the xdsl AST layer, which callers that only want
    # roundtrip_equiv should not pay for.
    from . import simequiv

    return simequiv.sim_equiv(in_text, out_text)


def graph_valid(in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    # Lazy for the same reason as sim_equiv: graphvalid imports this
    # module for Unavailable, and it pulls in the xdsl AST layer.
    from . import graphvalid

    return graphvalid.graph_valid(in_text, out_text)


_ORACLES = {
    "roundtrip_equiv": roundtrip_equiv,
    "sim_equiv": sim_equiv,
    "graph_valid": graph_valid,
}

# Public: the external-oracle function names a rule may call. The
# deriver's funcall allowlist folds these in next to the generic
# features and the legacy exec predicates.
NAMES = frozenset(_ORACLES)


def run(name: str, in_text: str, out_text: str) -> tuple[bool, str, list[int]]:
    return _ORACLES[name](in_text, out_text)
