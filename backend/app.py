from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
import shutil
import os
import csv
import io
from fastapi.responses import StreamingResponse
from video_processor import analyze_video, DEFAULT_SETTINGS, PRESET_OVERRIDES

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
        <head><title>Boxing AI Upload</title></head>
        <body>
            <h2>Upload a boxing match video</h2>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="video/*" />
                <p>
                    Preset:
                    <select name="preset">
                        <option value="balanced" selected>balanced</option>
                        <option value="conservative">conservative</option>
                        <option value="aggressive">aggressive</option>
                    </select>
                </p>
                <p><label>Min confidence: <input type="number" step="0.01" min="0" max="1" name="min_confidence" value="0.35" /></label></p>
                <p><label>Min visibility: <input type="number" step="0.01" min="0" max="1" name="min_visibility" value="0.5" /></label></p>
                <p><label>Speed threshold: <input type="number" step="0.001" min="0" name="speed_threshold" value="0.022" /></label></p>
                <p><label>Extension threshold: <input type="number" step="0.001" min="0" name="extension_threshold" value="0.006" /></label></p>
                <p><label>Elbow angle threshold: <input type="number" step="1" min="60" max="180" name="elbow_angle_threshold" value="120" /></label></p>
                <p><label>Cooldown (sec): <input type="number" step="0.01" min="0" name="cooldown_sec" value="0.15" /></label></p>
                <p><label>Combo gap (sec): <input type="number" step="0.01" min="0" name="combo_gap_sec" value="0.8" /></label></p>
                <p><label>Timeline bucket (sec): <input type="number" step="1" min="1" name="timeline_bucket_sec" value="10" /></label></p>
                <button type="submit">Upload</button>
            </form>
            <p>Tip: You can also use the API docs at <code>/docs</code>.</p>
            <p>Presets and defaults: <code>/settings-presets</code></p>
        </body>
    </html>
    """


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
