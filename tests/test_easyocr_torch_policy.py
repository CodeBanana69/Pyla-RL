"""Policy helpers for EasyOCR GPU vs CPU (CUDA vs ROCm / AMD breakage)."""

from __future__ import annotations

import unittest

import utils


class EasyOcrTorchPolicyTests(unittest.TestCase):
    def test_miopen_trace_triggers_fallback_flag(self):
        exc = RuntimeError(
            "MIOpen(HIP): Error [Compile] HIPRTC_ERROR_COMPILATION (6) "
            "fatal error: 'type_traits'"
        )
        self.assertTrue(utils._easyocr_failure_needs_cpu_fallback(exc))

    def test_generic_runtime_error_no_fallback_substring(self):
        self.assertFalse(utils._easyocr_failure_needs_cpu_fallback(RuntimeError("invalid tensor")))


if __name__ == "__main__":
    unittest.main()
