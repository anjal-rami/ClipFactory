"""
Task 3 - Voice Engine (ClipFactory pipeline)

Reads a script JSON (Task 1) and speaks each scene's narration with a neural
TTS voice (edge-tts: free, no API key). Each clip is rate-fitted to its
scene's duration: if the take runs long, it is re-synthesized slightly faster
(up to --max-speedup) until it fits or the cap is reached.

Default voice: en-IN-NeerjaNeural (Indian English female - fits Qoneqt's
audience). Override with --voice. The script's CTA is appended to the last
scene's audio; the hook stays on-screen text (Task 4 captions).

Usage:
  python pipeline/voice_engine.py output/scripts/<slug>.json [--voice en-IN-PrabhatNeural]

Output:
  output/videos/<slug>/audio/scene-<n>.mp3
  output/videos/<slug>/voice_manifest.json
"""

import argparse
import asyncio
import json
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "videos"

DEFAULT_VOICE = "en-IN-NeerjaNeural"
VOICE_BY_LANGUAGE = {"english": DEFAULT_VOICE, "hindi": "hi-IN-SwaraNeural"}
SLACK_SECONDS = 1.5   # accept a take if it fits target + slack
RATE_STEP = 8         # % faster per retry


def synth(text: str, voice: str, rate: int, out: Path) -> None:
    asyncio.run(edge_tts.Communicate(text, voice, rate=f"{rate:+d}%").save(str(out)))


def audio_seconds(path: Path) -> float:
    return MP3(str(path)).info.length


def render_scene(text: str, voice: str, target: float, out: Path, max_speedup: int) -> tuple[float, int, bool]:
    """Synthesize, measure, speed up until the take fits. Returns (duration, rate, over)."""
    rate = 0
    dur = 0.0
    for _ in range(1 + max_speedup // RATE_STEP):
        synth(text, voice, rate, out)
        dur = audio_seconds(out)
        if dur <= target + SLACK_SECONDS or rate >= max_speedup:
            break
        rate = min(rate + RATE_STEP, max_speedup)
    return dur, rate, dur > target + SLACK_SECONDS


def voice_script(script_path: Path, voice: str | None = None, max_speedup: int = 25) -> dict:
    script = json.loads(script_path.read_text(encoding="utf-8"))
    language = script.get("language", "English")
    voice = voice or VOICE_BY_LANGUAGE.get(language.lower(), DEFAULT_VOICE)
    slug = script_path.stem
    scenes = script["scenes"]
    audio_dir = OUTPUT_ROOT / slug / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "slug": slug,
        "voice": voice,
        "language": language,
        "scenes": [],
    }
    total = 0.0

    for idx, scene in enumerate(scenes, 1):
        text = scene["narration"]
        if idx == len(scenes) and script.get("cta"):
            text = f"{text} {script['cta']}"

        out = audio_dir / f"scene-{idx}.mp3"
        dur, rate, over = render_scene(text, voice, scene["duration_seconds"], out, max_speedup)
        total += dur

        status = "ok" if not over else "over-target"
        print(
            f"[{idx}/{len(scenes)}] scene-{idx}.mp3  {dur:5.1f}s / {scene['duration_seconds']}s target"
            f"  rate {rate:+d}%  {'OK' if not over else 'OVER'}"
        )
        manifest["scenes"].append(
            {
                "scene": idx,
                "status": status,
                "audio": str(out),
                "bytes": out.stat().st_size,
                "duration_seconds": round(dur, 2),
                "target_seconds": scene["duration_seconds"],
                "rate_applied": f"{rate:+d}%",
                "text": text,
            }
        )

    man_path = OUTPUT_ROOT / slug / "voice_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    over_n = sum(1 for s in manifest["scenes"] if s["status"] != "ok")
    print(f"Done: {len(scenes)} clips, total speech {total:.1f}s, {over_n} over-target -> {audio_dir}")
    print(f"Manifest: {man_path}")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Speak each scene of a script JSON with neural TTS")
    ap.add_argument("script", type=Path, help="script JSON from Task 1")
    ap.add_argument("--voice", default=None, help="edge-tts voice; auto-picked from the script's language if omitted")
    ap.add_argument("--max-speedup", type=int, default=25, help="max %% rate-up applied to fit duration")
    args = ap.parse_args()
    if not args.script.is_file():
        raise SystemExit(f"script not found: {args.script}")
    voice_script(args.script, args.voice, args.max_speedup)
