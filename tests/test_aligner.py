import unittest

from src.core.aligner import Aligner


class AlignerTests(unittest.TestCase):
    def test_unmatched_prefix_stays_near_first_anchor(self):
        lines = [
            "Кровь на рукаве\n",
            "Просыпаюсь в темноте\n",
        ]
        asr_words = [
            {"word": "Просыпаюсь", "start": 67.50, "end": 67.90},
            {"word": "в", "start": 68.00, "end": 68.10},
            {"word": "темноте", "start": 68.40, "end": 68.80},
        ]

        result = Aligner().align(lines, asr_words)

        self.assertEqual(len(result), 2)
        self.assertGreater(result[0][0], 60.0)
        self.assertLess(result[0][0], result[1][0])
        self.assertAlmostEqual(result[1][0], 67.50)

    def test_replace_does_not_create_unrelated_anchor(self):
        lines = ["кровь на рукаве\n"]
        asr_words = [
            {"word": "полностью", "start": 42.0, "end": 42.4},
            {"word": "другие", "start": 42.5, "end": 42.8},
            {"word": "слова", "start": 42.9, "end": 43.2},
        ]

        result = Aligner().align(lines, asr_words)

        self.assertEqual(result, [(0.0, "кровь на рукаве")])

    def test_unmatched_tail_moves_forward(self):
        lines = [
            "hello\n",
            "missing tail\n",
        ]
        asr_words = [
            {"word": "hello", "start": 10.0, "end": 10.4},
        ]

        result = Aligner().align(lines, asr_words)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], (10.0, "hello"))
        self.assertGreater(result[1][0], result[0][0])


if __name__ == "__main__":
    unittest.main()
