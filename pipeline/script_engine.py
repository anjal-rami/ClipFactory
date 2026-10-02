"""
Task 1 - Script & Story Engine (ctrl_freak pipeline, Qoneqt x CTRL FREAK)

Turns a topic into a structured video-script JSON:
  hook + scenes (narration, image_prompt, on_screen_text, duration) + CTA.

This JSON is the "contract" every later stage consumes:
  image prompts -> Task 2 (visuals), narration -> Task 3 (TTS),
  durations -> Task 4 (FFmpeg composition).

Usage:
  python pipeline/script_engine.py "AI in Indian education"            # generate + save
  python pipeline/script_engine.py "AI in Indian education" --dry-run  # show prompt only

Configure the LLM via env vars or a .env file (see pipeline/llm.py):
  NVIDIA_API_KEY / ZAI_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / LLM_BASE_URL+LLM_API_KEY
  Optional: LLM_MODEL
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:  # package import (web app) vs direct CLI execution
    from pipeline import llm
except ImportError:  # running as a script: pipeline/ itself is on sys.path
    import llm

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output" / "scripts"

# The pipeline contract. Later stages read exactly these fields.
SCHEMA_EXAMPLE = {
    "title": "short video title, max 8 words",
    "hook": "scroll-stopping opening line, max 12 words",
    "scenes": [
        {
            "id": 1,
            "narration": "what the voiceover says in this scene",
            "image_prompt": "detailed prompt for an AI image generator",
            "on_screen_text": "caption shown on screen, max 6 words",
            "duration_seconds": 6,
        }
    ],
    "cta": "closing line inviting viewers to join Qoneqt",
    "visual_style": "one English sentence: the single visual style (palette, lighting, mood) shared by ALL scenes",
    "hashtags": ["#example"],
}


def build_prompt(topic: str, language: str = "English") -> str:
    language_rules = ""
    if language.lower() == "hindi":
        language_rules = (
            "\nLANGUAGE RULES:\n"
            "- Write hook, narration, on_screen_text and cta in natural Hindi (Devanagari script).\n"
            "- Keep every image_prompt in ENGLISH — image models follow English best.\n"
        )
    return f"""You are a viral short-form video scriptwriter for the Qoneqt Global Feed,
a community-first social platform. Write a video script for this topic:

TOPIC: {topic}
{language_rules}
Rules:
- Exactly 5 to 6 scenes; total video length between 30 and 45 seconds.
- The hook must stop the scroll: bold claim, question, or surprise (max 12 words).
- Narration is conversational and punchy, roughly 2.5 words per second
  (so a 6-second scene has ~15 words of narration). No fluff, no filler.
- image_prompt: one detailed English prompt for an AI image generator.
  Vertical 9:16 composition. Keep one consistent visual style across all
  scenes (cinematic, vibrant, high detail). Describe subject, setting,
  lighting and mood. Never ask for text or watermarks inside the image.
- on_screen_text: short caption for that scene, max 6 words.
- The final CTA invites viewers to join the conversation on Qoneqt.
- 3-5 relevant hashtags.
- visual_style: one short English sentence describing ONE consistent look for every
  scene of this video — colour palette, lighting and mood matched to the topic.
  It is prepended to each scene's image prompt so the video feels like one film.

Begin your reply with '{' and end with '}'. Do not explain, do not restate these
requirements, do not plan out loud — reply with the finished JSON object only.

Return ONLY valid JSON matching exactly this schema (no markdown, no comments):
{json.dumps(SCHEMA_EXAMPLE, indent=2)}
"""


def validate(script: dict) -> list:
    """Return a list of problems (empty list = valid)."""
    problems = []
    if not script.get("hook"):
        problems.append("missing 'hook'")
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not (5 <= len(scenes) <= 6):
        got = len(scenes) if isinstance(scenes, list) else "non-list"
        problems.append(f"expected 5-6 scenes, got {got}")
    else:
        for i, s in enumerate(scenes, 1):
            for field in ("narration", "image_prompt", "duration_seconds"):
                if not s.get(field):
                    problems.append(f"scene {i}: missing '{field}'")
    total = sum(s.get("duration_seconds", 0) for s in scenes) if isinstance(scenes, list) else 0
    if not (25 <= total <= 50):
        problems.append(f"total duration {total}s outside 25-50s")
    return problems


def slugify(text: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in text.lower())
    return (re.sub(r"-+", "-", slug).strip("-") or "script")[:50]


def output_slug(topic: str, language: str = "English") -> str:
    slug = slugify(topic)
    return slug if language.lower() == "english" else f"{slug}-{language.lower()}"


def generate(topic: str, dry_run: bool = False, language: str = "English") -> dict | None:
    prompt = build_prompt(topic, language)

    if dry_run:
        print("---- PROMPT (dry run, no API call) ----")
        print(prompt)
        return None

    print(f"[1/2] Asking {llm.describe()} to write the script for: {topic!r}")
    # Reasoning models sometimes ramble past the token cap instead of emitting
    # JSON — retry with headroom until a reply parses.
    script = None
    last_error = None
    for attempt in range(1, 4):
        raw = llm.chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=6000)
        try:
            script = llm.extract_json(raw)
            break
        except ValueError as e:
            last_error = e
            print(f"      attempt {attempt}/3: unparseable reply, retrying...")
    if script is None:
        raise last_error

    problems = validate(script)
    if problems:
        print("WARNING - script failed validation:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("      script passed validation")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{output_slug(topic, language)}.json"
    payload = {"topic": topic, "language": language, "generated_at": datetime.now().isoformat(timespec="seconds"), **script}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(s.get("duration_seconds", 0) for s in script.get("scenes", []))
    print(f"[2/2] Saved -> {out_path}")
    print(f"      title : {script.get('title')}")
    print(f"      hook  : {script.get('hook')}")
    print(f"      scenes: {len(script.get('scenes', []))} | total {total}s")
    return script


if __name__ == "__main__":
    args = sys.argv[1:]
    language = "English"
    if "--language" in args:
        i = args.index("--language")
        if i + 1 < len(args):
            language = args[i + 1]
            del args[i:i + 2]
    if not args:
        raise SystemExit('Usage: python pipeline/script_engine.py "your topic here" [--language Hindi] [--dry-run]')
    generate(args[0], dry_run="--dry-run" in args, language=language)
