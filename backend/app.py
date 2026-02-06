from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import shutil
import os
from video_processor import analyze_video

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
        <head><title>Boxing AI Upload</title></head>
        <body>
            <h2>Upload a boxing match video</h2>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="file" accept="video/*" />
                <button type="submit">Upload</button>
            </form>
            <p>Tip: You can also use the API docs at <code>/docs</code>.</p>
        </body>
    </html>
    """

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    stats = analyze_video(file_path, show_preview=False)

    return {
        "filename": file.filename,
        "video_stats": stats
    }
