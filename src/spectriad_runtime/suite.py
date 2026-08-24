"""Running every unit of a specification bundle in one command.

A bundle checkout holds many units. `suite` discovers them, picks the
mode each unit can actually answer for, runs it, and reduces the
per-unit exit codes to one.

Mode selection (`--mode auto`, the default): a unit with frozen seed
records is REPLAYED, and a unit whose corpus is honestly empty falls
back to budgeted GENERATION, because an empty corpus means replay has
nothing to re-evaluate rather than that the unit is clean. `--mode
replay` and `--mode generate` force one mode on every unit: forcing
replay reports an empty-corpus unit as NO-SEEDS rather than covering
for it, and forcing generate runs fresh-input property-based testing
across the whole bundle.

Honesty rules:

* A unit that fails to load is BROKEN and carries exit 2. It is never
  skipped and never counted as clean: a suite that quietly drops the
  units it could not read reports a number about a smaller bundle than
  the one it was pointed at.
* No units discovered is exit 1, never a clean 0 over an empty set.
* Drift expectations (`expectations.json`) suppress a unit's exit code,
  never its line: a known-drift unit still prints its status and its
  note. An expected-drifting unit that comes back CLEAN is flagged
  (UNEXPECTED-CLEAN, effective 4), not silently accepted — the drift
  may have been fixed upstream, and the spec has to be rechecked before
  the expectation is dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import bundle, generate, replay

DEFAULT_GENERATE_SEEDS = 50
DEFAULT_OUT_DIR = "spectriad-suite-out"
EXPECTATIONS_FILE = "expectations.json"

#: Observed per-unit exit code -> the status it reports under.
STATUS_BY_CODE = {
    0: "CLEAN",
    2: "BROKEN",
    3: "NO-RUNNER",
    4: "DRIFT",
    5: "NO-SEEDS",
}


def discover_units(root: Path) -> list[Path]:
    """Every bundle unit under a bundle checkout, sorted by relative path.

    A unit is any directory holding a `manifest.json` beneath `units/`
    or `specs/`. The root itself is never a unit: pointing the suite at
    a single unit directory is what `replay`/`generate` are for.
    """
    root = Path(root).resolve()
    found: set[Path] = set()
    for top in ("units", "specs"):
        base = root / top
        if not base.is_dir():
            continue
        for manifest in base.rglob("manifest.json"):
            if manifest.is_file():
                found.add(manifest.parent)
    found.discard(root)
    return sorted(found, key=lambda p: str(p.relative_to(root)))


def load_expectations(root: Path, path: Path | None = None) -> dict:
    """The drift-expectation map: unit id -> {status, note, ref}.

    `--expectations` wins; otherwise `expectations.json` at the bundle
    root is used when it exists. A missing default file is not an error
    (a bundle need not declare any expectation); a named file that
    cannot be read is.
    """
    if path is not None:
        p = Path(path)
    else:
        p = Path(root) / EXPECTATIONS_FILE
        if not p.is_file():
            return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise bundle.BundleError(f"expectations file unreadable: {e}") from e
    if not isinstance(data, dict):
        raise bundle.BundleError(
            f"{p}: expectations must be an object mapping unit id -> "
            '{"status": "clean"|"known-drift", "note": ...}'
        )
    return data


def _effective(observed: int, expectation: dict | None) -> tuple[str, int]:
    """A unit's reported status and the exit code it contributes."""
    expected = str((expectation or {}).get("status") or "clean")
    if expected == "known-drift":
        if observed == 4:
            return "KNOWN-DRIFT", 0
        if observed == 0:
            # Possibly fixed upstream. Flagged rather than accepted: the
            # spec has to be rechecked before the expectation is removed.
            return "UNEXPECTED-CLEAN", 4
    return STATUS_BY_CODE.get(observed, "BROKEN"), observed


