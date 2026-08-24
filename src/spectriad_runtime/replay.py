"""Deterministic re-evaluation of a bundle unit's frozen seed corpus.

Replay is NOT property-based testing and is never described as such:
it re-runs the CURRENT subject compiler on each frozen seed's input and
evaluates the authored output constraints on the fresh output. Because
the inputs are regenerated from the unit's grammars (and verified
against the recorded content hashes), it catches behavioral drift
within seed coverage without golden-output diffing.

Honesty rules:

* A regenerated input whose hash does not match the recorded one is a
  loud failure, never silently substituted.
* ERROR and STUB are not violations, and `violations 0` alone proves
  nothing; the report surfaces the full per-constraint verdict SET
  (PASS / FAIL / STUB / ABSTAIN / NO_TRIGGER / ERROR counts).
* An unconfigured subject compiler is an infrastructure outcome, not a
  pass: the run reports the hash-check results it could obtain and
  says the compiler never ran.
* An empty seed corpus is not a clean replay: a unit exported with no
  frozen seeds has nothing to re-evaluate, and the run says so (exit 5)
  instead of reporting the vacuous zero.

Both unit schemas replay here. In a spec-only (schema 2) unit a
record's `source` is the GENERATOR it was drawn from, its input is
regenerated from that generator composed over `spec/base.pg`, and an
output constraint is evaluated only on the generators its statement
scopes it to.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import bundle, generation, runner
from .checker.ptc import check_constraint

VERDICT_ORDER = ("PASS", "FAIL", "STUB", "ABSTAIN", "NO_TRIGGER", "ERROR")


def _grammar_texts(unit: dict) -> dict[str, str]:
    """The grammar each generating stream draws from, keyed as the corpus
    keys it: source column in schema 1, generator id in schema 2 (where
    the text is the generator composed over the shared base)."""
    if unit["schema"] == bundle.SPEC_ONLY_SCHEMA:
        return {
            gid: bundle.statement_grammar_text(unit, gid)
            for gid in bundle.generator_ids(unit)
        }
    return {src: entry["grammar_text"] for src, entry in unit["sources"].items()}


def _unevaluated_constraints(unit: dict) -> list[str]:
    """Output constraints scoped onto no generator the unit carries.

    An authoring typo in a statement's `generator:` field would
    otherwise remove its constraint from every verdict set silently,
    and absence reads as covered. The report names such constraints so
    zero evaluations is loud, never mistaken for a pass.
    """
    if unit["schema"] != bundle.SPEC_ONLY_SCHEMA:
        return []
    gens = set(bundle.generator_ids(unit))
    return sorted(
        cid
        for cid, targets in bundle.constraint_generators(unit).items()
        if not set(targets) & gens
    )


def _scoped_constraints(unit: dict) -> dict[str, list[tuple[str, dict]]]:
    """Which output constraints are evaluated on a pair from each stream.

    Schema 1 evaluates every source column's constraints on every pair,
    under source-prefixed ids. Schema 2 evaluates a constraint only on
    the generators its statement scopes it to, under its bare id: a
    property claiming something about one input population says nothing
    about another, and counting it there would inflate the verdict set
    with pairs it never spoke about.
    """
    if unit["schema"] == bundle.SPEC_ONLY_SCHEMA:
        cgens = bundle.constraint_generators(unit)
        out: dict[str, list[tuple[str, dict]]] = {
            gid: [] for gid in bundle.generator_ids(unit)
        }
        for c in unit["output_constraints"]:
            cid = str(c.get("id"))
            for gid in cgens.get(cid, []):
                if gid in out:
                    out[gid].append((cid, c))
        return out
    every = [
        (f"{csrc}/{c.get('id')}", c)
        for csrc, entry in unit["sources"].items()
        for c in entry["output_constraints"]
    ]
    return {src: every for src in unit["sources"]}


def replay_unit(
    unit_dir: Path,
    runner_declaration: dict | None = None,
    *,
    limit: int | None = None,
    no_exec: bool = False,
    progress=None,
) -> dict:
    """Replay one bundle unit. Returns a machine-readable report.

    `runner_declaration` overrides the unit's stored declaration; when
    neither exists (or `no_exec` is set) the subject compiler is not
    invoked and the run is reported as `runner: not-configured`.
    """
    unit = bundle.load_unit(unit_dir)
    manifest = unit["manifest"]
    report: dict = {
        "unit": manifest.get("unit"),
        "schema": unit["schema"],
        "unit_dir": str(unit["unit_dir"]),
        "manifest_spec_hash": manifest.get("spec_hash"),
        "recomputed_spec_hash": unit["spec_hash"],
        "spec_hash_ok": manifest.get("spec_hash") == unit["spec_hash"],
        "subject_revision": manifest.get("subject_revision"),
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
    if no_exec:
        declaration = None
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

    records = unit["corpus"].get("records", [])
    # Decided on the RAW corpus: `--limit 0` is a caller's choice, an
    # empty export is a property of the unit.
    report["corpus_empty"] = not records
    if limit is not None:
        records = records[:limit]
    grammars = _grammar_texts(unit)
    scoped = _scoped_constraints(unit)
    hash_matched, mismatches, gen_failures = 0, [], []
    acceptance = {"agree": 0, "disagree": []}
    infrastructure = []
    verdict_sets: dict[str, Counter] = {}
    executed = 0

    for i, rec in enumerate(records):
        seed, src = rec.get("seed"), rec.get("source")
        if progress and i % 50 == 0:
            progress(f"seed {i + 1}/{len(records)}")
        grammar_text = grammars.get(src)
        if grammar_text is None:
            kind = "generator" if unit["schema"] == bundle.SPEC_ONLY_SCHEMA else "source"
            gen_failures.append(
                {"seed": seed, "source": src, "error": f"unknown {kind} {src!r}"}
            )
            continue
        try:
            text = generation.generate_from_text(
                grammar_text, seed, stem=f"{report['unit']}-{src}"
            )
        except RuntimeError as e:
            gen_failures.append(
                {"seed": seed, "source": src, "error": str(e)[:300]}
            )
            continue
        actual = bundle.input_sha(text)
        if actual != rec.get("input_sha"):
            mismatches.append(
                {
                    "seed": seed,
                    "source": src,
                    "recorded": rec.get("input_sha"),
                    "regenerated": actual,
                }
            )
            # A wrong input would make every downstream verdict about a
            # different input than the corpus froze; skip execution.
            continue
        hash_matched += 1
        if declaration is None:
            continue
        res = runner.run_subject(declaration, text)
        if not res["ok"] and res.get("failure_kind") == "infrastructure":
            infrastructure.append(
                {"seed": seed, "source": src, "detail": res["runner"][:200]}
            )
            continue
        executed += 1
        if res["ok"] != rec.get("accepted"):
            acceptance["disagree"].append(
                {
                    "seed": seed,
                    "source": src,
                    "recorded_accepted": rec.get("accepted"),
                    "replay_accepted": res["ok"],
                    "detail": res["runner"][:200],
                }
            )
        else:
            acceptance["agree"] += 1
        if not res["ok"]:
            continue
        for cid, constraint in scoped.get(src, []):
            v = check_constraint(constraint, text, res["output"])
            verdict_sets.setdefault(cid, Counter())[v.status] += 1

    report["seeds"] = {
        "total": len(records),
        "hash_matched": hash_matched,
        "hash_mismatched": len(mismatches),
        "generation_failures": len(gen_failures),
    }
    report["hash_mismatches"] = mismatches
    report["generation_failures"] = gen_failures
    report["executed"] = executed
    report["infrastructure_failures"] = infrastructure
    report["acceptance"] = acceptance
    report["verdict_sets"] = {
        cid: {s: c[s] for s in VERDICT_ORDER if c[s]}
        for cid, c in sorted(verdict_sets.items())
    }
    report["unevaluated_constraints"] = _unevaluated_constraints(unit)
    report["exit_code"] = _exit_code(report)
    return report


def _exit_code(report: dict) -> int:
    """0 clean; 2 hash mismatch or generation failure; 3 compiler never
    ran (not configured, or every configured run was an infrastructure
    failure); 4 behavioral difference (constraint FAIL/ERROR or
    acceptance disagreement); 5 the unit's seed corpus is empty, so
    there was nothing to replay and `generate` is the meaningful mode
    for it."""
    if report["corpus_empty"]:
        return 5
    if report["seeds"]["hash_mismatched"] or report["seeds"]["generation_failures"]:
        return 2
    behavioral = bool(report["acceptance"]["disagree"]) or any(
        set(c) & {"FAIL", "ERROR"} for c in report["verdict_sets"].values()
    )
    if behavioral:
        return 4
    if report["executed"] == 0:
        return 3
    return 0


def format_report(report: dict) -> str:
    lines = [
        f"unit: {report['unit']}  (subject revision "
        f"{report['subject_revision']})",
        f"spec hash: {report['recomputed_spec_hash']} "
        f"(matches manifest: {report['spec_hash_ok']})",
        f"runner: {report['runner']}",
    ]
    if report.get("build_identity"):
        b = report["build_identity"]
        lines.append(f"build identity: {b['id']}  ({b['command']})")
    if report.get("corpus_empty"):
        lines.append(
            "seed corpus: empty — this unit was exported with no frozen "
            "seeds, so replay re-evaluated nothing (not a clean run); "
            "`generate` is the meaningful mode for it"
        )
        lines.append(f"exit code: {report['exit_code']}")
        return "\n".join(lines)
    s = report["seeds"]
    lines.append(
        f"seeds: {s['total']} total, {s['hash_matched']} regenerated with "
        f"matching input hash, {s['hash_mismatched']} MISMATCHED, "
        f"{s['generation_failures']} generation failures"
    )
    for m in report["hash_mismatches"][:10]:
        lines.append(
            f"  HASH MISMATCH seed {m['seed']} ({m['source']}): recorded "
            f"{m['recorded']}, regenerated {m['regenerated']}"
        )
    for g in report["generation_failures"][:10]:
        lines.append(
            f"  GENERATION FAILURE seed {g['seed']} ({g['source']}): {g['error']}"
        )
    if report["executed"] == 0:
        lines.append(
            "subject compiler runs: 0 — no output constraint was evaluated "
            "(this is an infrastructure outcome, not a pass)"
        )
    else:
        lines.append(
            f"subject compiler runs: {report['executed']} "
            f"(acceptance agrees on {report['acceptance']['agree']}, "
            f"disagrees on {len(report['acceptance']['disagree'])})"
        )
    for d in report["acceptance"]["disagree"][:10]:
        lines.append(
            f"  ACCEPTANCE DRIFT seed {d['seed']} ({d['source']}): recorded "
            f"accepted={d['recorded_accepted']}, replay "
            f"accepted={d['replay_accepted']}: {d['detail']}"
        )
    for i in report["infrastructure_failures"][:5]:
        lines.append(
            f"  INFRASTRUCTURE seed {i['seed']} ({i['source']}): {i['detail']}"
        )
    if report["verdict_sets"]:
        lines.append("per-constraint verdict sets:")
        for cid, counts in report["verdict_sets"].items():
            parts = ", ".join(f"{k}={v}" for k, v in counts.items())
            lines.append(f"  {cid}: {parts}")
    for cid in report.get("unevaluated_constraints", []):
        lines.append(
            f"  WARNING {cid}: scoped onto no generator this unit carries "
            "— never evaluated (not covered)"
        )
    lines.append(f"exit code: {report['exit_code']}")
    return "\n".join(lines)
