import unittest

from spectriad_runtime.generation import generate_from_text

GRAMMAR = "start: 'hello ' name;\nname: 'world' | 'there';\n"


class GenerationTest(unittest.TestCase):
    def test_deterministic_per_seed(self):
        a = generate_from_text(GRAMMAR, 5)
        b = generate_from_text(GRAMMAR, 5)
        self.assertEqual(a, b)
        self.assertIn(a, ("hello world", "hello there"))

    def test_seeds_cover_alternatives(self):
        outputs = {generate_from_text(GRAMMAR, s) for s in range(12)}
        self.assertEqual(outputs, {"hello world", "hello there"})

    def test_non_ascii_rejected_clearly(self):
        with self.assertRaises(RuntimeError) as ctx:
            generate_from_text("start: 'héllo';\n", 1)
        self.assertIn("ASCII", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
