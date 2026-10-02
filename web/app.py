"""
Task 5 - Web app + job queue (ctrl_freak pipeline)

Serves the UI and a small JSON API. Jobs run in a background worker thread
sequentially (FFmpeg rendering is CPU-bound; one worker keeps it predictable).

  GET  /                 -> web/index.html (topic input, live progress, player)
  POST /api/jobs         -> {"topic": "..."} -> {"id", "stages", ...}
  GET  /api/jobs/{id}    -> job state (queued/running/done/failed + stages)
  /videos/*              -> static output (final.mp4 playback + download)

Run from the project root:
  python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
"""

import json
import queue
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import composer, script_engine, visual_engine, voice_engine  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "output"
VIDEOS_DIR = OUTPUT_ROOT / "videos"
JOBS_DIR = OUTPUT_ROOT / "jobs"
STAGES = ("script", "visuals", "voice", "compose")

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ctrl_freak")
JOBS = {}
Q = queue.Queue()


class JobCreate(BaseModel):
    topic: str
    language: str = "English"


def persist(job: dict) -> None:
    (JOBS_DIR / f"{job['id']}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def set_stage(job: dict, name: str, state: str) -> None:
    job["stages"][name] = state
    persist(job)


def run_job(job: dict) -> None:
    topic = job["topic"]
    try:
        language = job.get("language", "English")
        set_stage(job, "script", "running")
        script_engine.generate(topic, language=language)
        slug = script_engine.output_slug(topic, language)
        script_path = OUTPUT_ROOT / "scripts" / f"{slug}.json"
        set_stage(job, "script", "done")

        set_stage(job, "visuals", "running")
        visual_engine.generate_images(script_path)
        set_stage(job, "visuals", "done")

        set_stage(job, "voice", "running")
        voice_engine.voice_script(script_path)
        set_stage(job, "voice", "done")

        set_stage(job, "compose", "running")
        composer.compose(slug)
        set_stage(job, "compose", "done")

        job["status"] = "done"
        job["video_url"] = f"/videos/{slug}/final.mp4"
        persist(job)
    except BaseException as e:  # SystemExit from engine config must not kill the worker
        for name, state in job["stages"].items():
            if state == "running":
                job["stages"][name] = "failed"
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        persist(job)


def worker() -> None:
    while True:
        job_id = Q.get()
        job = JOBS.get(job_id)
        if job and job["status"] == "queued":
            job["status"] = "running"
            persist(job)
            run_job(job)
        Q.task_done()


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/jobs")
def create_job(body: JobCreate):
    topic = body.topic.strip()
    if not topic:
        raise HTTPException(400, "topic is empty")
    if len(topic) > 200:
        raise HTTPException(400, "topic too long (max 200 chars)")
    language = body.language.strip().capitalize()
    if language not in ("English", "Hindi"):
        raise HTTPException(400, "language must be English or Hindi")
    job = {
        "id": uuid.uuid4().hex[:12],
        "topic": topic,
        "language": language,
        "status": "queued",
        "stages": {s: "pending" for s in STAGES},
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    JOBS[job["id"]] = job
    persist(job)
    Q.put(job["id"])
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")
