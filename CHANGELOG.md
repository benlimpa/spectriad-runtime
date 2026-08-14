# Changelog

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
