"""Serve the production frontend and scientific API locally; no cloud deployment."""

from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from app.main import app

dist = Path(__file__).resolve().parents[2] / "frontend/dist"
if not (dist / "index.html").is_file():
    raise RuntimeError("Build frontend first with VITE_API_BASE_URL=/")
app.mount("/", StaticFiles(directory=dist, html=True), name="judge-preview")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8027)
