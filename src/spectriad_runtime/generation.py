"""Grammar-backed input generation.

A source's input specification IS a `.pg` grammar: the joint structural
grammar with the source's semantic constraints as executable annotations
(state variables, quoted predicates, boundary-weighted alternatives).
Generating a conforming input means compiling that grammar with the
bundled pgen engine and running the compiled generator — the same
artifact the spec displays is the artifact that generates.

Compilation is cached in a content-hash-keyed directory (override with
SPECTRIAD_PG_CACHE). The compiled generator runs in a subprocess so a
constraint set that cannot be satisfied (root restarts loop forever by
design) is cut off by a timeout instead of hanging the caller.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from .pgen.main import main as pgen_compile

GENERATE_TIMEOUT_S = 20


def _cache_dir() -> Path:
    env = os.environ.get("SPECTRIAD_PG_CACHE")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / f"spectriad-pg-cache-{os.getuid()}"


# Runs inside this interpreter's subprocess (which has rstr, the
# compiled generator's one runtime dependency). Seeding the global
# `random` module makes generation reproducible: the generated code
# calls the module-level functions.
_BOOTSTRAP = textwrap.dedent(
    """
    import importlib.util
    import random
    import sys

    gen_path, seed = sys.argv[1], int(sys.argv[2])
    random.seed(seed)
    spec = importlib.util.spec_from_file_location("pg_generated", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The corpus grammars bound recursion by counters (unrolled store
    # lists, case lists), not by depth; the engine's static depth cap
    # would starve those recursions of candidates, so raise it.
    mod.__dict__["__max_depth"] = max(mod.__dict__.get("__max_depth", 0), 500)
    result = mod.generate_root()
    sys.stdout.write(result)
    """
)


def compile_grammar_text(text: str, stem: str = "grammar") -> Path:
    """Compile `.pg` grammar source text to a Python generator module.

    Cached by content hash. The engine's ANTLR front end reads an ASCII
    FileStream, so a grammar with non-ASCII bytes is rejected here with
    a clear message rather than failing cryptically at compile time.
    """
    try:
        text.encode("ascii")
    except UnicodeEncodeError as e:
        raise RuntimeError(
            f".pg grammars must be ASCII (offending byte at position {e.start})"
        )
    digest = hashlib.sha256(text.encode()).hexdigest()[:16]
    cache = _cache_dir()
    out = cache / f"{stem}-{digest}.py"
    if not out.exists():
        cache.mkdir(parents=True, exist_ok=True)
        pg_src = cache / f"{stem}-{digest}.pg"
        pg_src.write_text(text)
        pgen_compile(str(pg_src), str(out))
    return out


def generate_from_text(text: str, seed: int, stem: str = "grammar") -> str:
    """Generate one input conforming to the grammar, deterministically.

    Returns the generated text. Raises RuntimeError when generation
    fails or times out (e.g. unsatisfiable constraints).
    """
    gen_py = compile_grammar_text(text, stem)
    argv = [sys.executable, "-c", _BOOTSTRAP, str(gen_py), str(seed)]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=GENERATE_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"generation timed out after {GENERATE_TIMEOUT_S}s "
            f"(grammar {stem}, seed {seed})"
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"generation failed (grammar {stem}, seed {seed}):\n"
            f"{proc.stderr.strip()}"
        )
    return proc.stdout
