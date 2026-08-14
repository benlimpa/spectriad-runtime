# Changelog

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
