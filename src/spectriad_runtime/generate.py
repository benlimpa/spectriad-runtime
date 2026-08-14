"""Budgeted property-based testing over a bundle unit's grammars.

`generate` is the mode that makes this a PBT integration: it draws
FRESH inputs from the unit's per-source input grammars under a seed or
wall-clock budget, runs the current subject compiler on each, and
evaluates every source column's output constraints on the accepted
pairs. Source columns are round-robined the same way the internal
campaign driver assigns them: sources are sorted and seed `s` draws
from `sources[s % len(sources)]`, so a docs/code/examples unit spreads
the budget evenly across columns.

Seed selection is sequential from `--seed-base` (v0.2): there is no
coverage-directed or novelty-based selection here, deliberately —
sequential seeds keep a run reproducible from two numbers and are
sufficient for maintainer-side budgets.

Honesty rules (identical to replay):

* ERROR and STUB are not violations, ABSTAIN is a decline, and a
  violation count of zero alone proves nothing; the report carries the
  full per-constraint verdict SET.
* A run where the subject compiler never executed is an infrastructure
  outcome (exit 3), never a pass.
* A compiler rejection of a grammar-conforming input is a behavioral
  finding: the source's input spec claims the input is accepted.

Everything worth a second look is preserved to the output directory:
rejections and constraint failures keep the input, the output or
diagnostics, and the per-constraint verdicts for that pair; generation
failures keep the generator error.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from . import bundle, generation, runner
from .checker.ptc import check_constraint
from .replay import VERDICT_ORDER

PRESERVE_LIST_CAP = 25


def generate_unit(
    unit_dir: Path,
    runner_declaration: dict | None = None,
    *,
    seeds: int | None = None,
    duration: float | None = None,
    seed_base: int = 0,
    out_dir: Path | None = None,
    progress=None,
) -> dict:
    """Run one budgeted generative campaign over a bundle unit.

    Exactly like replay, `runner_declaration` overrides the unit's
    stored declaration. At least one of `seeds` (input count) and
    `duration` (wall-clock seconds) must be given; with both, whichever
    budget is exhausted first ends the run.
    """
    if seeds is None and duration is None:
        raise ValueError("generate needs a budget: seeds and/or duration")
    unit = bundle.load_unit(unit_dir)
    manifest = unit["manifest"]
    report: dict = {
        "mode": "generate",
        "unit": manifest.get("unit"),
        "unit_dir": str(unit["unit_dir"]),
        "manifest_spec_hash": manifest.get("spec_hash"),
        "recomputed_spec_hash": unit["spec_hash"],
        "spec_hash_ok": manifest.get("spec_hash") == unit["spec_hash"],
        "subject_revision": manifest.get("subject_revision"),
        "budget": {
            "seeds": seeds,
            "duration_s": duration,
            "seed_base": seed_base,
        },
    }
    if not report["spec_hash_ok"]:
        raise bundle.BundleError(
            f"spec tree hash {unit['spec_hash']} does not match the "
            f"manifest's {manifest.get('spec_hash')}; the unit's spec "
            "content drifted after export"
        )

    declaration = runner_declaration or unit["runner"]
    runner_state = "not-configured"
    build = None
    if declaration is not None:
        try:
            runner.resolve_command(declaration)
            runner_state = "configured"
            build = runner.build_identity(declaration)
        except runner.RunnerNotConfigured as e:
            runner_state = f"not-configured ({e})"
            declaration = None
    report["runner"] = runner_state
    report["build_identity"] = build

    out_dir = Path(out_dir) if out_dir else Path(f"spectriad-generate-{report['unit']}")
    findings_dir = out_dir / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    report["out_dir"] = str(out_dir)

    # Round-robin source assignment, matching the internal driver:
    # sorted columns, seed modulo the column count.
    sources = sorted(unit["sources"])
    gen_failures, rejections, infrastructure = [], [], []
    verdict_sets: dict[str, Counter] = {}
    findings = 0
    generated = executed = 0
    started = time.monotonic()

    def _preserve(seed, src, kind, *, input_text=None, output_text=None,
                  diagnostics=None, verdicts=None) -> str:
        nonlocal findings
        findings += 1
        d = findings_dir / f"seed-{seed}-{src}"
        d.mkdir(parents=True, exist_ok=True)
        meta = {"seed": seed, "source": src, "kind": kind,
                "unit": report["unit"], "spec_hash": unit["spec_hash"]}
        (d / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        if input_text is not None:
            (d / "input.mlir").write_text(input_text)
        if output_text is not None:
            (d / "output.mlir").write_text(output_text)
        if diagnostics is not None:
            (d / "diagnostics.txt").write_text(diagnostics)
        if verdicts is not None:
            (d / "verdicts.json").write_text(json.dumps(verdicts, indent=2) + "\n")
        return str(d)

    i = 0
    while True:
        if seeds is not None and i >= seeds:
            break
        if duration is not None and time.monotonic() - started >= duration:
            break
        seed = seed_base + i
        i += 1
        src = sources[seed % len(sources)]
        if progress and (i == 1 or i % 25 == 0):
            progress(f"seed {seed} ({src}), {i} generated")
        entry = unit["sources"][src]
        try:
            text = generation.generate_from_text(
                entry["grammar_text"], seed, stem=f"{report['unit']}-{src}"
            )
        except RuntimeError as e:
            row = {"seed": seed, "source": src, "error": str(e)[:300]}
            row["preserved"] = _preserve(
                seed, src, "generation_failure", diagnostics=str(e)
            )
            gen_failures.append(row)
            continue
        generated += 1
        if declaration is None:
            continue
        res = runner.run_subject(declaration, text)
        if not res["ok"]:
            if res.get("failure_kind") == "infrastructure":
                infrastructure.append(
                    {"seed": seed, "source": src, "detail": res["runner"][:200]}
                )
                continue
            # The generating source's input spec says this input is in
            # the pass's domain; a rejection is a disagreement.
            row = {"seed": seed, "source": src, "detail": res["runner"][:200]}
            row["preserved"] = _preserve(
                seed, src, "rejection",
                input_text=text,
                diagnostics=f"{res['runner']}\n\n{res.get('output', '')}",
            )
            rejections.append(row)
            executed += 1
            continue
        executed += 1
        pair_verdicts, pair_bad = {}, False
        for csrc, entry2 in unit["sources"].items():
            for constraint in entry2["output_constraints"]:
                cid = f"{csrc}/{constraint.get('id')}"
                v = check_constraint(constraint, text, res["output"])
                verdict_sets.setdefault(cid, Counter())[v.status] += 1
                pair_verdicts[cid] = {
                    "status": v.status,
                    "detail": v.detail[:300],
                    "lines": v.lines,
                }
                if v.status in ("FAIL", "ERROR"):
                    pair_bad = True
        if pair_bad:
            _preserve(
                seed, src, "constraint_failure",
                input_text=text, output_text=res["output"],
                verdicts=pair_verdicts,
            )

    report["generated"] = generated
    report["executed"] = executed
    report["generation_failures"] = gen_failures[:PRESERVE_LIST_CAP]
    report["generation_failure_count"] = len(gen_failures)
    report["rejections"] = rejections[:PRESERVE_LIST_CAP]
    report["rejection_count"] = len(rejections)
    report["infrastructure_failures"] = infrastructure[:PRESERVE_LIST_CAP]
    report["infrastructure_failure_count"] = len(infrastructure)
    report["verdict_sets"] = {
        cid: {s: c[s] for s in VERDICT_ORDER if c[s]}
        for cid, c in sorted(verdict_sets.items())
    }
    report["findings_preserved"] = findings
    report["elapsed_s"] = round(time.monotonic() - started, 3)
    report["exit_code"] = _exit_code(report)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _exit_code(report: dict) -> int:
    """Same contract as replay: 2 generation failure; 4 behavioral
    difference (compiler rejection or constraint FAIL/ERROR); 3 the
    subject compiler never ran; 0 clean."""
    if report["generation_failure_count"]:
        return 2
    behavioral = bool(report["rejection_count"]) or any(
        set(c) & {"FAIL", "ERROR"} for c in report["verdict_sets"].values()
    )
    if behavioral:
        return 4
    if report["executed"] == 0:
        return 3
    return 0


def format_report(report: dict) -> str:
    b = report["budget"]
    lines = [
        f"unit: {report['unit']}  (subject revision "
        f"{report['subject_revision']})",
        f"spec hash: {report['recomputed_spec_hash']} "
        f"(matches manifest: {report['spec_hash_ok']})",
        f"runner: {report['runner']}",
        "budget: "
        + (f"seeds={b['seeds']}" if b["seeds"] is not None else "")
        + (" " if b["seeds"] is not None and b["duration_s"] is not None else "")
        + (f"duration={b['duration_s']}s" if b["duration_s"] is not None else "")
        + f" seed-base={b['seed_base']}  (elapsed {report['elapsed_s']}s)",
    ]
    if report.get("build_identity"):
        bid = report["build_identity"]
        lines.append(f"build identity: {bid['id']}  ({bid['command']})")
    lines.append(
        f"generated: {report['generated']} inputs, "
        f"{report['generation_failure_count']} generation failures"
    )
    if report["executed"] == 0:
        lines.append(
            "subject compiler runs: 0 — no output constraint was evaluated "
            "(this is an infrastructure outcome, not a pass)"
        )
    else:
        lines.append(
            f"subject compiler runs: {report['executed']} "
            f"({report['rejection_count']} rejections, "
            f"{report['infrastructure_failure_count']} infrastructure failures)"
        )
    for g in report["generation_failures"][:10]:
        lines.append(
            f"  GENERATION FAILURE seed {g['seed']} ({g['source']}): {g['error']}"
        )
    for r in report["rejections"][:10]:
        lines.append(
            f"  REJECTION seed {r['seed']} ({r['source']}): {r['detail']}"
        )
    for inf in report["infrastructure_failures"][:5]:
        lines.append(
            f"  INFRASTRUCTURE seed {inf['seed']} ({inf['source']}): {inf['detail']}"
        )
    if report["verdict_sets"]:
        lines.append("per-constraint verdict sets:")
        for cid, counts in report["verdict_sets"].items():
            parts = ", ".join(f"{k}={v}" for k, v in counts.items())
            lines.append(f"  {cid}: {parts}")
    lines.append(
        f"findings preserved: {report['findings_preserved']} under "
        f"{report['out_dir']}/findings"
    )
    lines.append(f"exit code: {report['exit_code']}")
    return "\n".join(lines)
