"""The `spectriad-runtime` command line.

Three modes:

  spectriad-runtime replay <bundle-unit-dir> [options]
  spectriad-runtime generate <bundle-unit-dir> --seeds N|--duration S [options]
  spectriad-runtime suite <bundle-root> [options]

`replay` deterministically re-evaluates one unit's frozen seed corpus;
`generate` is budgeted property-based testing over fresh inputs from
that unit's grammars; `suite` discovers every unit of a bundle
checkout, runs each in the mode it can answer for, and reduces their
exit codes to one under an optional drift-expectation file.

Every mode reads a unit's stored runner declaration (`runner.json`,
written by the bundle exporter) when one is present; explicit
`--runner-env/--runner-flags` override it.

Exit codes (shared contract): 0 clean; 1 usage or bundle error, or a
suite that discovered no units; 2 input regeneration hash mismatch,
generation failure, or a unit that would not load; 3 the subject
compiler never ran (not configured, or infrastructure failures only);
4 behavioral difference (constraint FAIL/ERROR, acceptance drift, or a
rejected generated input); 5 the unit's seed corpus is empty, so
replay had nothing to re-evaluate and `generate` is the meaningful
mode for it. A suite exits with the highest code any unit contributed,
after expectations are applied.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from . import __version__, bundle, generate, replay, suite


def _add_runner_arguments(sub: argparse.ArgumentParser) -> None:
    sub.add_argument(
        "--runner-env",
        help="environment variable holding the subject compiler command "
        "prefix (overrides the unit's stored runner declaration)",
    )
    sub.add_argument(
        "--runner-flags",
        help="flags passed to the subject compiler, one shell-quoted string",
    )
    sub.add_argument("--json", dest="json_out", help="also write the report as JSON")
    sub.add_argument(
        "--quiet", action="store_true", help="suppress progress output"
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="spectriad-runtime")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    rp = sub.add_parser(
        "replay",
        help="re-evaluate a bundle unit's frozen seed corpus against the "
        "current subject compiler",
    )
    rp.add_argument("unit_dir", help="path to a bundle units/<unit-id>/ directory")
    rp.add_argument(
        "--limit", type=int, help="replay only the first N seed records"
    )
    rp.add_argument(
        "--no-exec",
        action="store_true",
        help="regenerate and hash-check inputs only; never invoke the "
        "subject compiler",
    )
    _add_runner_arguments(rp)

    gp = sub.add_parser(
        "generate",
        help="budgeted property-based testing: fresh inputs from the "
        "unit's grammars against the current subject compiler",
    )
    gp.add_argument("unit_dir", help="path to a bundle units/<unit-id>/ directory")
    gp.add_argument(
        "--seeds", type=int, help="generate exactly N fresh inputs"
    )
    gp.add_argument(
        "--duration",
        type=float,
        help="generate for at most this many wall-clock seconds",
    )
    gp.add_argument(
        "--seed-base",
        type=int,
        default=0,
        help="first seed value; a run is reproducible from "
        "(--seed-base, --seeds) alone (default 0)",
    )
    gp.add_argument(
        "--out",
        help="output directory for preserved findings and report.json "
        "(default spectriad-generate-<unit> in the working directory)",
    )
    _add_runner_arguments(gp)

    sp = sub.add_parser(
        "suite",
        help="discover and run every unit of a bundle checkout, reducing "
        "their exit codes to one",
    )
    sp.add_argument("root", help="path to a specification-bundle checkout")
    sp.add_argument(
        "--mode",
        choices=("auto", "replay", "generate"),
        default="auto",
        help="auto replays a unit with seed records and generates over one "
        "whose corpus is empty; replay and generate force one mode on "
        "every unit (default auto)",
    )
    sp.add_argument(
        "--generate-seeds",
        type=int,
        default=suite.DEFAULT_GENERATE_SEEDS,
        help="seed budget for each unit run in generate mode "
        f"(default {suite.DEFAULT_GENERATE_SEEDS})",
    )
    sp.add_argument(
        "--out",
        help="output directory for per-unit findings and suite-report.json "
        f"(default {suite.DEFAULT_OUT_DIR} in the working directory)",
    )
    sp.add_argument(
        "--expectations",
        help="drift-expectation file: unit id -> {\"status\": "
        "\"clean\"|\"known-drift\", \"note\": ...} "
        f"(default {suite.EXPECTATIONS_FILE} at the bundle root when present)",
    )
    _add_runner_arguments(sp)
    return p


def _declaration(args) -> dict | None:
    if not args.runner_env:
        return None
    return {
        "env": args.runner_env,
        "flags": {"head": shlex.split(args.runner_flags or "")},
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    progress = None
    if not args.quiet:
        progress = lambda msg: print(
            f"[{args.command}] {msg}", file=sys.stderr, flush=True
        )
    try:
        if args.command == "replay":
            report = replay.replay_unit(
                Path(args.unit_dir),
                _declaration(args),
                limit=args.limit,
                no_exec=args.no_exec,
                progress=progress,
            )
            print(replay.format_report(report))
        elif args.command == "suite":
            report = suite.run_suite(
                Path(args.root),
                _declaration(args),
                mode=args.mode,
                generate_seeds=args.generate_seeds,
                out_dir=Path(args.out) if args.out else None,
                expectations_path=(
                    Path(args.expectations) if args.expectations else None
                ),
                progress=progress,
            )
            print(suite.format_report(report))
        else:
            if args.seeds is None and args.duration is None:
                print(
                    "error: generate needs a budget: --seeds N and/or "
                    "--duration SECONDS",
                    file=sys.stderr,
                )
                return 1
            report = generate.generate_unit(
                Path(args.unit_dir),
                _declaration(args),
                seeds=args.seeds,
                duration=args.duration,
                seed_base=args.seed_base,
                out_dir=Path(args.out) if args.out else None,
                progress=progress,
            )
            print(generate.format_report(report))
    except (bundle.BundleError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
    return report["exit_code"]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
