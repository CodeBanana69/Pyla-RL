import os
import platform
import threading
import warnings
from pathlib import Path

import cv2
import numpy as np
from cuda_runtime_paths import add_cuda_dll_directories

add_cuda_dll_directories()
import onnxruntime as ort

from gpu_support import (
    describe_directml_adapter,
    gpu_help_message,
    normalize_preferred_device,
    primary_vendor,
    resolve_directml_device_id,
    resolve_inference_device,
)
from utils import load_toml_as_dict, resolve_project_path

warnings.filterwarnings(
    "ignore",
    message=".*'pin_memory' argument is set as true but no accelerator is found.*",
    category=UserWarning,
)

debug = load_toml_as_dict("cfg/general_config.toml")["super_debug"] == "yes"

_GPU_PROVIDERS = frozenset({"CUDAExecutionProvider", "DmlExecutionProvider"})
_gpu_inference_lock = threading.Lock()
_cuda_runtime_failed = threading.Event()


def gpu_provider_requires_serial_inference(provider) -> bool:
    return _provider_name(provider) in _GPU_PROVIDERS


def get_optimal_threads(max_limit=4):
    general_config = load_toml_as_dict("cfg/general_config.toml")
    configured_threads = general_config.get("used_threads", general_config.get("onnx_cpu_threads", "auto"))
    if str(configured_threads).strip().lower() != "auto":
        try:
            threads_amount = max(1, int(configured_threads))
            print(f"Using configured ONNX CPU threads: {threads_amount}.")
            return threads_amount
        except (TypeError, ValueError):
            print(f"Ignoring invalid used_threads={configured_threads!r}; falling back to auto.")

    threads = os.cpu_count() or 2
    threads_amount = min(max(2, threads // 2), max_limit)
    print(f"Detected {threads} CPU threads, using {threads_amount} threads.")
    return threads_amount


_provider_message_printed = False
_provider_fallback_warning_printed = False
_runtime_provider_fallback_warning_printed = False


def _directml_provider():
    config = load_toml_as_dict("cfg/general_config.toml")
    device_id = resolve_directml_device_id(config.get("directml_device_id", "auto"))
    if str(device_id).strip().lower() in ("", "auto", "none"):
        return "DmlExecutionProvider"
    try:
        adapter_index = int(device_id)
        print(describe_directml_adapter(adapter_index))
        return ("DmlExecutionProvider", {"device_id": adapter_index})
    except (TypeError, ValueError):
        print(f"Ignoring invalid directml_device_id={device_id!r}; using default DirectML adapter.")
        return "DmlExecutionProvider"


def _cuda_provider_options():
    return (
        "CUDAExecutionProvider",
        {
            "cudnn_conv_algo_search": "EXHAUSTIVE",
            "cudnn_conv_use_max_workspace": "1",
            "do_copy_in_default_stream": "1",
            "use_tf32": "1",
        },
    )


def _build_providers(preferred_device):
    global _provider_message_printed
    requested_device = normalize_preferred_device(preferred_device)
    preferred_device = resolve_inference_device(requested_device)
    if preferred_device == "cuda" and primary_vendor() == "amd":
        print(
            "WARNING: CUDA was requested on an AMD GPU system. "
            "Using DirectML instead. Run: py -3.11-64 tools\\fix_gpu_runtime.py directml"
        )
        preferred_device = "directml"
    available_providers = set(ort.get_available_providers())
    providers = []

    if preferred_device == "cuda" and "CUDAExecutionProvider" in available_providers:
        providers.append(_cuda_provider_options())
    elif preferred_device in ("directml", "dml") and "DmlExecutionProvider" in available_providers:
        providers.append(_directml_provider())
    elif preferred_device == "openvino" and "OpenVINOExecutionProvider" in available_providers:
        providers.append("OpenVINOExecutionProvider")

    providers.append("CPUExecutionProvider")
    if not _provider_message_printed:
        selected = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
        if selected == "CPUExecutionProvider":
            print(
                f"Using CPU inference. Available ONNX providers: {', '.join(ort.get_available_providers())}. "
                f"Python={platform.python_version()} {platform.architecture()[0]}."
            )
            if preferred_device in ("directml", "dml", "cuda", "openvino") or requested_device in ("auto", "gpu"):
                print(gpu_help_message("missing_gpu_provider", provider=selected))
        else:
            print(
                f"Using {selected} for ONNX inference with CPU fallback. "
                f"Available ONNX providers: {', '.join(ort.get_available_providers())}. "
                f"Python={platform.python_version()} {platform.architecture()[0]}."
            )
        _provider_message_printed = True
    return providers


def _provider_name(provider):
    return provider[0] if isinstance(provider, tuple) else provider


def _fallback_providers_after_runtime_failure(failed_provider):
    failed_provider = _provider_name(failed_provider)
    available_providers = set(ort.get_available_providers())
    providers = []
    # CUDA illegal-memory failures poison the device context; switch straight to CPU.
    if failed_provider == "CUDAExecutionProvider":
        return ["CPUExecutionProvider"]
    if failed_provider != "DmlExecutionProvider" and "DmlExecutionProvider" in available_providers:
        providers.append(_directml_provider())
    providers.append("CPUExecutionProvider")
    return providers


def _configure_session_options_for_provider(session_options, provider_name):
    if provider_name == "DmlExecutionProvider":
        session_options.enable_mem_pattern = False
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # DmlFusedNode crashes on some Windows GPU/driver combos; run unfused kernels instead.
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        session_options.add_session_config_entry("ep.dml.disable_graph_fusion", "1")
    elif provider_name == "CUDAExecutionProvider":
        session_options.add_session_config_entry("gpu_mem_limit", "2147483648")
        session_options.add_session_config_entry("arena_extend_strategy", "kSameAsRequested")


def _fp16_model_path(model_path: str) -> str:
    path = Path(model_path)
    return str(path.with_name(f"{path.stem}.fp16{path.suffix}"))


def _use_fp16_models() -> bool:
    general = load_toml_as_dict("cfg/general_config.toml")
    return str(general.get("onnx_fp16", "yes")).strip().lower() in ("yes", "true", "1", "on")


def _fp16_allowed_for_provider(provider_name: str) -> bool:
    # DirectML is unstable with converted FP16 graphs on many Windows GPUs.
    return provider_name == "CUDAExecutionProvider" and _use_fp16_models()


def _session_input_numpy_dtype(session) -> np.dtype:
    type_str = str(session.get_inputs()[0].type or "tensor(float)")
    if "float16" in type_str:
        return np.float16
    return np.float32


def _ensure_fp16_model(model_path: str) -> str | None:
    if not _use_fp16_models():
        return None
    fp16_path = _fp16_model_path(model_path)
    if os.path.exists(fp16_path):
        try:
            if os.path.getmtime(fp16_path) >= os.path.getmtime(model_path):
                return fp16_path
        except OSError:
            return fp16_path
    try:
        import onnx
        from onnxconverter_common import float16
    except ImportError:
        print("onnxconverter-common not installed; using FP32 ONNX models.")
        return None

    try:
        print(f"Converting {os.path.basename(model_path)} to FP16...")
        model = onnx.load(model_path)
        fp16_model = float16.convert_float_to_float16(model, keep_io_types=True)
        onnx.save(fp16_model, fp16_path)
        return fp16_path
    except Exception as exc:
        print(f"FP16 conversion failed for {model_path}: {exc}")
        return None


def _make_inference_probe(model, device, classes, ignore_classes, input_size, model_path):
    probe = Detect.__new__(Detect)
    probe.model_path = model_path
    probe.model = model
    probe.device = device
    probe.input_name = model.get_inputs()[0].name
    probe.output_names = [output.name for output in model.get_outputs()]
    probe.classes = classes
    probe.ignore_classes = ignore_classes
    probe.input_size = input_size
    probe._input_dtype = _session_input_numpy_dtype(model)
    probe._padded_img_buffer = np.full(
        (1, 3, input_size[0], input_size[1]),
        128.0 / 255.0,
        dtype=probe._input_dtype,
    )
    probe._last_resized_w = 0
    probe._last_resized_h = 0
    probe._use_io_binding = False
    probe._io_binding = None
    probe._input_ortvalue = None
    probe._allow_runtime_fallback = False
    return probe


def _detection_signature(results: dict) -> tuple:
    signature = []
    for class_name in sorted(results.keys()):
        boxes = results.get(class_name) or []
        signature.append((class_name, len(boxes)))
    return tuple(signature)


def _validate_fp16_against_fp32(fp32_detector, fp16_detector) -> bool:
    warmup = np.full((480, 640, 3), 128, dtype=np.uint8)
    try:
        fp32_result = fp32_detector.detect_objects(warmup, conf_tresh=0.25)
        fp16_result = fp16_detector.detect_objects(warmup, conf_tresh=0.25)
    except Exception as exc:
        print(f"FP16 validation inference failed: {exc}")
        return False

    fp32_sig = _detection_signature(fp32_result)
    fp16_sig = _detection_signature(fp16_result)
    if fp32_sig == fp16_sig:
        return True

    fp32_count = sum(count for _, count in fp32_sig)
    fp16_count = sum(count for _, count in fp16_sig)
    if fp32_count == 0 and fp16_count == 0:
        return True
    if fp32_count == 0:
        return fp16_count <= 2
    ratio = fp16_count / max(fp32_count, 1)
    if 0.5 <= ratio <= 1.5:
        return True
    print(f"FP16 validation mismatch: fp32={fp32_sig} fp16={fp16_sig}")
    return False


def _numpy_nms(boxes, scores, iou_threshold=0.6):
    if len(boxes) == 0:
        return np.array([], dtype=np.int32)

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        order = order[np.where(iou <= iou_threshold)[0] + 1]

    return np.array(keep, dtype=np.int32)


def _batched_nms(boxes_xyxy, confidences, class_ids, iou_thresh=0.6):
    if boxes_xyxy.size == 0:
        return []

    results = []
    offset = 0
    for class_id in np.unique(class_ids):
        class_mask = class_ids == class_id
        class_boxes = boxes_xyxy[class_mask]
        class_scores = confidences[class_mask]
        keep = _numpy_nms(class_boxes, class_scores, iou_thresh)
        if len(keep) == 0:
            continue
        kept_boxes = class_boxes[keep]
        kept_scores = class_scores[keep]
        kept_classes = np.full((len(keep), 1), class_id, dtype=np.float32)
        results.append(np.hstack([kept_boxes, kept_scores.reshape(-1, 1), kept_classes]))
        offset += len(keep)
    return results


def _postprocess_raw(raw_output, conf_thresh=0.6, iou_thresh=0.6):
    prediction = raw_output[0]

    if prediction.ndim == 3:
        prediction = prediction[0]
        if prediction.shape[0] < prediction.shape[1]:
            prediction = prediction.T

    if prediction.shape[1] <= 6:
        boxes_xyxy = prediction[:, :4]
        confidences = prediction[:, 4]
        class_ids = prediction[:, 5].astype(np.int32)
    else:
        boxes_cxcywh = prediction[:, :4]
        class_scores = prediction[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(prediction.shape[0]), class_ids]

        x1 = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
        y1 = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
        x2 = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
        y2 = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2
        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

    mask = confidences >= conf_thresh
    if not np.any(mask):
        return []

    boxes_xyxy = boxes_xyxy[mask]
    confidences = confidences[mask]
    class_ids = class_ids[mask]
    return _batched_nms(boxes_xyxy, confidences, class_ids, iou_thresh)


def _scale_detections(detections, orig_img_shape, resized_shape):
    orig_h, orig_w = orig_img_shape
    resized_w, resized_h = resized_shape
    scale_w = orig_w / resized_w
    scale_h = orig_h / resized_h

    results = []
    for detection in detections:
        if len(detection):
            detection = detection.copy()
            detection[:, 0] *= scale_w
            detection[:, 1] *= scale_h
            detection[:, 2] *= scale_w
            detection[:, 3] *= scale_h
            results.append(detection)
    return results


def _rows_to_results(rows, classes, ignore_classes, conf_thresh):
    results = {}
    for row in rows:
        score = float(row[4])
        if score < conf_thresh:
            continue
        x1, y1, x2, y2 = int(row[0]), int(row[1]), int(row[2]), int(row[3])
        class_id = int(row[5])
        if classes is None:
            class_name = str(class_id)
        elif class_id < 0 or class_id >= len(classes):
            continue
        else:
            class_name = classes[class_id]

        if class_id in ignore_classes or class_name in ignore_classes:
            continue
        results.setdefault(class_name, []).append([x1, y1, x2, y2])
    return results


def _flatten_detection_rows(detections):
    if not detections:
        return np.empty((0, 6), dtype=np.float32)
    return np.vstack(detections)


class Detect:
    def __init__(self, model_path, ignore_classes=None, classes=None, input_size=(640, 640)):
        optimal_threads = get_optimal_threads()
        cv2.setNumThreads(optimal_threads)
        self.preferred_device = load_toml_as_dict("cfg/general_config.toml")["cpu_or_gpu"]
        self.model_path = resolve_project_path(model_path)
        self.classes = classes
        self.ignore_classes = set(ignore_classes) if ignore_classes else set()
        self.input_size = input_size
        self._use_io_binding = False
        self._io_binding = None
        self._input_ortvalue = None
        self._device_id = 0
        self._allow_runtime_fallback = True

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        self.model, self.device = self.load_model()
        self.input_name = self.model.get_inputs()[0].name
        self.output_names = [output.name for output in self.model.get_outputs()]
        self._sync_input_dtype_from_model()
        self._setup_inference_backend()

    def _sync_input_dtype_from_model(self):
        self._input_dtype = _session_input_numpy_dtype(self.model)
        self._padded_img_buffer = np.full(
            (1, 3, self.input_size[0], self.input_size[1]),
            128.0 / 255.0,
            dtype=self._input_dtype,
        )
        self._last_resized_w = 0
        self._last_resized_h = 0

    def load_model(self):
        providers = _build_providers(self.preferred_device)
        return self._load_model_with_providers(providers, self.model_path)

    def _load_model_with_providers(self, providers, model_path):
        global _provider_fallback_warning_printed
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        first_provider = _provider_name(providers[0])
        _configure_session_options_for_provider(so, first_provider)
        optimal_threads_amount = get_optimal_threads()
        if first_provider == "CPUExecutionProvider":
            so.intra_op_num_threads = optimal_threads_amount
            so.inter_op_num_threads = max(1, min(2, optimal_threads_amount))
        else:
            so.intra_op_num_threads = 1
            so.inter_op_num_threads = 1
        model = ort.InferenceSession(model_path, sess_options=so, providers=providers)
        actual_provider = model.get_providers()[0]
        if (
                actual_provider == "CPUExecutionProvider"
                and first_provider != "CPUExecutionProvider"
                and not _provider_fallback_warning_printed
        ):
            print(
                f"WARNING: ONNX requested {first_provider}, but the session fell back to CPU. "
                "NVIDIA users run: py -3.11-64 tools\\fix_gpu_runtime.py cuda"
            )
            _provider_fallback_warning_printed = True

        if (
                actual_provider in _GPU_PROVIDERS
                and model_path == self.model_path
                and _fp16_allowed_for_provider(actual_provider)
        ):
            fp16_path = _ensure_fp16_model(model_path)
            if fp16_path and os.path.exists(fp16_path):
                fp32_model = model
                fp32_device = actual_provider
                try:
                    fp16_model, fp16_device = self._load_model_with_providers(providers, fp16_path)
                    probe = _make_inference_probe(
                        fp32_model,
                        fp32_device,
                        self.classes,
                        self.ignore_classes,
                        self.input_size,
                        model_path,
                    )
                    fp16_probe = _make_inference_probe(
                        fp16_model,
                        fp16_device,
                        self.classes,
                        self.ignore_classes,
                        self.input_size,
                        fp16_path,
                    )

                    if _validate_fp16_against_fp32(probe, fp16_probe):
                        print(f"Using FP16 model: {os.path.basename(fp16_path)}")
                        return fp16_model, fp16_device
                    print(f"FP16 model rejected; keeping FP32 for {os.path.basename(model_path)}")
                except Exception as exc:
                    print(f"FP16 session failed to load; keeping FP32: {exc}")

        return model, actual_provider

    def _setup_inference_backend(self):
        self._use_io_binding = False
        self._io_binding = None
        self._input_ortvalue = None
        if self.device not in _GPU_PROVIDERS:
            return
        if self.device == "DmlExecutionProvider":
            return
        try:
            self._io_binding = self.model.io_binding()
            device_type = "cuda" if self.device == "CUDAExecutionProvider" else "dml"
            self._input_ortvalue = ort.OrtValue.ortvalue_from_numpy(
                self._padded_img_buffer,
                device_type,
                self._device_id,
            )
            self._io_binding.bind_ortvalue_input(self.input_name, self._input_ortvalue)
            for output_name in self.output_names:
                self._io_binding.bind_output(output_name, device_type, self._device_id)
            self._use_io_binding = True
        except Exception as exc:
            print(f"IO binding unavailable for {self.device}; using standard run(): {exc}")
            self._use_io_binding = False
            self._io_binding = None
            self._input_ortvalue = None

    def warmup_frame(self, frame, *, label=None):
        """Run one inference pass on a real frame (used for deferred match warmup)."""
        import time

        import runtime_log

        display = label or os.path.basename(self.model_path)
        start = time.perf_counter()
        try:
            self.detect_objects(frame, conf_tresh=0.35)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            runtime_log.log_info(
                "perf",
                f"Inference warmup {display}: {elapsed_ms:.1f}ms ({self.device})",
            )
            return elapsed_ms
        except Exception as exc:
            runtime_log.log_warn("perf", f"Inference warmup {display} failed: {exc}")
            return None

    def _fallback_after_runtime_failure(self, error):
        global _runtime_provider_fallback_warning_printed
        if not getattr(self, "_allow_runtime_fallback", True):
            return False
        if self.device == "CPUExecutionProvider":
            return False

        providers = _fallback_providers_after_runtime_failure(self.device)
        fallback_provider = _provider_name(providers[0])
        if self.device == "CUDAExecutionProvider":
            _cuda_runtime_failed.set()

        if not _runtime_provider_fallback_warning_printed:
            print(
                f"WARNING: ONNX provider {self.device} failed during inference; "
                f"switching to {fallback_provider}. Error: {error}"
            )
            if self.device == "CUDAExecutionProvider":
                print(
                    "CUDA/cuDNN runtime failed. NVIDIA users can repair it with: "
                    "py -3.11-64 tools\\fix_gpu_runtime.py cuda"
                )
            elif self.device == "DmlExecutionProvider":
                print(
                    "DirectML failed. Keep onnx_fp16 = \"no\" on Windows GPU, update drivers, "
                    "or repair with: py -3.11-64 tools\\fix_gpu_runtime.py directml"
                )
            _runtime_provider_fallback_warning_printed = True

        self.model, self.device = self._load_model_with_providers(providers, self.model_path)
        self.input_name = self.model.get_inputs()[0].name
        self.output_names = [output.name for output in self.model.get_outputs()]
        self._sync_input_dtype_from_model()
        self._setup_inference_backend()
        return True

    def _coerce_model_input(self, preprocessed_img):
        expected = _session_input_numpy_dtype(self.model)
        if preprocessed_img.dtype != expected:
            return preprocessed_img.astype(expected, copy=False)
        return preprocessed_img

    def preprocess_image(self, img):
        h, w = img.shape[:2]
        scale = min(self.input_size[0] / h, self.input_size[1] / w)
        new_w = int(w * scale)
        new_h = int(h * scale)

        if new_w != self._last_resized_w or new_h != self._last_resized_h:
            self._padded_img_buffer[:] = 128.0 / 255.0
            self._last_resized_w = new_w
            self._last_resized_h = new_h

        resized_img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        inv_scale = 1.0 / 255.0
        np.multiply(resized_img[:, :, 0], inv_scale, out=self._padded_img_buffer[0, 0, :new_h, :new_w], casting="unsafe")
        np.multiply(resized_img[:, :, 1], inv_scale, out=self._padded_img_buffer[0, 1, :new_h, :new_w], casting="unsafe")
        np.multiply(resized_img[:, :, 2], inv_scale, out=self._padded_img_buffer[0, 2, :new_h, :new_w], casting="unsafe")
        return self._padded_img_buffer, new_w, new_h

    def postprocess(self, raw_output, orig_img_shape, resized_shape, conf_tresh=0.6):
        detections = _postprocess_raw(raw_output, conf_thresh=conf_tresh, iou_thresh=0.6)
        return _scale_detections(detections, orig_img_shape, resized_shape)

    def _run_model(self, preprocessed_img, *, _retried_cuda_poison=False):
        if (
            not _retried_cuda_poison
            and self.device == "CUDAExecutionProvider"
            and _cuda_runtime_failed.is_set()
        ):
            if self._fallback_after_runtime_failure("CUDA runtime previously failed"):
                return self._run_model(preprocessed_img, _retried_cuda_poison=True)

        model_input = self._coerce_model_input(preprocessed_img)

        def _execute():
            if self._use_io_binding and self._io_binding is not None and self._input_ortvalue is not None:
                self._input_ortvalue.update_inplace(model_input)
                self.model.run_with_iobinding(self._io_binding)
                return self._io_binding.copy_outputs_to_cpu()
            return self.model.run(self.output_names, {self.input_name: model_input})

        if self.device in _GPU_PROVIDERS:
            with _gpu_inference_lock:
                return _execute()
        return _execute()

    def _infer_outputs(self, img):
        preprocessed_img, _, _ = self.preprocess_image(img)
        try:
            return self._run_model(preprocessed_img)
        except Exception as error:
            if not self._fallback_after_runtime_failure(error):
                raise
            return self._run_model(preprocessed_img)

    def _infer_rows(self, img, conf_tresh):
        orig_h, orig_w = img.shape[:2]
        preprocessed_img, resized_w, resized_h = self.preprocess_image(img)
        try:
            outputs = self._run_model(preprocessed_img)
        except Exception as error:
            if not self._fallback_after_runtime_failure(error):
                raise
            outputs = self._run_model(preprocessed_img)
        detections = self.postprocess(outputs, (orig_h, orig_w), (resized_w, resized_h), conf_tresh)
        return _flatten_detection_rows(detections)

    def detect_objects(self, img, conf_tresh=0.6):
        rows = self._infer_rows(img, conf_tresh)
        return _rows_to_results(rows, self.classes, self.ignore_classes, conf_tresh)

    def detect_objects_dual(self, img, primary_conf, retry_conf):
        low_conf = min(float(primary_conf), float(retry_conf))
        rows = self._infer_rows(img, low_conf)
        primary = _rows_to_results(rows, self.classes, self.ignore_classes, float(primary_conf))
        retry = _rows_to_results(rows, self.classes, self.ignore_classes, float(retry_conf))
        return primary, retry

    def count_objects(self, results):
        return sum(len(boxes or []) for boxes in (results or {}).values())
