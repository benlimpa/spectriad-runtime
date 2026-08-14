"""Client for Loom's dataflow simulator, `loom-dfg-sim`.

The simulator executes a `dataflow.graph` under Loom's token model and
writes a JSON report. It is the only implementation of that model, so
it is the only way to learn what a lowered graph actually computes.

CLI contract, pinned against the tool and its lit suite (2026-07-25):

  loom-dfg-sim <input.mlir> --graph <sym> --output <report.json>
               [--arg I=V]... [--memref I[:byte_offset]=V0,V1,...]
               [--invocations N] [--max-event-steps N]

`I` indexes the graph's `function_type` inputs, in ONE index space
shared by scalar and memref arguments. It does NOT index block
arguments: a graph's leading `none` control argument is implicit and
carries no index.

The report is keyed as follows:

  status              "pass", or a failure label
  final_outputs       [aggregate ctrl token, then the value results in
                      function_type result order]. Element 0 is always
                      the string "none"; a graph with several control
                      results still reports one aggregate token.
  final_memory_state  {"arg<I>": ["<type>:<value>", ...]} final
                      contents of each memref fixture
  operation_fire_counts, event_count, diagnostics, ...

Because the tool wants a file in and a file out, neither of which
survives the ssh hop to bibim, SPECTRIAD_LOOM_DFG_SIM points at a
wrapper giving it a stdin/stdout shape (`loom/remote-dfg-sim.sh`):
MLIR in, report JSON out, diagnostics on stderr, exit code preserved.

A non-zero exit is NOT an error here. The simulator statically
validates a graph before running it (token cardinality, residual
structured ops), and a pass that emits a graph its own simulator
refuses is exactly the kind of defect this oracle exists to catch. So
a rejection is returned as a `Report` with `ok=False` and the
diagnostic text, and the caller decides whether that is a verdict.
`Unavailable` is reserved for "we could not ask the question": the env
var is unset, the transport failed, or the tool timed out.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field

from .oracles import Unavailable

ENV_VAR = "SPECTRIAD_LOOM_DFG_SIM"
TIMEOUT_S = 120


@dataclass
class Report:
    """One simulation, decoded into engine-neutral values."""

    ok: bool
    status: str = ""
    # Value results only, in function_type result order: the leading
    # aggregate ctrl token is stripped, because control-token shape is
    # a structural property the specs already cover and comparing it
    # across engines would compare bookkeeping, not computation.
    outputs: list[tuple[str, object]] = field(default_factory=list)
    # {function_type input index: [element values]}
    memory: dict[int, list[tuple[str, object]]] = field(default_factory=dict)
    fire_counts: dict[str, int] = field(default_factory=dict)
    event_count: int = 0
    error: str = ""
    raw: dict = field(default_factory=dict)


_TYPED = re.compile(r"^([^:]+):(.*)$", re.S)


def decode_value(s: str) -> tuple[str, object]:
    """Decode one "<type>:<value>" report string.

    Returns (type, value) with the value as a Python int/float where the
    type is scalar, and as the raw string otherwise (vectors are
    reported as packed hex, which is comparable verbatim). A bare
    "none" is the control token.
    """
    s = s.strip()
    if s == "none":
        return ("none", None)
    m = _TYPED.match(s)
    if not m:
        return ("?", s)
    ty, raw = m.group(1), m.group(2).strip()
    if ty.startswith(("i", "si", "ui", "index")) and not ty.startswith("index_"):
        try:
            return (ty, int(raw, 0))
        except ValueError:
            pass
    if ty.startswith("f") or ty.startswith("bf"):
        try:
            return (ty, float(raw))
        except ValueError:
            pass
    return (ty, raw)


def available() -> bool:
    return bool(os.environ.get(ENV_VAR, "").strip())


def _cmd() -> list[str]:
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        raise Unavailable(f"{ENV_VAR} not configured")
    return shlex.split(raw)


def simulate(
    text: str,
    graph: str,
    args: dict[int, str] | None = None,
    memrefs: dict[int, list[str]] | None = None,
    invocations: int = 1,
    max_event_steps: int = 100000,
) -> Report:
    """Run one graph. Raises Unavailable only when we could not ask."""
    argv = list(_cmd()) + ["--graph", graph]
    for i, v in sorted((args or {}).items()):
        argv += ["--arg", f"{i}={v}"]
    for i, vs in sorted((memrefs or {}).items()):
        argv += ["--memref", f"{i}=" + ",".join(str(v) for v in vs)]
    argv += ["--invocations", str(invocations),
             "--max-event-steps", str(max_event_steps)]

    last = ""
    for attempt in range(3):
        try:
            proc = subprocess.run(
                argv, input=text, capture_output=True, text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            raise Unavailable(f"loom-dfg-sim timed out after {TIMEOUT_S}s")
        except OSError as e:
            raise Unavailable(f"loom-dfg-sim failed to launch: {e}")
        if proc.returncode != 255:
            break
        # ssh throttling, same retry the other remote wrappers use.
        last = (proc.stderr or "").strip()[:300]
        time.sleep(1.5 * (attempt + 1))
    else:
        raise Unavailable(f"loom-dfg-sim transport failed: {last}")

    err = (proc.stderr or "").strip()
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        # The simulator refused the graph. That is an answer, not an
        # outage: report it and let the oracle decide.
        return Report(ok=False, error=err or f"exited {proc.returncode}")
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise Unavailable(f"loom-dfg-sim report is not JSON: {e}")

    outs = [decode_value(s) for s in d.get("final_outputs", [])]
    # Strip the leading aggregate control token.
    if outs and outs[0][0] == "none":
        outs = outs[1:]
    mem: dict[int, list[tuple[str, object]]] = {}
    for key, elems in (d.get("final_memory_state") or {}).items():
        m = re.match(r"arg(\d+)$", key)
        if m:
            mem[int(m.group(1))] = [decode_value(s) for s in elems]
    status = str(d.get("status", ""))
    return Report(
        ok=status == "pass",
        status=status,
        outputs=outs,
        memory=mem,
        fire_counts=dict(d.get("operation_fire_counts") or {}),
        event_count=int(d.get("event_count") or 0),
        error="" if status == "pass" else (err or f"status {status}"),
        raw=d,
    )
