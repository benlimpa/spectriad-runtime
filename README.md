# spectriad-runtime

The public runtime for SpecTriad specification bundles: grammar-backed
input generation, an MLIR input/output constraint checker, a `replay`
command that deterministically re-evaluates a bundle unit's frozen seed
corpus against the current subject compiler, a `generate` command that
runs budgeted property-based testing over the unit's grammars, and a
`suite` command that runs every unit of a bundle checkout at once.

Pure Python. Installing and running needs **no Java**: the ANTLR
lexer/parser modules for the `.pg` grammar format are committed as
generated source, and the only ANTLR dependency is the pure-Python
`antlr4-python3-runtime`.

```
pip install spectriad-runtime
spectriad-runtime replay path/to/units/<unit-id>
spectriad-runtime generate path/to/units/<unit-id> --seeds 200
spectriad-runtime suite path/to/bundle-checkout
```

## What a bundle unit is

A bundle unit is one `units/<unit-id>/` directory of a SpecTriad
specification-bundle repository. Documentation is the unit's only
source, so its specification is a flat list of statements rather than
anything per-source:

```
units/<unit-id>/
  spec/structured_nl.yaml   `statements:` — the flat statement list.
                            Each statement has an id, a side
                            (input/output), its text, and the docs path
                            and source quote it was derived from. An
                            output statement may name the `generator:`
                            whose population its property is checked on.
  spec/input_constraints.yaml
  spec/output_spec.yaml     `constraints:` — flat lists. An output
                            constraint's `nl:` names its statement.
  spec/base.pg              shared IR well-formedness fragments. Never
                            run alone.
  spec/gen/<statement id>.pg
                            one generator per formalized input
                            statement, plus an optional `baseline`.
  pbt-provenance.json       per-property source-statement and code links
                            (when the exporting workspace recorded them)
  intent-freeze.json        write-once docs intent snapshot (when present)
  seeds/corpus.json         the frozen seed corpus: per seed, the
                            GENERATOR it was drawn from, the recorded
                            acceptance verdict, and the input content
                            hash (sha256, 12 hex). May be honestly
                            empty, in which case `generate` is the
                            meaningful mode for the unit.
  manifest.json             unit id, spec hash, subject source revision,
                            target runtime version, exporter identity
  runner.json               the unit's subject-runner declaration (when
                            the exporter carried one): `env` names the
                            command-prefix environment variable, `flags`
                            maps variant name to flag list; an optional
                            `profiles`/`default_profile` pair preserves
                            the exporting unit's full profile declaration
```

The grammar actually compiled and run is one generator composed over
the base, the generator's own text FIRST: a compiled generator roots at
the first nonterminal defined in the file, so a base placed ahead of it
would silently become the start rule. Input constraint rules are
verbatim excerpts of their generator.

An output constraint is evaluated only on the generators its statement
scopes it to. An explicit `generator:` wins; otherwise the `baseline`
generator claims the property, and absent a baseline a property that
names no generator constrains every input and is checked on all of
them. A property claiming something about one input population says
nothing about another, so it is never counted there.

The manifest names the declared subject source revision the properties
were generated from; running against a different revision measures that
other revision, not the bundle's provenance.

### Legacy schema 1 units

Units exported before the spec-only format carry three source columns
(docs / code / examples), one `spec/<source>.pg` grammar each, a
per-source `structured_nl.yaml`, and a corpus whose `source` field
names the generating column. They remain fully supported and behave
exactly as they did: every column's output constraints are evaluated on
every pair, under source-prefixed verdict ids (`docs/O1`). A unit is
recognized as spec-only when its manifest says `"schema": 2` or its
`structured_nl.yaml` has a flat `statements:` key; either marker alone
decides.

## The replay contract

`spectriad-runtime replay <unit-dir>`:

1. **Verifies the spec tree**: recomputes the spec hash over
   `spec/` and refuses a unit whose content drifted from its manifest.
2. **Regenerates every frozen seed's input** deterministically from the
   grammar the record names — its generator, composed over the base —
   with the bundled engine, and checks
   the sha256 of the regenerated text against the recorded
   `input_sha`. A mismatch is a loud failure (exit 2): downstream
   verdicts about a different input than the corpus froze are worthless.
