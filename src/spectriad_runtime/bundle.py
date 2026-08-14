"""Loading exported specification-bundle units.

A bundle unit directory (one `units/<unit-id>/` tree of a bundle
repository) carries::

  spec/                 structured NL statements, input grammars (.pg),
                        and input/output constraints, one column per source
  pbt-provenance.json   per-property source/code links (when present)
  intent-freeze.json    write-once docs intent snapshot (when present)
  seeds/corpus.json     frozen seed corpus: per seed, the generating
                        source column, the recorded acceptance verdict,
                        and the input content hash (sha256, 12 hex chars)
  manifest.json         unit id, spec hash, subject revision, target
                        runtime version, exporting workspace identity

This module reads that layout and recomputes the spec hash so a replay
can refuse a unit whose spec tree no longer matches its manifest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

SOURCES = ["docs", "code", "examples"]
SPEC_FILES = (
    "spec/structured_nl.yaml",
    "spec/input_constraints.yaml",
    "spec/output_spec.yaml",
    "spec/implementation_plan.yaml",
)
INTENT_FREEZE_FILE = "intent-freeze.json"


class BundleError(RuntimeError):
    pass


def spec_hash(unit_dir: Path) -> str:
    """Recompute the spec hash over the unit's spec tree.

    Mirrors the exporting side's algorithm: the spec YAML files and
    every `spec/*.pg` grammar, hashed in sorted relative-path order,
    plus the intent freeze's canonical digest when one is present.
    """
    unit_dir = Path(unit_dir)
    h = hashlib.sha256()
    rels = [
        *SPEC_FILES,
        *(f"spec/{p.name}" for p in sorted((unit_dir / "spec").glob("*.pg"))),
    ]
    for rel in sorted(rels):
        f = unit_dir / rel
        if f.exists():
            h.update(rel.encode())
            h.update(f.read_bytes())
    freeze = unit_dir / INTENT_FREEZE_FILE
    if freeze.exists():
        try:
            artifact = json.loads(freeze.read_text())
            digest = artifact["intent_sha256"]
        except (json.JSONDecodeError, KeyError) as e:
            raise BundleError(f"unreadable intent freeze: {e}") from e
        h.update(INTENT_FREEZE_FILE.encode())
        h.update(str(digest).encode())
    return h.hexdigest()[:16]


def load_unit(unit_dir: Path) -> dict:
    """Load one bundle unit: manifest, seed corpus, and per-source specs.

    Returns {"unit_dir", "manifest", "corpus", "sources", "spec_hash",
    "runner"}. `sources` maps each source column to {"grammar_text",
    "output_constraints", "input_constraints", "statements"}. `runner`
    is the unit's runner declaration when one is stored (runner.yaml or
    a `runner:` block in a derivations.yaml beside the spec), else None.
    """
    unit_dir = Path(unit_dir).resolve()
    manifest_path = unit_dir / "manifest.json"
    if not manifest_path.is_file():
        raise BundleError(f"{unit_dir} is not a bundle unit (no manifest.json)")
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        raise BundleError(f"manifest.json unreadable: {e}") from e
    corpus_path = unit_dir / "seeds" / "corpus.json"
    try:
        corpus = json.loads(corpus_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise BundleError(f"seeds/corpus.json unreadable: {e}") from e
    try:
        nl = yaml.safe_load((unit_dir / "spec/structured_nl.yaml").read_text()) or {}
        inp = (
            yaml.safe_load((unit_dir / "spec/input_constraints.yaml").read_text())
            or {}
        )
        outc = yaml.safe_load((unit_dir / "spec/output_spec.yaml").read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        raise BundleError(f"spec file unreadable: {e}") from e
    sources: dict[str, dict] = {}
    for src in SOURCES:
        if src not in nl:
            continue
        gpath = unit_dir / f"spec/{src}.pg"
        if not gpath.is_file():
            raise BundleError(f"missing grammar spec/{src}.pg")
        sources[src] = {
            "statements": nl[src] or [],
            "grammar_text": gpath.read_text(),
            "input_constraints": (inp.get(src) or {}).get("constraints", []),
            "output_constraints": (outc.get(src) or {}).get("constraints", []),
        }
    if not sources:
        raise BundleError("spec/structured_nl.yaml names no known source")
    return {
        "unit_dir": unit_dir,
        "manifest": manifest,
        "corpus": corpus,
        "sources": sources,
        "spec_hash": spec_hash(unit_dir),
        "runner": _runner_declaration(unit_dir),
    }


def _runner_declaration(unit_dir: Path) -> dict | None:
    """The unit's stored runner declaration, when the export carried one."""
    for rel in ("runner.yaml", "derivations.yaml", "spec/runner.yaml"):
        p = unit_dir / rel
        if not p.is_file():
            continue
        try:
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as e:
            raise BundleError(f"{rel} unreadable: {e}") from e
        decl = data.get("runner") if "runner" in data else data
        if isinstance(decl, dict) and decl.get("env"):
            return decl
    return None


def input_sha(text: str) -> str:
    """The frozen corpus's input content hash: sha256, first 12 hex chars."""
    return hashlib.sha256(text.encode()).hexdigest()[:12]
