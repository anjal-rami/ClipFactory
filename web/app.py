"""
Task 5 - Web app + job queue (ClipFactory pipeline)

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
import re
import sys
import threading
import time
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

app = FastAPI(title="ClipFactory")
JOBS = {}
Q = queue.Queue()


class JobCreate(BaseModel):
    topic: str
    language: str = "English"


class JobBatch(BaseModel):
    topics: list[str]
    language: str = "English"


def _norm_topic(raw: str) -> str:
    topic = raw.strip()
    if not topic:
        raise HTTPException(400, "topic is empty")
    if len(topic) > 200:
        raise HTTPException(400, "topic too long (max 200 chars)")
    return topic


def _norm_language(raw: str) -> str:
    language = (raw or "English").strip().capitalize()
    if language not in ("English", "Hindi"):
        raise HTTPException(400, "language must be English or Hindi")
    return language


def _new_job(topic: str, language: str) -> dict:
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


def persist(job: dict) -> None:
    (JOBS_DIR / f"{job['id']}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def set_stage(job: dict, name: str, state: str) -> None:
    job["stages"][name] = state
    persist(job)


def run_job(job: dict) -> None:
    topic = job["topic"]
    started = time.time()
    try:
        language = job.get("language", "English")
        set_stage(job, "script", "running")
        script_engine.generate(topic, language=language)
        slug = script_engine.output_slug(topic, language)
        script_path = OUTPUT_ROOT / "scripts" / f"{slug}.json"
        set_stage(job, "script", "done")

        set_stage(job, "visuals", "running")
        visual_engine.generate_images(script_path)
        vis_manifest = OUTPUT_ROOT / "videos" / slug / "visual_manifest.json"
        if vis_manifest.is_file():
            vis_data = json.loads(vis_manifest.read_text(encoding="utf-8"))
            bad = [str(s.get("scene")) for s in vis_data.get("scenes", []) if s.get("status") != "ok"]
            if bad:
                job.setdefault("warnings", []).append("scene(s) " + ", ".join(bad) + " used fallback imagery")
        set_stage(job, "visuals", "done")

        set_stage(job, "voice", "running")
        voice_engine.voice_script(script_path)
        set_stage(job, "voice", "done")

        set_stage(job, "compose", "running")
        composer.compose(slug)
        set_stage(job, "compose", "done")

        job["status"] = "done"
        job["video_url"] = f"/videos/{slug}/final.mp4"
        job["render_seconds"] = round(time.time() - started, 1)
        job["finished_at"] = datetime.now().isoformat(timespec="seconds")
        persist(job)
    except BaseException as e:  # SystemExit from engine config must not kill the worker
        for name, state in job["stages"].items():
            if state == "running":
                job["stages"][name] = "failed"
        job["status"] = "failed"
        job["render_seconds"] = round(time.time() - started, 1)
        job["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        persist(job)


@app.get("/api/metrics")
def metrics():
    jobs = list(JOBS.values())
    done = [j for j in jobs if j.get("status") == "done"]
    failed = [j for j in jobs if j.get("status") == "failed"]
    active = [j for j in jobs if j.get("status") in ("queued", "running")]
    renders = [j["render_seconds"] for j in done if j.get("render_seconds")]
    languages = {}
    for j in jobs:
        lang = j.get("language", "English")
        languages[lang] = languages.get(lang, 0) + 1
    return {
        "jobs_total": len(jobs),
        "videos_done": len(done),
        "jobs_failed": len(failed),
        "jobs_active": len(active),
        "avg_render_seconds": round(sum(renders) / len(renders), 1) if renders else None,
        "languages": languages,
        "infra_cost_per_video_inr": 0,  # the entire stack runs on free tiers
    }


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
    # Reload persisted jobs so the dashboard survives restarts; anything that
    # was mid-flight when the server died is marked failed (honest state).
    for f in JOBS_DIR.glob("*.json"):
        try:
            job = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if job.get("status") in ("queued", "running"):
            job["status"] = "failed"
            job["error"] = "server restarted before this job finished"
            persist(job)
        JOBS[job["id"]] = job
    threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.post("/api/jobs")
def create_job(body: JobCreate):
    return _new_job(_norm_topic(body.topic), _norm_language(body.language))


@app.post("/api/jobs/batch")
def create_batch(body: JobBatch):
    if len(body.topics) > 10:
        raise HTTPException(400, "max 10 topics per batch")
    language = _norm_language(body.language)
    return {"jobs": [_new_job(_norm_topic(t), language) for t in body.topics]}


@app.get("/api/jobs")
def list_jobs():
    jobs = sorted(JOBS.values(), key=lambda j: j.get("created_at", ""), reverse=True)
    return {"jobs": jobs}


@app.get("/jobs")
def jobs_page():
    return FileResponse(WEB_DIR / "jobs.html")


@app.get("/publish/{slug}")
def publish_page(slug: str):
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise HTTPException(400, "invalid slug")
    return FileResponse(WEB_DIR / "publish.html")


@app.get("/api/publish/{slug}")
def publish_pack(slug: str):
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise HTTPException(400, "invalid slug")
    path = OUTPUT_ROOT / "scripts" / f"{slug}.json"
    if not path.is_file():
        raise HTTPException(404, "no script for this slug")
    script = json.loads(path.read_text(encoding="utf-8"))
    caption = "\n".join(p for p in (script.get("hook", ""), script.get("cta", "")) if p)
    if not caption:
        caption = script.get("topic", slug)
    tags = " ".join(script.get("hashtags", []))
    return {
        "slug": slug,
        "topic": script.get("topic", slug),
        "language": script.get("language", "English"),
        "video_url": f"/videos/{slug}/final.mp4",
        "caption": caption,
        "hashtags": tags,
        "full_post": f"{caption}\n\n{tags}".strip(),
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    return job


app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")
