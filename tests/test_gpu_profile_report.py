#!/usr/bin/env python3
"""Contract tests for runtime GPU timestamp log parsing."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/summarize_gpu_profile.py"
spec = importlib.util.spec_from_file_location("summarize_gpu_profile", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ProfileParsingTests(unittest.TestCase):
    def test_weighted_windows_and_hotspots(self):
        text = """
GPU profile: 30.00 ms/frame over 10 frames, 2 labels
  20.000 ms/frame   1.0/frame  Guest G-buffer
  10.000 ms/frame   2.0/frame  Compose
GPU profile: 40.00 ms/frame over 30 frames, 2 labels
  25.000 ms/frame   1.0/frame  Guest G-buffer
  15.000 ms/frame   2.0/frame  Compose
"""
        got = module.parse(text)
        self.assertEqual(got["windows"], 2)
        self.assertEqual(got["frames"], 40)
        self.assertAlmostEqual(got["mean_reported_gpu_ms"], 37.5)
        self.assertEqual(got["labels"][0][0], "Guest G-buffer")
        self.assertAlmostEqual(got["labels"][0][1], 23.75)
        self.assertAlmostEqual(got["labels"][1][1], 13.75)

    def test_empty_log(self):
        got = module.parse("Game started but no GPU timestamps are enabled.")
        self.assertEqual(got["frames"], 0)
        self.assertEqual(got["labels"], [])

if __name__ == "__main__":
    unittest.main()
