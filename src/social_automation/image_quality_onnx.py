"""Valutazione qualità immagine (sfocatura / distorsione) tramite modello ONNX locale."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from social_automation.settings import Settings, repo_root

_LOG = logging.getLogger(__name__)

_INPUT_SIZE = 512
_GOOD_INDEX = 1


@dataclass(frozen=True)
class ImageQualityEvalResult:
    """Output inferenza qualità (softmax su logits ONNX)."""

    is_valid_by_quality_evaluation: int
    """1 se P(good) ≥ soglia impostata, altrimenti 0."""

    predicted_class: str
    """Etichetta classe con probabilità massima (argmax)."""

    predicted_confidence: float
    """Probabilità della classe predetta (``P(argmax)``)."""


def _strip_env_quotes(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1].strip()
    return s


def _resolve_artifact_path(raw: str) -> Path | None:
    """Path assoluto a file modello / JSON; relativi: prima root repo, poi cwd."""
    s = _strip_env_quotes(raw)
    if not s:
        return None
    p = Path(s).expanduser()
    if p.is_absolute():
        return p.resolve() if p.is_file() else None
    alt = repo_root() / p
    if alt.is_file():
        return alt.resolve()
    if p.is_file():
        return p.resolve()
    return None


def quality_gate_configured(settings: Settings) -> bool:
    """True se ONNX + class_names sono configurati e leggibili (e onnxruntime importabile)."""
    try:
        import onnxruntime as ort  # noqa: F401
    except ImportError:
        return False
    onnx_p = _resolve_artifact_path(str(settings.image_quality_onnx_path or ""))
    cls_p = _resolve_artifact_path(str(settings.image_quality_class_names_path or ""))
    return onnx_p is not None and cls_p is not None


@lru_cache(maxsize=4)
def _load_class_names(path_str: str) -> tuple[str, ...]:
    data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("class_names.json deve essere una lista con almeno 2 classi")
    names = tuple(str(x).strip().lower() for x in data)
    if names[0] != "bad" or names[1] != "good":
        _LOG.warning(
            "Ordine classi inatteso in class_names.json: %s (atteso bad, good)", names
        )
    return names


@lru_cache(maxsize=2)
def _inference_session(model_path_str: str) -> Any:
    import onnxruntime as ort

    return ort.InferenceSession(model_path_str, providers=["CPUExecutionProvider"])


def _preprocess_rgb(path: Path) -> np.ndarray:
    im = Image.open(path).convert("RGB")
    im = im.resize((_INPUT_SIZE, _INPUT_SIZE), Image.Resampling.LANCZOS)
    arr = np.asarray(im, dtype=np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


def evaluate_image_quality(
    image_path: Path, settings: Settings
) -> ImageQualityEvalResult | None:
    """
    Esegue inferenza sul file immagine.

    ``is_valid_by_quality_evaluation`` è 1 se P(good) ≥ soglia, altrimenti 0.
    ``predicted_class`` / ``predicted_confidence`` derivano dall'argmax sulla softmax.
    ``None`` se la valutazione non è configurata o non è applicabile.
    """
    if not quality_gate_configured(settings):
        return None
    onnx_p = _resolve_artifact_path(str(settings.image_quality_onnx_path or ""))
    cls_p = _resolve_artifact_path(str(settings.image_quality_class_names_path or ""))
    if onnx_p is None or cls_p is None:
        return None
    if not image_path.is_file():
        _LOG.warning("Immagine assente per quality eval: %s", image_path)
        return None

    class_names = _load_class_names(str(cls_p))
    sess = _inference_session(str(onnx_p))
    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]
    batch = _preprocess_rgb(image_path)
    logits = sess.run([out.name], {inp.name: batch})[0]
    row = np.asarray(logits[0], dtype=np.float64)
    ex = np.exp(row - np.max(row))
    probs = ex / np.sum(ex)
    thr = float(settings.image_quality_confidence_threshold)
    try:
        good_idx = class_names.index("good")
    except ValueError:
        good_idx = min(_GOOD_INDEX, len(class_names) - 1)
    p_good = float(probs[good_idx])
    pred_i = int(np.argmax(probs))
    pred_label = class_names[pred_i] if pred_i < len(class_names) else str(pred_i)
    p_pred = float(probs[pred_i])
    valid = 1 if p_good >= thr else 0
    return ImageQualityEvalResult(
        is_valid_by_quality_evaluation=valid,
        predicted_class=pred_label,
        predicted_confidence=p_pred,
    )


def evaluate_image_file(image_path: Path, settings: Settings) -> int | None:
    """Compat: restituisce solo ``is_valid_by_quality_evaluation`` (0/1) o ``None``."""
    r = evaluate_image_quality(image_path, settings)
    return None if r is None else int(r.is_valid_by_quality_evaluation)