3. **Runs the subject compiler** on each verified input. The runner
   declaration is env-var based: the declaration's `env` key names an
   environment variable holding a shell-split command prefix (a local
   binary, or e.g. `ssh host docker run --rm -i image /work/bin/opt`);
   the input is piped over stdin and the output read from stdout. Units
   exported with a `runner.json` need nothing beyond setting that
   environment variable; pass `--runner-env VAR --runner-flags
   "--the-pass"` to override the stored declaration or when the unit
   does not store one. With no compiler configured the run reports
   an infrastructure outcome (exit 3), never a fake pass.
4. **Evaluates the output constraints scoped to that seed's generator**
   on each fresh output and reports per-constraint verdict SETS
   (PASS / FAIL / STUB / ABSTAIN / NO_TRIGGER / ERROR counts), plus the
   acceptance comparison against the recorded verdicts.

Honest-verdict semantics are identical to the internal checker:
`ERROR` is not a violation, `STUB` means the check is not executable
here, `ABSTAIN` means the predicate declines to assert on the pair,
and a violation count of zero alone proves nothing — read the verdict
sets.

Replay is deterministic re-evaluation of a frozen corpus. It is not
property-based testing and is not described as such; `generate` is the
property-based-testing mode.

A unit whose seed corpus is empty is not a clean replay: there was
nothing to re-evaluate, and the run says so (exit 5) and names
`generate` as the meaningful mode for that unit.

## The generate contract

`spectriad-runtime generate <unit-dir> --seeds N` (and/or
`--duration SECONDS`; with both, whichever budget runs out first ends
the run):

1. **Verifies the spec tree** exactly as replay does.
2. **Draws fresh inputs from the unit's grammars** under the budget.
   The streams are the unit's generators (its source columns in a
   legacy unit), round-robined the way the internal campaign driver
   assigns them: streams are sorted and seed `s` draws from
   `streams[s % len(streams)]`. Seeds are sequential from `--seed-base`
   (default 0), so a run is reproducible from `(--seed-base, --seeds)`
   alone. There is no coverage-directed or novelty-based seed selection
   — sequential seeds are deliberate: two numbers reproduce the
   run, and that is sufficient for maintainer-side budgets.
3. **Runs the subject compiler** on each generated input, with the same
   runner declaration contract as replay (stored `runner.json`, or
   `--runner-env/--runner-flags` override). A compiler REJECTION of a
   grammar-conforming input is a behavioral finding here: the unit's
   input spec claims that input is in the pass's domain. With no
   compiler configured the run is an infrastructure outcome (exit 3),
   never a pass.
4. **Evaluates the output constraints scoped to that seed's generator**
   on each accepted pair, with the same honest verdict sets as replay.
5. **Preserves everything worth a second look** to the output directory
   (`--out`, default `spectriad-generate-<unit>`): each rejection and
   each constraint FAIL/ERROR pair keeps its input, output or
   diagnostics, per-constraint verdicts, and a `meta.json`; generation
   failures keep the generator error; `report.json` is always written.

## The suite contract

`spectriad-runtime suite <bundle-root>` runs a whole bundle checkout in
one command:

1. **Discovers every unit**: each directory holding a `manifest.json`
   beneath `units/` or `specs/`, sorted by path relative to the root.
   Discovering none is exit 1 with a message, never a clean zero over
   an empty set.
2. **Picks each unit's mode.** With `--mode auto` (the default) a unit
   with frozen seed records is REPLAYED and a unit whose corpus is
   empty falls back to GENERATION under `--generate-seeds N` (default
   50, seed base 0, so the run is reproducible from the count alone).
   `--mode replay` forces replay everywhere, so an empty-corpus unit
   reports NO-SEEDS rather than being covered for; `--mode generate`
   forces fresh-input property-based testing on every unit regardless
   of its corpus.