def run_suite(
    root: Path,
    runner_declaration: dict | None = None,
    *,
    mode: str = "auto",
    generate_seeds: int = DEFAULT_GENERATE_SEEDS,
    out_dir: Path | None = None,
    expectations_path: Path | None = None,
    progress=None,
) -> dict:
    """Run every discovered unit of a bundle checkout. Returns a report.

    `mode` is "auto" (replay a seeded unit, generate over an empty one),
    "replay", or "generate". `runner_declaration` overrides each unit's
    stored declaration exactly as it does for a single unit.
    """
    if mode not in ("auto", "replay", "generate"):
        raise ValueError(f"unknown suite mode {mode!r}")
    root = Path(root).resolve()
    out_dir = Path(out_dir) if out_dir else Path(DEFAULT_OUT_DIR)
    expectations = load_expectations(root, expectations_path)
    unit_dirs = discover_units(root)

    report: dict = {
        "mode": "suite",
        "root": str(root),
        "out_dir": str(out_dir),
        "unit_mode": mode,
        "generate_seeds": generate_seeds,
        "units": [],
    }
    if not unit_dirs:
        report["summary"] = {"units": 0}
        report["exit_code"] = 1
        report["error"] = (
            f"no bundle units found under {root}: expected unit directories "
            "holding a manifest.json beneath units/ or specs/"
        )
        return report

    out_dir.mkdir(parents=True, exist_ok=True)
    for i, unit_dir in enumerate(unit_dirs):
        rel = str(unit_dir.relative_to(root))
        unit_id = unit_dir.name
        if progress:
            progress(f"unit {i + 1}/{len(unit_dirs)}: {rel}")
        row = _run_one(
            unit_dir,
            runner_declaration,
            mode=mode,
            generate_seeds=generate_seeds,
            out_dir=out_dir / unit_id,
        )
        row["unit"] = row.get("unit") or unit_id
        row["path"] = rel
        expectation = expectations.get(row["unit"]) or expectations.get(rel)
        status, effective = _effective(row["exit_code"], expectation)
        row["status"] = status
        row["effective_exit_code"] = effective
        if expectation:
            row["expectation"] = expectation
        report["units"].append(row)

    counts: dict[str, int] = {}
    for row in report["units"]:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report["summary"] = {"units": len(report["units"]), "by_status": counts}
    report["exit_code"] = max(r["effective_exit_code"] for r in report["units"])
    (out_dir / "suite-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def _run_one(
    unit_dir: Path,
    runner_declaration: dict | None,
    *,
    mode: str,
    generate_seeds: int,
    out_dir: Path,
) -> dict:
    """One unit's sub-report. A load or run error is BROKEN, not a crash:
    one unreadable unit must not take the rest of the bundle with it."""
    try:
        if mode == "generate":
            chosen = "generate"
        elif mode == "replay":
            chosen = "replay"
        else:
            unit = bundle.load_unit(unit_dir)
            chosen = "replay" if unit["corpus"].get("records") else "generate"
        if chosen == "replay":
            sub = replay.replay_unit(unit_dir, runner_declaration)
            seeds = sub["seeds"]["total"] if not sub["corpus_empty"] else 0
        else:
            sub = generate.generate_unit(
                unit_dir,
                runner_declaration,
                seeds=generate_seeds,
                seed_base=0,
                out_dir=out_dir,
            )
            seeds = sub["generated"]
    except (bundle.BundleError, OSError) as e:
        return {
            "unit": unit_dir.name,
            "mode": mode if mode != "auto" else None,
            "exit_code": 2,
            "seeds": 0,
            "note": str(e)[:300],
            "report": None,
        }
    return {
        "unit": sub.get("unit"),
        "mode": chosen,
        "exit_code": sub["exit_code"],
        "seeds": seeds,
        "note": _note(sub, chosen),
        "report": sub,
    }


def _note(sub: dict, chosen: str) -> str:
    """The one-line reason a unit's code is what it is."""
    if sub["exit_code"] == 5:
        return "seed corpus empty; generate is the meaningful mode"
    if sub["exit_code"] == 3:
        return f"subject compiler never ran ({sub['runner']})"
    bad = sorted(
        cid for cid, c in sub["verdict_sets"].items() if set(c) & {"FAIL", "ERROR"}
    )
    parts = []
    if chosen == "replay":
        s = sub["seeds"]
        if s["hash_mismatched"]:
            parts.append(f"{s['hash_mismatched']} input hash mismatches")
        if s["generation_failures"]:
            parts.append(f"{s['generation_failures']} generation failures")
        if sub["acceptance"]["disagree"]:
            parts.append(
                f"{len(sub['acceptance']['disagree'])} acceptance disagreements"
            )
    else:
        if sub["generation_failure_count"]:
            parts.append(f"{sub['generation_failure_count']} generation failures")
        if sub["rejection_count"]:
            parts.append(f"{sub['rejection_count']} rejections")
    if bad:
        parts.append("FAIL/ERROR on " + ", ".join(bad))
    return "; ".join(parts)


def format_report(report: dict) -> str:
    if not report["units"]:
        return f"error: {report.get('error', 'no units')}\nexit code: 1"
    lines = []
    width = max(len(r["unit"] or "?") for r in report["units"])
    for r in report["units"]:
        line = (
            f"{(r['unit'] or '?').ljust(width)}  {r['status']}  "
            f"({r['mode'] or 'unloadable'}, exit {r['exit_code']}, "
            f"{r['seeds']} seeds)"
        )
        note = r.get("note") or ""
        if r["status"] == "KNOWN-DRIFT":
            expected_note = (r.get("expectation") or {}).get("note")
            if expected_note:
                note = f"{note} [expected: {expected_note}]" if note else (
                    f"[expected: {expected_note}]"
                )
        if r["status"] == "UNEXPECTED-CLEAN":
            note = (
                "expected known drift, observed clean: recheck the spec "
                "before removing the expectation"
            )
        lines.append(f"{line}  {note}".rstrip())
    s = report["summary"]
    by = ", ".join(f"{k}={v}" for k, v in sorted(s["by_status"].items()))
    lines.append(f"{s['units']} units: {by}")
    lines.append(f"reports under {report['out_dir']}")
    lines.append(f"exit code: {report['exit_code']}")
    return "\n".join(lines)
