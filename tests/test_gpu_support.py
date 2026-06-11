import unittest
from unittest.mock import patch

from gpu_support import (
    apply_gpu_config,
    auto_candidate_variants,
    gpu_help_message,
    normalize_preferred_device,
    normalize_runtime_variant,
    primary_vendor,
    recommended_directml_device_id,
    recommended_setup_onnx_variant,
    resolve_inference_device,
    select_best_runtime_result,
)


class GpuSupportTests(unittest.TestCase):
    def test_normalize_preferred_device_maps_amd_to_directml(self):
        self.assertEqual(normalize_preferred_device("amd"), "directml")
        self.assertEqual(normalize_preferred_device("AMD"), "directml")
        self.assertEqual(normalize_preferred_device("auto"), "auto")

    def test_normalize_runtime_variant_maps_amd_alias(self):
        self.assertEqual(normalize_runtime_variant("amd"), "directml")

    def test_primary_vendor_prefers_discrete_amd_over_intel(self):
        cards = [("intel", "Intel UHD"), ("amd", "AMD Radeon RX 7600")]
        self.assertEqual(primary_vendor(cards), "amd")

    def test_auto_candidates_skip_cuda_for_amd_only(self):
        self.assertEqual(
            auto_candidate_variants([("amd", "AMD Radeon RX 7600")]),
            ["directml", "cpu"],
        )

    def test_auto_candidates_include_cuda_for_nvidia(self):
        self.assertEqual(
            auto_candidate_variants([("nvidia", "NVIDIA GeForce RTX 4070")]),
            ["directml", "cuda", "cpu"],
        )

    def test_recommended_setup_variant_for_nvidia_is_cuda(self):
        self.assertEqual(recommended_setup_onnx_variant("nvidia"), "cuda")

    def test_recommended_setup_variant_for_amd_is_directml(self):
        self.assertEqual(recommended_setup_onnx_variant("amd_windows"), "directml")

    def test_recommended_setup_variant_for_cpu_only_is_cpu(self):
        self.assertEqual(recommended_setup_onnx_variant("cpu", []), "cpu")

    @patch("gpu_support._wmic_video_controllers", return_value=[
        "Intel UHD Graphics",
        "AMD Radeon RX 7600",
    ])
    def test_recommended_directml_device_id_picks_radeon(self, _):
        cards = [("amd", "AMD Radeon RX 7600"), ("intel", "Intel UHD Graphics")]
        self.assertEqual(recommended_directml_device_id(cards), "1")

    @patch("gpu_support._wmic_video_controllers", return_value=["AMD Radeon RX 7600"])
    def test_recommended_directml_device_id_auto_for_single_gpu(self, _):
        self.assertEqual(
            recommended_directml_device_id([("amd", "AMD Radeon RX 7600")]),
            "auto",
        )

    def test_apply_gpu_config_sets_directml_fields(self):
        config = {}
        apply_gpu_config(config, "directml", [("amd", "AMD Radeon RX 7600")])
        self.assertEqual(config["cpu_or_gpu"], "directml")

    def test_resolve_inference_device_maps_amd_auto_to_directml(self):
        cards = [("amd", "AMD Radeon RX 7600")]
        self.assertEqual(resolve_inference_device("auto", cards), "directml")

    def test_apply_gpu_config_resolves_auto_for_amd(self):
        config = {"directml_device_id": "auto"}
        apply_gpu_config(config, "auto", [("amd", "AMD Radeon RX 7600")])
        self.assertEqual(config["cpu_or_gpu"], "directml")

    def test_select_best_runtime_prefers_directml_on_amd(self):
        cards = [("amd", "AMD Radeon RX 7600")]
        results = [
            {"variant": "directml", "provider": "DmlExecutionProvider", "ips": 35.0, "ok": True},
            {"variant": "cpu", "provider": "CPUExecutionProvider", "ips": 40.0, "ok": True},
        ]
        best = select_best_runtime_result(results, cards)
        self.assertEqual(best["variant"], "directml")

    def test_gpu_help_message_for_amd_missing_provider(self):
        message = gpu_help_message("missing_gpu_provider", "amd")
        self.assertIn("directml", message.lower())
        self.assertNotIn("cuda", message.lower())

    def test_gpu_help_message_for_nvidia_missing_provider(self):
        message = gpu_help_message("missing_gpu_provider", "nvidia")
        self.assertIn("cuda", message.lower())


if __name__ == "__main__":
    unittest.main()
