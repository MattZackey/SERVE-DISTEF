import json
import sys
import numpy as np
import onnxruntime as ort
from utils import loadvideo
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def _onnx_providers():
    available = set(ort.get_available_providers())
    preferred = ["CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider"]
    return [p for p in preferred if p in available] or ["CPUExecutionProvider"]


def load_onnx_session(onnx_path):
    session = ort.InferenceSession(onnx_path, providers=_onnx_providers())
    return session


def preprocess(video_path, num_frames, period):
    
    video = loadvideo(video_path)  # (C, F, H, W)
    
    total_frames = video.shape[1]
    max_idx = min(total_frames + 1, num_frames * 2)
    
    idx = list(range(0, max_idx, period))
    video_clip = video[:,idx] 
    video_clip = np.expand_dims(video_clip, axis=0)
    
    return video_clip


def predict_ef(video_path, ef_session, ef_input, ef_output, qr_session, qr_input, qr_output, num_frames, period):
    """Predict EF and Quantiles"""
    
    x = preprocess(video_path, num_frames, period)
    logger.debug(f"Model input shape: {x.shape}")

    ef_pred = ef_session.run([ef_output], {ef_input: x})[0]
    ef = float(np.asarray(ef_pred).reshape(-1)[0])

    qr_pred = qr_session.run([qr_output], {qr_input: x})[0]
    quantiles = [float(v) for v in np.asarray(qr_pred).reshape(-1)]

    return {"point_estimate": ef, "quantiles": quantiles}
