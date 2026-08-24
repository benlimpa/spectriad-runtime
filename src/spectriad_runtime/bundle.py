"""Loading exported specification-bundle units.

Two unit schemas exist, and this module reads both.

**Schema 2 (spec-only), the current export format.** Documentation is
the only source, so there are no source columns. The unit carries a
FLAT statement list, one shared well-formedness grammar base, and one
generator per formalized input statement::

  spec/structured_nl.yaml   `statements:` — a flat list; each statement
                            has id, side (input/output), text, path and
                            source_quote, and an output statement may
                            name the `generator:` its property is
                            checked on
  spec/input_constraints.yaml
  spec/output_spec.yaml     `constraints:` — flat lists; an output
                            constraint's `nl:` names its statement
  spec/base.pg              shared IR well-formedness fragments, never
                            run alone
  spec/gen/<id>.pg          one generator fragment per formalized input
                            statement (plus an optional `baseline`)
  seeds/corpus.json         frozen seed corpus: per seed, the GENERATOR
                            it was drawn from, the recorded acceptance
                            verdict, and the input content hash
                            (sha256, 12 hex chars). May be honestly
                            empty, in which case `generate` is the
                            meaningful mode for the unit.
  pbt-provenance.json       per-property source/code links (when present)
  intent-freeze.json        write-once docs intent snapshot (when present)
  manifest.json             unit id, spec hash, subject revision, target
                            runtime version, exporting workspace identity

**Schema 1 (legacy, three-source).** `spec/` carries one column per
source (docs / code / examples), one `spec/<source>.pg` grammar each,
and the corpus's `source` field names the generating column. Units in
this shape stay supported unchanged.

Schema discrimination mirrors the exporting side: a manifest saying
`"schema": 2` OR a `spec/structured_nl.yaml` with a flat `statements:`
key decides, either marker alone.

This module reads both layouts and recomputes the spec hash so a replay
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

#: The spec-only unit schema.
SPEC_ONLY_SCHEMA = 2
BASE_GRAMMAR_FILE = "spec/base.pg"
GEN_GRAMMAR_DIR = "spec/gen"
#: The generator an output statement gets when it names none.
BASELINE_GENERATOR = "baseline"


class BundleError(RuntimeError):
    pass


def spec_hash(unit_dir: Path) -> str:
    """Recompute the spec hash over the unit's spec tree.

    Mirrors the exporting side's algorithm: the spec YAML files, every
    `spec/*.pg` grammar and every `spec/gen/*.pg` generator, hashed in
    sorted relative-path order, plus the intent freeze's canonical
    digest when one is present. A schema-1 unit has no `spec/gen`, so
    its hash is unaffected; an edited generator is a spec change like
    any other.
    """
    unit_dir = Path(unit_dir)
    h = hashlib.sha256()
    rels = [
        *SPEC_FILES,
        *(f"spec/{p.name}" for p in (unit_dir / "spec").glob("*.pg")),
        *(f"{GEN_GRAMMAR_DIR}/{p.name}" for p in (unit_dir / "spec" / "gen").glob("*.pg")),
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
    """Load one bundle unit, in whichever schema it was exported.

    Common keys: "unit_dir", "manifest", "corpus", "spec_hash",
    "runner", "schema". `runner` is the unit's runner declaration when
    one is stored (runner.json, runner.yaml, or a `runner:` block in a
    derivations.yaml beside the spec), else None.

    A schema-1 unit adds "sources": each source column mapped to
    {"grammar_text", "output_constraints", "input_constraints",
    "statements"}.

    A schema-2 unit adds the flat "statements" list, "input_constraints"
    and "output_constraints" lists, "grammar_text" (the shared
    `spec/base.pg`, or "" when the unit ships none) and "generators"
    (generator id -> that generator's own fragment text).
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
    common = {
        "unit_dir": unit_dir,
        "manifest": manifest,
        "corpus": corpus,
        "spec_hash": spec_hash(unit_dir),
        "runner": _runner_declaration(unit_dir),
    }
    if _is_spec_only(manifest, nl):
        return {**common, "schema": SPEC_ONLY_SCHEMA, **_load_spec_only(unit_dir, nl, inp, outc)}

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
    return {**common, "schema": 1, "sources": sources}


def _is_spec_only(manifest: dict, nl: dict) -> bool:
    """Whether this unit is in the flat, source-free schema-2 shape.

    Either marker alone decides: the manifest's declared schema, or a
    structured_nl.yaml whose statements are a flat list rather than a
    per-source mapping.
    """
    if manifest.get("schema") == SPEC_ONLY_SCHEMA:
        return True
    return isinstance(nl, dict) and isinstance(nl.get("statements"), list)


def _load_spec_only(unit_dir: Path, nl: dict, inp: dict, outc: dict) -> dict:
    """The schema-2 half of `load_unit`: statements, constraints, grammars."""
    base = unit_dir / BASE_GRAMMAR_FILE
    generators: dict[str, str] = {}
    for p in sorted((unit_dir / "spec" / "gen").glob("*.pg")):
        generators[p.stem] = p.read_text()
    if not generators:
        # A bundle unit is post-gate. With no generator nothing can be
        # drawn and no property is ever exercised, so reporting anything
        # over an empty generator set would be a lie.
        raise BundleError(
            f"spec-only unit has no generators: {GEN_GRAMMAR_DIR}/<statement id>.pg "
            "is missing for every formalized input statement"
        )
    return {
        "statements": nl.get("statements") or [],
        "input_constraints": (inp or {}).get("constraints") or [],
        "output_constraints": (outc or {}).get("constraints") or [],
        "grammar_text": base.read_text() if base.is_file() else "",
        "generators": generators,
    }


def statement_grammar_text(unit: dict, generator_id: str) -> str:
    """The composed generator text for one spec-only generator.

    The base is never run alone and a generator fragment is never
    compiled without the base, so the composition is the unit of
    compilation.

    The generator's own text comes FIRST: a compiled generator roots at
    the first nonterminal defined in the file, so a base placed ahead of
    it would silently become the start rule and generate one shared
    fragment instead of the statement's input.
    """
    generators = unit.get("generators") or {}
    if generator_id not in generators:
        raise KeyError(f"no generator {GEN_GRAMMAR_DIR}/{generator_id}.pg in this unit")
    base = unit.get("grammar_text") or ""
    own = generators[generator_id].rstrip("\n")
    return f"{own}\n{base}" if base else own


def generator_ids(unit: dict) -> list[str]:
    """Every generator the unit can run, sorted. Includes any baseline."""
    return sorted(unit.get("generators") or {})


def statements_by_id(unit: dict) -> dict[str, dict]:
    return {str(s.get("id")): s for s in (unit.get("statements") or []) if s.get("id")}


def generator_for_statement(unit: dict, statement: dict) -> list[str]:
    """Which generators one output statement's property is checked on.

    A named `generator:` wins. Otherwise the baseline generator claims
    it; absent a baseline, a property that names no generator constrains
    every input and is therefore checked on all of them.
    """
    named = str(statement.get("generator") or "").strip()
    if named:
        return [named]
    gens = generator_ids(unit)
    if BASELINE_GENERATOR in gens:
        return [BASELINE_GENERATOR]
    return gens


def constraint_generators(unit: dict) -> dict[str, list[str]]:
    """Map each output-constraint id to the generators it is checked on."""
    by_id = statements_by_id(unit)
    out: dict[str, list[str]] = {}
    for c in unit.get("output_constraints") or []:
        cid = str(c.get("id") or "")
        statement = by_id.get(str(c.get("nl") or "")) or {}
        out[cid] = generator_for_statement(unit, statement)
    return out


def _runner_declaration(unit_dir: Path) -> dict | None:
    """The unit's stored runner declaration, when the export carried one.

    The bundle exporter writes `runner.json` beside `manifest.json`
    (schema: top-level `env` names the command-prefix environment
    variable, `flags` maps variant name to flag list; an optional
    `profiles`/`default_profile` pair carries the exporting unit's full
    profile declaration verbatim, for reference). The YAML fallbacks
    accept hand-assembled units. Explicit `--runner-env/--runner-flags`
    on the CLI override whatever is stored here.
    """
    runner_json = unit_dir / "runner.json"
    if runner_json.is_file():
        try:
            decl = json.loads(runner_json.read_text())
        except json.JSONDecodeError as e:
            raise BundleError(f"runner.json unreadable: {e}") from e
        if isinstance(decl, dict) and decl.get("env"):
            return decl
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
