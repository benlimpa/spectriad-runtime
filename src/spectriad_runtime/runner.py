"""Subject-compiler invocation for replay.

The runner declaration is env-var based, same contract as the internal
prototype: the environment variable named by the declaration's `env`
key holds a COMMAND PREFIX, split shell-style, so a remote toolchain
works too:

  # local binary
  export SPECTRIAD_LOOM_RAISE_OPT=/path/to/loom-raise-opt
  # remote build (input piped over stdin, output read from stdout,
  # so nothing is copied to the remote)
  export SPECTRIAD_LOOM_RAISE_OPT='ssh host docker run --rm -i image /work/bin/opt'

The per-variant flags come from the declaration's `flags` mapping; the
replay CLI uses the first declared variant, matching the internal
campaign's behavior.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess

RUN_TIMEOUT_S = 60


class RunnerNotConfigured(RuntimeError):
    """The declaration's environment variable is unset or empty."""


def resolve_command(declaration: dict) -> list[str]:
    """The shell-split command prefix this declaration resolves to.

    Raises RunnerNotConfigured when the env var is unset: replay never
    substitutes a canned output for a real run.
    """
    env_var = declaration.get("env")
    if not env_var:
        raise RunnerNotConfigured("runner declaration has no `env` key")
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        raise RunnerNotConfigured(
            f"environment variable {env_var} is unset; the subject "
            "compiler is not configured"
        )
    return shlex.split(raw)


def default_variant(declaration: dict) -> str:
    flags = declaration.get("flags") or {}
    if not flags:
        raise RunnerNotConfigured("runner declaration has no variant flags")
    return next(iter(flags))


def run_subject(
    declaration: dict, input_text: str, variant: str | None = None
) -> dict:
    """Pipe the input through the declared opt tool (local or remote).

    Returns {"output", "runner", "ok", "failure_kind"?}. `failure_kind`
    distinguishes a compiler rejection from an infrastructure failure
    when `ok` is false.
    """
    command = resolve_command(declaration)
    variant = variant or default_variant(declaration)
    flags = (declaration.get("flags") or {}).get(variant)
    if flags is None:
        raise RunnerNotConfigured(
            f"runner declaration has no flags for variant {variant!r}"
        )
    argv = [*command, *flags, "-"]
    label = " ".join(flags)
    try:
        proc = subprocess.run(
            argv,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "runner": f"binary ({label}): timed out",
            "ok": False,
            "failure_kind": "infrastructure",
        }
    if proc.returncode != 0:
        infrastructure = bool(
            command and command[0] == "ssh" and proc.returncode == 255
        )
        return {
            "output": proc.stderr,
            "runner": f"binary ({label}): exit {proc.returncode}",
            "ok": False,
            "failure_kind": (
                "infrastructure" if infrastructure else "compiler_rejection"
            ),
        }
    return {"output": proc.stdout, "runner": f"binary ({label})", "ok": True}


def build_identity(declaration: dict) -> dict | None:
    """Identify the binary behind the declaration, or None if unset.

    The resolved command (which carries the build directory) and the
    tool's own `--version` banner both go in; the pair is hashed to a
    short `id`. A failed or unsupported `--version` is not an error:
    the command string alone still identifies the build selection.
    """
    try:
        command = resolve_command(declaration)
    except RunnerNotConfigured:
        return None
    key = " ".join(command)
    version = ""
    try:
        proc = subprocess.run(
            [*command, "--version"], capture_output=True, text=True, timeout=60
        )
        if proc.returncode == 0:
            lines = [
                ln.strip()
                for ln in (proc.stdout + proc.stderr).splitlines()
                if ln.strip()
            ]
            version = "\n".join(lines[:6])
    except (OSError, subprocess.SubprocessError):
        version = ""
    return {
        "command": key,
        "version": version,
        "id": hashlib.sha256(f"{key}\n{version}".encode()).hexdigest()[:12],
    }
