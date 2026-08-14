"""Stub subject compiler for the replay end-to-end test.

Reads a module on stdin and writes the "transformed" module on stdout.
The transformation is the identity, so every preservation constraint
holds. STUB_OPT_MODE=drop-arith deletes the arith operation line
instead, which must surface as a FAIL verdict, never be hidden.
STUB_OPT_MODE=reject exits nonzero, a compiler rejection.
"""

import os
import sys


def main() -> int:
    text = sys.stdin.read()
    mode = os.environ.get("STUB_OPT_MODE", "identity")
    if mode == "reject":
        sys.stderr.write("stub-opt: rejecting input\n")
        return 1
    if mode == "drop-arith":
        # An honest defect injection: the load-bearing op disappears.
        # The dropped SSA result would leave a dangling use, so return
        # a constant-free rewrite that still parses.
        text = text.replace("arith.addi", "arith.subi").replace(
            "arith.muli", "arith.subi"
        )
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
