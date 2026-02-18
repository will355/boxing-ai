from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
import shutil
import os
import csv
import io
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from video_processor import analyze_video, DEFAULT_SETTINGS, PRESET_OVERRIDES

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


def _settings_from_form(
    preset,
    min_visibility,
    speed_threshold,
    extension_threshold,
    elbow_angle_threshold,
    cooldown_sec,
    combo_gap_sec,
    timeline_bucket_sec,
    min_confidence,
):
    return {
        "preset": preset,
        "min_visibility": min_visibility,
        "speed_threshold": speed_threshold,
        "extension_threshold": extension_threshold,
        "elbow_angle_threshold": elbow_angle_threshold,
        "cooldown_sec": cooldown_sec,
        "combo_gap_sec": combo_gap_sec,
        "timeline_bucket_sec": timeline_bucket_sec,
        "min_confidence": min_confidence,
    }


def _events_to_csv(events):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "frame",
            "time_sec",
            "hand",
            "type",
            "confidence",
            "counted",
            "speed",
            "distance_growth",
            "elbow_angle",
        ]
    )
    for e in events:
        debug = e.get("debug", {})
        writer.writerow(
            [
                e.get("frame"),
                e.get("time_sec"),
                e.get("hand"),
                e.get("type"),
                e.get("confidence"),
                e.get("counted"),
                debug.get("speed"),
                debug.get("distance_growth"),
                debug.get("elbow_angle"),
            ]
        )
    output.seek(0)
    return output


def _safe_filename(name):
    cleaned = os.path.basename(name or "")
    return cleaned or "upload.mp4"


@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/settings-presets")
def settings_presets():
    return {
        "default_settings": DEFAULT_SETTINGS,
        "preset_overrides": PRESET_OVERRIDES,
    }


@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    min_visibility: float = Form(0.5),
    speed_threshold: float = Form(0.022),
    extension_threshold: float = Form(0.006),
    elbow_angle_threshold: float = Form(120.0),
    cooldown_sec: float = Form(0.15),
    combo_gap_sec: float = Form(0.8),
    timeline_bucket_sec: int = Form(10),
    min_confidence: float = Form(0.35),
):
    safe_name = _safe_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    settings = _settings_from_form(
        preset,
        min_visibility,
        speed_threshold,
        extension_threshold,
        elbow_angle_threshold,
        cooldown_sec,
        combo_gap_sec,
        timeline_bucket_sec,
        min_confidence,
    )
    stats = analyze_video(file_path, show_preview=False, settings=settings)

    return {
        "filename": safe_name,
        "video_stats": stats
    }


@app.post("/upload-csv")
async def upload_video_csv(
    file: UploadFile = File(...),
    preset: str = Form("balanced"),
    min_visibility: float = Form(0.5),
    speed_threshold: float = Form(0.022),
    extension_threshold: float = Form(0.006),
    elbow_angle_threshold: float = Form(120.0),
    cooldown_sec: float = Form(0.15),
    combo_gap_sec: float = Form(0.8),
    timeline_bucket_sec: int = Form(10),
    min_confidence: float = Form(0.35),
):
    safe_name = _safe_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    settings = _settings_from_form(
        preset,
        min_visibility,
        speed_threshold,
        extension_threshold,
        elbow_angle_threshold,
        cooldown_sec,
        combo_gap_sec,
        timeline_bucket_sec,
        min_confidence,
    )
    stats = analyze_video(file_path, show_preview=False, settings=settings)
    csv_buffer = _events_to_csv(stats.get("punch_events", []))
    headers = {
        "Content-Disposition": f'attachment; filename="{os.path.splitext(safe_name)[0]}_events.csv"'
    }
    return StreamingResponse(csv_buffer, media_type="text/csv", headers=headers)