3. **Reports one line per unit** — `<unit-id>  <STATUS>  (<mode>, exit
   <n>, <k> seeds)  <note>` — then a summary line, and always writes a
   machine-readable `suite-report.json` (per-unit sub-reports plus the
   summary) under `--out` (default `spectriad-suite-out/`, with each
   unit's generate findings under `<out>/<unit-id>/`). `--json PATH`
   writes a second copy wherever you want it.
4. **Reduces the per-unit codes to one**: the suite exits with the
   highest effective code any unit contributed. A unit that will not
   load is BROKEN (exit 2), reported in place and never skipped: a
   suite that quietly drops the units it could not read reports a
   number about a smaller bundle than the one it was pointed at.

`--runner-env/--runner-flags` override every unit's stored runner
declaration, exactly as they do for a single unit.

### Drift expectations

A bundle may declare which units are known to drift, so a suite run
stays actionable without hiding anything. The file is JSON mapping unit
id to an expectation, read from `expectations.json` at the bundle root
when present and from `--expectations PATH` otherwise:

```json
{
  "some-unit": {
    "status": "known-drift",
    "note": "the pass drops the attribute; upstream issue not yet filed",
    "ref": "https://example.invalid/issues/1"
  }
}
```

`"status"` is `"clean"` (the default for any unit not listed) or
`"known-drift"`. An expected drifting unit that drifts reports
KNOWN-DRIFT and contributes 0, with its line and note still printed. An
expected drifting unit that comes back CLEAN reports UNEXPECTED-CLEAN
and contributes 4: the drift may have been fixed upstream, and the spec
has to be rechecked before the expectation is removed.

## Exit codes

One contract across all three modes:

| Code | Meaning |
| --- | --- |
| `0` | Clean run. |
| `1` | Usage or bundle error, or a suite that discovered no units. |
| `2` | Input regeneration hash mismatch, generation failure, or a unit that would not load. |
| `3` | The subject compiler never ran (not configured, or infrastructure failures only). Never a pass. |
| `4` | Behavioral difference: constraint FAIL/ERROR, acceptance drift, or a rejected generated input. |
| `5` | The unit's seed corpus is empty, so replay had nothing to re-evaluate; `generate` is the meaningful mode for it. |

A suite exits with the highest code any unit contributed, after
expectations are applied.

Optional oracle binaries, also env-var configured (unset means an
honest STUB, never a silent pass): `SPECTRIAD_UPSTREAM_MLIR_OPT`
(round-trip equivalence for raising passes) and
`SPECTRIAD_LOOM_DFG_SIM` (dataflow-simulator differential execution;
on a machine with a Loom build this is a local binary and needs no
remote plumbing).

## Layout

- `spectriad_runtime.pgen` — the `.pg` grammar engine: compiles a
  grammar into a Python generator module. `.g4` sources and the
  generated ANTLR parser modules live side by side.
- `spectriad_runtime.generation` — deterministic seeded generation on
  top of the engine (content-hash-cached compilation, subprocess
  isolation, timeout).
- `spectriad_runtime.checker` — the MLIR pair checker: xdsl-backed AST,
  feature library, trigger/rule constraint evaluator, sandboxed ad-hoc
  predicates, reference interpreter, and the external oracles.
- `spectriad_runtime.bundle` / `.replay` / `.generate` / `.suite` /
  `.cli` — bundle-unit loading (both schemas, generator composition and
  constraint scoping), the replay engine, the budgeted PBT engine, the
  whole-bundle suite driver, and the console script.

## Maintaining the grammar front end

The vendored parser modules (`src/spectriad_runtime/pgen/PgenLexer.py`,
`PgenParser.py`, `PgenParserListener.py` and the `.interp`/`.tokens`
files) are generated from `PgenLexer.g4` / `PgenParser.g4` with ANTLR
4.13.1 (matching the pinned `antlr4-python3-runtime` minor version).
Regenerate only when the `.g4` files change:

```
cd src/spectriad_runtime/pgen
uv run --with antlr4-tools antlr4 -v 4.13.1 -Dlanguage=Python3 PgenLexer.g4 PgenParser.g4
```

Java is needed only for that regeneration step, never by consumers.

## Releasing

Releases are manual and deliberate (no CI publishing):

1. Bump `version` in `pyproject.toml` and `__version__` in
   `src/spectriad_runtime/__init__.py`; update `CHANGELOG.md`.
2. `python -m build` (or `uv build`) to produce sdist + wheel.
3. Verify in a clean venv: `pip install dist/*.whl`,
   `python -c "import spectriad_runtime"`, and
   `spectriad-runtime replay` on a fixture unit — on a machine with no
   Java.
4. `twine upload dist/*` (PyPI credentials required).
5. Tag: `git tag v<version> && git push --tags`.
