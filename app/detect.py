import os
import platform
import time
import warnings

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
    if failed_provider != "DmlExecutionProvider" and "DmlExecutionProvider" in available_providers:
        providers.append(_directml_provider())
    providers.append("CPUExecutionProvider")
    return providers


def _configure_session_options_for_provider(session_options, provider_name):
    if provider_name == "DmlExecutionProvider":
        # ONNX Runtime documents these as required for DirectML sessions.
        # Without them some Windows/NVIDIA/AMD setups can initialize but run
        # extremely slowly or fall back unpredictably.
        session_options.enable_mem_pattern = False
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL


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

    results = []
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

    return results


class Detect:
    def __init__(self, model_path, ignore_classes=None, classes=None, input_size=(640, 640), model_tag="model"):
        self.model_tag = str(model_tag or "model")
        self.preferred_device = load_toml_as_dict("cfg/general_config.toml")["cpu_or_gpu"]
        self.requested_provider = ""
        self.model_path = resolve_project_path(model_path)
        self.classes = classes
        self.ignore_classes = set(ignore_classes) if ignore_classes else set()
        self.input_size = input_size

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        self.model, self.device = self.load_model()
        if self.device != "CPUExecutionProvider":
            cv2.setNumThreads(1)
        else:
            cv2.setNumThreads(get_optimal_threads())
        self.input_name = self.model.get_inputs()[0].name
        self.output_names = [output.name for output in self.model.get_outputs()]
        self._padded_img_buffer = np.full(
            (1, 3, self.input_size[0], self.input_size[1]),
            128.0 / 255.0,
            dtype=np.float32,
        )
        self._last_resized_w = 0
        self._last_resized_h = 0

    def load_model(self):
        global _provider_fallback_warning_printed
        providers = _build_providers(self.preferred_device)
        self.requested_provider = _provider_name(providers[0])
        return self._load_model_with_providers(providers)

    def get_provider_info(self):
        return {
            "requested": self.requested_provider or self.device,
            "actual": self.device,
            "model_path": self.model_path,
            "model_tag": self.model_tag,
        }

    def _record_init_fallback(self, requested_provider, actual_provider):
        try:
            from inference_health import record_provider_fallback

            record_provider_fallback(
                self.model_tag,
                requested_provider,
                actual_provider,
                error="session initialized on fallback provider",
            )
        except Exception:
            pass

    def _load_model_with_providers(self, providers):
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
        model = ort.InferenceSession(self.model_path, sess_options=so, providers=providers)
        actual_provider = model.get_providers()[0]
        if actual_provider == "CPUExecutionProvider" and first_provider != "CPUExecutionProvider":
            self._record_init_fallback(first_provider, actual_provider)
        if (
                actual_provider == "CPUExecutionProvider"
                and first_provider != "CPUExecutionProvider"
                and not _provider_fallback_warning_printed
        ):
            detail = ""
            if first_provider == "CUDAExecutionProvider":
                try:
                    from gpu_runtime_install import verify_cuda_dlls

                    ok, missing = verify_cuda_dlls()
                    if not ok:
                        detail = f" Missing CUDA DLLs: {', '.join(missing)}."
                except Exception:
                    pass
            fix_hint = gpu_help_message("session_cpu_fallback", vendor=primary_vendor())
            print(
                f"WARNING: ONNX requested {first_provider}, but the session fell back to CPU.{detail} {fix_hint}".strip()
            )
            _provider_fallback_warning_printed = True
        return model, actual_provider

    def _fallback_after_runtime_failure(self, error):
        global _runtime_provider_fallback_warning_printed
        if self.device == "CPUExecutionProvider":
            return False

        previous_provider = self.device
        providers = _fallback_providers_after_runtime_failure(self.device)
        fallback_provider = _provider_name(providers[0])
        try:
            from inference_health import record_provider_fallback

            record_provider_fallback(self.model_tag, previous_provider, fallback_provider, error=str(error))
        except Exception:
            pass
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
            _runtime_provider_fallback_warning_printed = True

        self.model, self.device = self._load_model_with_providers(providers)
        self.input_name = self.model.get_inputs()[0].name
        self.output_names = [output.name for output in self.model.get_outputs()]
        if self.device != "CPUExecutionProvider":
            cv2.setNumThreads(1)
        else:
            cv2.setNumThreads(get_optimal_threads())
        return True

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
        img_float = resized_img.astype(np.float32, copy=True)
        np.multiply(img_float, 1.0 / 255.0, out=img_float)

        self._padded_img_buffer[0, 0, :new_h, :new_w] = img_float[:, :, 0]
        self._padded_img_buffer[0, 1, :new_h, :new_w] = img_float[:, :, 1]
        self._padded_img_buffer[0, 2, :new_h, :new_w] = img_float[:, :, 2]

        return self._padded_img_buffer, new_w, new_h

    def postprocess(self, raw_output, orig_img_shape, resized_shape, conf_tresh=0.6):
        detections = _postprocess_raw(raw_output, conf_thresh=conf_tresh, iou_thresh=0.6)

        orig_h, orig_w = orig_img_shape
        resized_w, resized_h = resized_shape
        scale_w = orig_w / resized_w
        scale_h = orig_h / resized_h

        results = []
        for detection in detections:
            if len(detection):
                detection[:, 0] *= scale_w
                detection[:, 1] *= scale_h
                detection[:, 2] *= scale_w
                detection[:, 3] *= scale_h
                results.append(detection)
        return results

    def detect_objects(self, img, conf_tresh=0.6):
        try:
            from perf_profiler import get_profiler

            profiler = get_profiler()
        except Exception:
            profiler = None

        orig_h, orig_w = img.shape[:2]
        preprocess_started = time.perf_counter() if profiler and profiler.enabled else None
        preprocessed_img, resized_w, resized_h = self.preprocess_image(img)
        if preprocess_started is not None:
            profiler.record(f"onnx_preprocess:{self.model_tag}", (time.perf_counter() - preprocess_started) * 1000.0)

        infer_started = time.perf_counter() if profiler and profiler.enabled else None
        try:
            outputs = self.model.run(self.output_names, {self.input_name: preprocessed_img})
        except Exception as e:
            if not self._fallback_after_runtime_failure(e):
                raise
            outputs = self.model.run(self.output_names, {self.input_name: preprocessed_img})
        if infer_started is not None:
            profiler.record(f"onnx_inference:{self.model_tag}", (time.perf_counter() - infer_started) * 1000.0)

        post_started = time.perf_counter() if profiler and profiler.enabled else None
        detections = self.postprocess(outputs, (orig_h, orig_w), (resized_w, resized_h), conf_tresh)
        if post_started is not None:
            profiler.record(f"onnx_postprocess:{self.model_tag}", (time.perf_counter() - post_started) * 1000.0)

        if profiler and profiler.enabled and self.device == "CPUExecutionProvider":
            profiler.mark_counter("onnx_cpu_frames")

        results = {}
        for detection in detections:
            for row in detection:
                x1, y1, x2, y2 = int(row[0]), int(row[1]), int(row[2]), int(row[3])
                class_id = int(row[5])
                if self.classes is None:
                    class_name = str(class_id)
                elif class_id < 0 or class_id >= len(self.classes):
                    continue
                else:
                    class_name = self.classes[class_id]

                if class_id in self.ignore_classes or class_name in self.ignore_classes:
                    continue
                results.setdefault(class_name, []).append([x1, y1, x2, y2])

        return results
