# ctrl_freak — AI Video Pipeline for the Qoneqt Global Feed

**Qoneqt × CTRL FREAK Challenge entry.** An LLM-powered content pipeline that turns
any topic, prompt, idea, or trend into a publish-ready vertical video for the
Qoneqt Global Feed — repeatably, at scale.

**🔴 Live demo:** https://ctrl-freak-i4bs.onrender.com *(free tier — sleeps when idle, first request wakes it in ~1 min)*

## Pipeline

```
Topic ──► Script Engine (LLM) ──► Visuals (image gen) ──► Voiceover (TTS)
                                                                │
   Publish on Qoneqt ◄── Deployed web UI ◄── 9:16 MP4 ◄── FFmpeg composition
```

## Build order (one task at a time)

| # | Task | Status |
|---|------|--------|
| 1 | Script & Story Engine — topic → structured JSON (hook, scenes, image prompts) | ✅ done |
| 2 | Visual generation — image prompts → 720×1280 scene images (NVIDIA FLUX) | ✅ done |
| 3 | Voiceover — narration text → TTS audio per scene (edge-tts, rate-fitted) | ✅ done |
| 4 | Composition — Ken Burns + captions + voiceover → 9:16 MP4 (FFmpeg) | ✅ done |
| 5 | Web UI + job queue — topic input, live status, video preview | ✅ done (backend verified: job → final.mp4 in 180s; UI served at `/`) |
| 6 | Deployment — frontend on Vercel, worker on Render | pending |
| 7 | Ship — GitHub repo, demo video, publish one video on Qoneqt Global Feed | pending |

## Structure

```
ctrl_freak/
├── pipeline/
│   ├── llm.py             # provider-agnostic LLM client (NVIDIA/Z.AI/OpenAI/Gemini)
│   ├── script_engine.py   # Task 1: topic → script JSON
│   ├── visual_engine.py   # Task 2: script JSON → 720×1280 scene PNGs
│   ├── voice_engine.py    # Task 3: narration → TTS audio (edge-tts, rate-fitted)
│   └── composer.py        # Task 4: Ken Burns + captions + voice → final.mp4
├── web/
│   ├── app.py             # Task 5: FastAPI server + job queue + worker (untested)
│   └── index.html         # Task 5: UI — topic form, live stage status, video player
├── output/
│   ├── scripts/           # generated script JSONs land here
│   └── videos/<slug>/     # scene-<n>.png + audio/scene-<n>.mp3 + clip-<n>.mp4 + final.mp4
├── tools/                 # portable FFmpeg (gitignored)
├── .env                   # API keys (gitignored — never commit)
└── README.md
```

## Known limitations

- **No auth on the API** — anyone with a job ID can view that job's status, and
  generated videos are publicly served. Fine for this demo; add authentication
  before real use (flagged as inconclusive by the Mimosa deep security scan).
- **Free-tier hosting** — the service sleeps after ~15 min idle (first request
  wakes it in ~1 min) and `output/` is ephemeral: videos regenerate per job.

## Setup

```bash
python -m pip install edge-tts mutagen
# .env (project root, auto-loaded): NVIDIA_API_KEY=...  (free: build.nvidia.com)
```

## Usage

**Task 1 — script:**
```bash
python pipeline/script_engine.py "AI in Indian education"
# -> output/scripts/ai-in-indian-education.json
```

If the LLM reply is unparseable (reasoning models sometimes ramble past the
token cap), the script stage auto-retries up to 3× with a larger token budget.

**Task 2 — visuals:**
```bash
python pipeline/visual_engine.py output/scripts/ai-in-indian-education.json
# -> output/videos/<slug>/scene-<n>.png  (720×1280)
```

**Task 3 — voiceover:**
```bash
python pipeline/voice_engine.py output/scripts/ai-in-indian-education.json
# -> output/videos/<slug>/audio/scene-<n>.mp3  (rate-fitted to scene durations)
# male voice:  --voice en-IN-PrabhatNeural
```

**Task 4 — composition:**
```bash
python pipeline/composer.py output/scripts/ai-in-indian-education.json
# -> output/videos/<slug>/final.mp4  (H.264 720×1280@30fps + AAC)
```

**Task 6 — deploy (Render + Docker):**
```bash
# create an empty repo named ctrl_freak on github.com (no README init), then:
git remote add origin https://github.com/<you>/ctrl_freak.git
git push -u origin main
# render.com → sign in with GitHub → New + → Blueprint → pick ctrl_freak
# → Render reads render.yaml → paste NVIDIA_API_KEY when prompted → Deploy
```
Free-tier notes: the service sleeps after ~15 min idle (first request wakes it,
~1 min); `output/` is ephemeral — videos regenerate per job.

Each stage validates its output and writes a manifest JSON alongside the assets,
so every downstream stage consumes measured, real values.
