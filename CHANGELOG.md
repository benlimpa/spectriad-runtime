# Changelog

## 0.3.0 — 2026-08-24

- **Spec-only (schema 2) units.** The current export format is now the
  primary one: a flat `statements:` list instead of source columns, one
  shared `spec/base.pg` of well-formedness fragments, and one
  `spec/gen/<statement id>.pg` generator per formalized input
  statement. The generator actually compiled is the statement's own
  fragment followed by the base — own text FIRST, because a compiled
  generator roots at the first nonterminal in the file and a base
  placed ahead of it would silently become the start rule. A seed
  record's `source` names the GENERATOR it was drawn from, and
  `generate` round-robins the sorted generator list the same way it
  round-robined source columns.
- **Generator-scoped constraint evaluation.** An output constraint is
  evaluated only on the generators its statement scopes it to: an
  explicit `generator:` wins, otherwise the `baseline` generator claims
  it, and absent a baseline a property that names no generator is
  checked on every generator. Verdict sets are keyed by the bare
  constraint id. A property that claims something about one input
  population says nothing about another, so counting it there would
  inflate the verdict set with pairs it never spoke about.
- **`spec_hash` covers `spec/gen/*.pg`.** An edited generator is a spec
  change like any other. Schema-1 units have no `spec/gen`, so their
  hashes are unchanged.
- **Exit 5: the seed corpus is honestly empty.** A unit exported with
  no frozen seeds has nothing to replay; that is not a clean run, and
  it no longer falls into exit 3. The report says so and names
  `generate` as the meaningful mode for the unit.
- **`spectriad-runtime suite <bundle-root>`.** Discovers every unit
  under `units/` and `specs/`, runs each, and reduces their exit codes
  to one. `--mode auto` (the default) replays a unit with seed records
  and generates over one whose corpus is empty; `--mode replay` and
  `--mode generate` force one mode on every unit. A unit that will not
  load is reported BROKEN (exit 2), never skipped and never counted
  clean; discovering no units is exit 1, never a clean zero over an
  empty set. An `expectations.json` (unit id -> `{"status":
  "clean"|"known-drift", "note": ...}`, default at the bundle root,
  `--expectations` to override) suppresses a known-drifting unit's exit
  code but never its line, and flags the reverse transition: a unit
  expected to drift that comes back CLEAN is UNEXPECTED-CLEAN and
  exits 4, because the spec has to be rechecked before the expectation
  is dropped. `suite-report.json` is always written under `--out`.
- Legacy schema-1 (three-source) units replay and generate exactly as
  before, byte for byte.

## 0.2.0 — 2026-08-13

- `spectriad-runtime generate <bundle-unit-dir>`: budgeted
  property-based testing — fresh inputs from the unit's grammars under
  a `--seeds` and/or `--duration` budget (`--seed-base` for
  determinism), source columns round-robined like the internal
  campaign driver, output constraints evaluated on accepted pairs with
  the same honest PASS/FAIL/STUB/ABSTAIN/NO_TRIGGER/ERROR verdict
  sets as replay. Rejections, constraint failures, and generation
  failures are preserved to an output directory (input, output or
  diagnostics, per-constraint verdicts, meta). Exit codes follow the
  replay contract; a run where the compiler never executed is an
  infrastructure outcome (exit 3), never a pass. Seed selection is
  sequential (no coverage-directed selection in v0.2, deliberately).
- Bundle units now carry an optional `runner.json` (written by the
  SpecTriad bundle exporter): both `replay` and `generate` read the
  stored runner declaration automatically, with explicit
  `--runner-env/--runner-flags` still overriding it.

## 0.1.0 — 2026-08-13

Initial release.

- `.pg` grammar engine (`spectriad_runtime.pgen`) with vendored
  ANTLR 4.13.1 parser modules: no Java on the consumer path.
- Deterministic seeded generation (`spectriad_runtime.generation`).
- MLIR pair checker (`spectriad_runtime.checker`): xdsl-backed AST,
  feature library, trigger/rule evaluator with honest
  PASS/FAIL/STUB/ABSTAIN/NO_TRIGGER/ERROR verdicts, sandboxed ad-hoc
  predicates, reference interpreter, external oracles.
- `spectriad-runtime replay <bundle-unit-dir>`: spec-hash
  verification, per-seed input regeneration with content-hash checks,
  env-var-declared subject-compiler execution, per-constraint verdict
  sets, acceptance comparison.
