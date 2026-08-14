# spectriad-runtime

The public runtime for SpecTriad specification bundles: grammar-backed
input generation, an MLIR input/output constraint checker, and a
`replay` command that deterministically re-evaluates a bundle unit's
frozen seed corpus against the current subject compiler.

Pure Python. Installing and running needs **no Java**: the ANTLR
lexer/parser modules for the `.pg` grammar format are committed as
generated source, and the only ANTLR dependency is the pure-Python
`antlr4-python3-runtime`.

```
pip install spectriad-runtime
spectriad-runtime replay path/to/units/<unit-id>
```

## What a bundle unit is

A bundle unit is one `units/<unit-id>/` directory of a SpecTriad
specification-bundle repository:

```
units/<unit-id>/
  spec/                 structured NL statements, input grammars (.pg),
                        and input/output constraints, one column per
                        source (docs / code / examples)
  pbt-provenance.json   per-property source-statement and code links
                        (when the exporting workspace recorded them)
  intent-freeze.json    write-once docs intent snapshot (when present)
  seeds/corpus.json     the frozen seed corpus: per seed, the generating
                        source column, the recorded acceptance verdict,
                        and the input content hash (sha256, 12 hex)
  manifest.json         unit id, spec hash, subject source revision,
                        target runtime version, exporter identity
```

Each source column's spec states only what that source states; input
constraint rules are verbatim excerpts of their grammar. The manifest
names the declared subject source revision the properties were
generated from; replaying against a different revision measures that
other revision, not the bundle's provenance.

## The replay contract

`spectriad-runtime replay <unit-dir>`:

1. **Verifies the spec tree**: recomputes the spec hash over
   `spec/` and refuses a unit whose content drifted from its manifest.
2. **Regenerates every frozen seed's input** deterministically from the
   recorded source column's grammar with the bundled engine, and checks
   the sha256 of the regenerated text against the recorded
   `input_sha`. A mismatch is a loud failure (exit 2): downstream
   verdicts about a different input than the corpus froze are worthless.
3. **Runs the subject compiler** on each verified input. The runner
   declaration is env-var based: the declaration's `env` key names an
   environment variable holding a shell-split command prefix (a local
   binary, or e.g. `ssh host docker run --rm -i image /work/bin/opt`);
   the input is piped over stdin and the output read from stdout. Pass
   `--runner-env VAR --runner-flags "--the-pass"` when the unit does
   not store a declaration. With no compiler configured the run reports
   an infrastructure outcome (exit 3), never a fake pass.
4. **Evaluates the output constraints** of every source column on each
   fresh output and reports per-constraint verdict SETS
   (PASS / FAIL / STUB / ABSTAIN / NO_TRIGGER / ERROR counts), plus the
   acceptance comparison against the recorded verdicts.

Honest-verdict semantics are identical to the internal checker:
`ERROR` is not a violation, `STUB` means the check is not executable
here, `ABSTAIN` means the predicate declines to assert on the pair,
and a violation count of zero alone proves nothing — read the verdict
sets.

Replay is deterministic re-evaluation of a frozen corpus. It is not
property-based testing and is not described as such; a generative mode
is planned separately.

Exit codes: `0` clean replay; `1` usage or bundle error; `2` input
regeneration hash mismatch or generation failure; `3` the subject
compiler never ran; `4` behavioral difference (constraint FAIL/ERROR
or acceptance drift).

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
- `spectriad_runtime.bundle` / `.replay` / `.cli` — bundle-unit
  loading, the replay engine, and the console script.

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
