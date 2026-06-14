import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from perf_profiler import PerfProfiler, configure_profiler, get_profiler
from runtime_metrics import read_metrics, write_metrics


class PerfProfilerTests(unittest.TestCase):
    def test_rollup_computes_stage_stats(self):
        profiler = PerfProfiler({"perf_instrumentation": "yes"})
        profiler.record("main_onnx", 20.0)
        profiler.record("main_onnx", 30.0)
        profiler.record("play_main", 55.0)
        rollup = profiler.rollup(ips=10.0, feed_fps=60.0, game_state="match")
        self.assertEqual(rollup["stages"]["main_onnx"]["count"], 2)
        self.assertEqual(rollup["stages"]["main_onnx"]["avg_ms"], 25.0)
        self.assertIn("bottleneck", rollup)

    def test_classify_cpu_inference_fallback(self):
        profiler = PerfProfiler({"perf_instrumentation": "yes"})
        profiler.set_inference_health({"inference_health": {"using_cpu_despite_gpu": True}})
        rollup = {"stages": {}, "counters": {}, "loop_ms": {"avg_ms": 0.0, "total_ms": 0.0}}
        label = profiler.classify_bottleneck(rollup, ips=5.0, feed_fps=60.0)
        self.assertEqual(label, "cpu_inference_fallback")

    def test_disabled_profiler_is_noop(self):
        configure_profiler({"perf_instrumentation": "no", "perf_auto_when_ips_below": 0})
        profiler = get_profiler()
        with profiler.time_stage("play_main"):
            pass
        self.assertEqual(profiler.rollup(), {})

    def test_auto_enable_when_ips_low(self):
        profiler = PerfProfiler({"perf_instrumentation": "no", "perf_auto_when_ips_below": 12.0})
        profiler.maybe_auto_enable(8.0)
        self.assertTrue(profiler.enabled)


class RuntimeMetricsPerfTests(unittest.TestCase):
    def test_write_read_metrics_with_perf_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime_metrics.json"
            perf = {"bottleneck": "inference_bound", "stages": {"main_onnx": {"avg_ms": 12.0}}}
            system = {"primary_gpu": "Test GPU"}
            write_metrics(path, 15.0, 60.0, [15.0], perf=perf, system=system)
            data = read_metrics(path)
            self.assertEqual(data["ips"], 15.0)
            self.assertEqual(data["perf"]["bottleneck"], "inference_bound")
            self.assertEqual(data["system"]["primary_gpu"], "Test GPU")

    def test_read_metrics_backward_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime_metrics.json"
            path.write_text(
                json.dumps({"ips": 9.0, "feed_fps": 30.0, "history": [9.0]}),
                encoding="utf-8",
            )
            data = read_metrics(path)
            self.assertNotIn("perf", data)
            self.assertEqual(data["feed_fps"], 30.0)


class InferenceHealthTests(unittest.TestCase):
    @patch("gpu_runtime_install.smoke_test_variant")
    @patch("tools.python_runtime.probe_runtime_imports")
    @patch("tools.launcher_bat.candidate_python_commands")
    @patch("inference_health.detect_graphics_cards", return_value=[("nvidia", "NVIDIA GeForce GTX 960")])
    @patch("inference_health.primary_vendor", return_value="nvidia")
    @patch("inference_health.resolve_inference_device", return_value="cuda")
    def test_preflight_audit_uses_project_venv_python(
        self,
        mock_resolve,
        mock_vendor,
        mock_cards,
        mock_candidates,
        mock_probe,
        mock_smoke,
    ):
        from inference_health import audit_inference_for_preflight

        mock_candidates.return_value = [
            ("pinned", [r"C:\project\.venv\Scripts\python.exe"]),
            ("py-3.11-64", ["py", "-3.11-64"]),
        ]
        mock_probe.return_value = {
            "ok": True,
            "executable": r"C:\project\.venv\Scripts\python.exe",
            "versions": {
                "onnxruntime_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
        }
        mock_smoke.return_value = {
            "ok": True,
            "provider": "CUDAExecutionProvider",
            "ips": 46.5,
        }

        health = audit_inference_for_preflight({"cpu_or_gpu": "cuda"})
        self.assertFalse(health["inference_health"]["missing_gpu_provider"])
        self.assertEqual(health["provider_summary"], "CUDA")
        self.assertIn("46.5", health["preflight_detail"])

    @patch("inference_health.detect_graphics_cards", return_value=[("nvidia", "NVIDIA GeForce RTX 3060")])
    @patch("inference_health.primary_vendor", return_value="nvidia")
    @patch("inference_health.resolve_inference_device", return_value="cuda")
    @patch("inference_health._has_physical_gpu", return_value=True)
    @patch("onnxruntime.get_available_providers", return_value=["CUDAExecutionProvider", "CPUExecutionProvider"])
    @patch("gpu_runtime_install.verify_cuda_dlls", return_value=(False, ["cudnn64_9.dll"]))
    def test_evaluate_flags_missing_cuda_dlls(self, *_mocks):
        from inference_health import evaluate_gpu_runtime_status

        status = evaluate_gpu_runtime_status({"cpu_or_gpu": "auto"})
        self.assertTrue(status["needs_repair"])
        self.assertEqual(status["reason"], "missing_cuda_dlls")

    @patch("inference_health.detect_graphics_cards", return_value=[("amd", "AMD Radeon RX 7900 XT")])
    @patch("inference_health.primary_vendor", return_value="amd")
    @patch("inference_health.resolve_inference_device", return_value="directml")
    @patch("inference_health._has_physical_gpu", return_value=True)
    @patch("onnxruntime.get_available_providers", return_value=["CPUExecutionProvider"])
    def test_evaluate_flags_missing_gpu_provider(self, *_mocks):
        from inference_health import evaluate_gpu_runtime_status

        status = evaluate_gpu_runtime_status({"cpu_or_gpu": "directml"})
        self.assertTrue(status["needs_repair"])
        self.assertEqual(status["reason"], "missing_gpu_provider")

    @patch("inference_health.detect_graphics_cards", return_value=[("nvidia", "NVIDIA GeForce RTX 3060")])
    @patch("inference_health.primary_vendor", return_value="nvidia")
    @patch("inference_health.resolve_inference_device", return_value="cuda")
    def test_audit_flags_cpu_despite_gpu(self, *_mocks):
        from unittest.mock import Mock

        from inference_health import audit_inference_setup

        detector = Mock()
        detector.get_provider_info.return_value = {
            "requested": "CUDAExecutionProvider",
            "actual": "CPUExecutionProvider",
            "model_path": "models/mainInGameModel.onnx",
        }
        detector.detect_objects.return_value = {}

        play = Mock()
        play.Detect_main_info = detector
        play.Detect_tile_detector = None
        play.Detect_close_tile_detector = None

        health = audit_inference_setup(play, {"cpu_or_gpu": "auto"})
        self.assertTrue(health["inference_health"]["using_cpu_despite_gpu"])
        self.assertEqual(health["provider_summary"], "CPU(!)")


if __name__ == "__main__":
    unittest.main()
