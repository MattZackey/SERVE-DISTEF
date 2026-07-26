import os
import tempfile
import configparser
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from model import load_onnx_session, predict_ef

MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/ml/model")
if not os.path.isdir(MODEL_DIR):
    MODEL_DIR = "models"

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(os.path.dirname(__file__), "config.ini"))
model_cfg = _cfg["model"]


EF_MODEL_PATH = os.path.join(MODEL_DIR, model_cfg["ef_model_filename"])
QR_MODEL_PATH = os.path.join(MODEL_DIR, model_cfg["qr_model_filename"])

BATCH_SIZE = model_cfg.getint("batch_size")
NUM_FRAMES = model_cfg.getint("num_frames")
PERIOD = model_cfg.getint("period")
TARGET_IMAGE_SIZE = model_cfg.getint("target_image_size")

state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    state["ef_session"]  = load_onnx_session(EF_MODEL_PATH)
    state["qr_session"] = load_onnx_session(QR_MODEL_PATH)
    yield
    state.clear()


app = FastAPI(title="Echo CONDFID-EF Prediction (SageMaker)", lifespan=lifespan)


def _run_inference(raw_bytes: bytes, suffix: str = ".avi") -> float:
    """Write the incoming video bytes to a temp file and run EF prediction."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        return predict_ef(
            video_path = tmp_path,
            ef_session = state["ef_session"],
            ef_input = state["ef_session"].get_inputs()[0].name,
            ef_output = state["ef_session"].get_outputs()[0].name,
            qr_session = state["qr_session"],
            qr_input = state["qr_session"].get_inputs()[0].name,
            qr_output = state["qr_session"].get_outputs()[0].name,
            num_frames = NUM_FRAMES, 
            period = PERIOD
        )
        
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/ping")
def ping():
    if "ef_session" not in state:
        raise HTTPException(status_code=503, detail="ef model not loaded")
    if "qr_session" not in state:
        raise HTTPException(status_code=503, detail="qr model not loaded")
    return {"status": "ok"}


@app.post("/invocations")
async def invocations(request: Request):
    
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty request body")
    suffix = "." + os.environ.get("VIDEO_EXT", "avi").lstrip(".")
    try:
        ef = _run_inference(body, suffix=suffix)
        return {"ejection_fraction": ef}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))

