# boxing-ai

Computer-vision backend for boxing footage analysis using FastAPI + MediaPipe pose landmarks.

## Current Features

- Video upload + analysis API (`/upload`)
- CSV event export (`/upload-csv`)
- Health endpoint (`/health`)
- Preset and settings discovery endpoint (`/settings-presets`)
- Per-punch event timeline with:
  - hand (`left` / `right`)
  - type (`straight` / `hook`)
  - confidence score (`0..1`)
  - raw debug metrics (speed, extension, elbow angle)
- Aggregated analytics:
  - punches per minute
  - combo count and max combo
  - timeline bucket counts
- Runtime tuning settings on every upload:
  - presets: `conservative`, `balanced`, `aggressive`
  - confidence thresholding and detector thresholds

## Quick Start (Windows / PowerShell)

1. Create and activate a virtual environment:
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies:
```powershell
pip install -r requirements.txt
```

3. Run API:
```powershell
uvicorn app:app --reload
```

4. Open:
- Interactive docs: `http://127.0.0.1:8000/docs`
- Upload form: `http://127.0.0.1:8000/`

## API Overview

- `GET /health`
  - Liveness check
- `GET /settings-presets`
  - Returns default settings and preset overrides
- `POST /upload`
  - Returns JSON with full `video_stats`
- `POST /upload-csv`
  - Returns downloadable punch-events CSV

## Output Fields (`video_stats`)

- `frames`, `fps`, `frames_with_pose`, `pose_coverage`
- `detected_punches_raw`, `counted_punches`, `punch_attempts`
- `punches_by_hand`, `punches_by_type`
- `punch_events` (all detected, each includes `counted`)
- `counted_events` (events that passed `min_confidence`)
- `analytics`
- `settings_used`

## Notes

- `punch_attempts` is currently equal to `counted_punches` for compatibility.
- This version uses heuristic punch classification and does not yet detect landed vs. missed.
