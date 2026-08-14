"""The `spectriad-runtime` command line.

Currently one mode:

  spectriad-runtime replay <bundle-unit-dir> [options]

Exit codes: 0 clean replay; 1 usage or bundle error; 2 input
regeneration hash mismatch or generation failure; 3 the subject
compiler never ran (not configured, or infrastructure failures only);
4 behavioral difference (constraint FAIL/ERROR or acceptance drift).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, bundle, replay


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
        "--runner-env",
        help="environment variable holding the subject compiler command "
        "prefix (overrides the unit's stored runner declaration)",
    )
    rp.add_argument(
        "--runner-flags",
        help="flags passed to the subject compiler, one shell-quoted string",
    )
    rp.add_argument(
        "--limit", type=int, help="replay only the first N seed records"
    )
    rp.add_argument(
        "--no-exec",
        action="store_true",
        help="regenerate and hash-check inputs only; never invoke the "
        "subject compiler",
    )
    rp.add_argument("--json", dest="json_out", help="also write the report as JSON")
    rp.add_argument(
        "--quiet", action="store_true", help="suppress progress output"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "replay":  # pragma: no cover
        return 1
    declaration = None
    if args.runner_env:
        import shlex

        declaration = {
            "env": args.runner_env,
            "flags": {"head": shlex.split(args.runner_flags or "")},
        }
    progress = None
    if not args.quiet:
        progress = lambda msg: print(f"[replay] {msg}", file=sys.stderr, flush=True)
    try:
        report = replay.replay_unit(
            Path(args.unit_dir),
            declaration,
            limit=args.limit,
            no_exec=args.no_exec,
            progress=progress,
        )
    except (bundle.BundleError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(replay.format_report(report))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2) + "\n")
    return report["exit_code"]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
