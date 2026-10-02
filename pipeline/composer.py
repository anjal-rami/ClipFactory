"""
Task 4 - Composer (ctrl_freak pipeline)

Assembles the final 9:16 MP4 from Task 2 images + Task 3 voiceover:
  per scene  -> Ken Burns zoom on the still (alternating in/out)
             -> caption overlay (scene 1 shows the hook, others the on_screen_text)
             -> voiceover audio padded to the clip length
  then       -> concat all clips -> output/videos/<slug>/final.mp4

Clip durations come from the measured voiceover lengths (voice_manifest.json),
not the scripted targets, so no scene ever cuts off mid-sentence.

Usage:
  python pipeline/composer.py output/scripts/<slug>.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "videos"
TOOLS_DIR = PROJECT_ROOT / "tools"

FPS = 30
try:  # single source of truth for output resolution (visual engine owns it)
    from visual_engine import TARGET_H as H, TARGET_W as W
except ImportError:  # package import (web app)
    from pipeline.visual_engine import TARGET_H as H, TARGET_W as W
FONTSIZE = int(58 * H / 1280)          # caption sizes scale with resolution
BORDERW = int(9 * H / 1280)            # caption outline (modern shorts style)
SHADOWY = int(8 * H / 1280)
CAPTION_MARGIN = int(320 * H / 1280)   # lower-middle third: above platform UI overlays
PAD_SECONDS = 0.5      # breathing room after each voice clip
ZOOM_AMOUNT = 0.10     # 10% Ken Burns travel
FONT = "C:/Windows/Fonts/arialbd.ttf"
# Devanagari captions need a font with Hindi glyphs (arialbd has none).
# Bundled Noto font first: identical rendering on Windows and in the Docker image.
DEVANAGARI_FONTS = (
    str(PROJECT_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"),
    str(PROJECT_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Regular.ttf"),
    "C:/Windows/Fonts/Nirmala.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-Regular.ttf",
)


def has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def pick_font(text: str) -> str:
    if has_devanagari(text):
        for cand in DEVANAGARI_FONTS:
            if os.path.exists(cand):
                return cand
    return FONT


def find_ffmpeg(name: str) -> str:
    # The zip extracts as tools/ffmpeg/<build-name>/bin/<name>.exe — search any depth.
    cand = sorted(TOOLS_DIR.glob(f"**/bin/{name}.exe"))
    if cand:
        return str(cand[-1])
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(f"{name}.exe not found (looked in {TOOLS_DIR} and PATH)")


def esc_drawtext(text: str) -> str:
    """Make a string safe inside a drawtext text='...' value."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")


def wrap_text(text: str, width: int = 22, max_lines: int = 3) -> str:
    """Greedy word wrap; drawtext has no auto-wrap."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines[max_lines - 1] = " ".join(lines[max_lines - 1:])  # spill into last line
        lines = lines[:max_lines]
    return "\n".join(lines)


def run(cmd: list) -> None:
    # shell=False (explicit): cmd is always an argv list, never a shell string.
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-600:]
        raise RuntimeError(f"ffmpeg failed ({' '.join(cmd[:3])}...):\n{tail}")


def build_clip(ffmpeg: str, img: Path, audio: Path, out: Path, dur: float, caption: str, zoom_in: bool) -> None:
    frames = max(int(round(dur * FPS)), 2)
    last = frames - 1
    if zoom_in:
        z = f"min(1.0+{ZOOM_AMOUNT}*on/{last},{1.0 + ZOOM_AMOUNT})"
    else:
        z = f"max({1.0 + ZOOM_AMOUNT}-{ZOOM_AMOUNT}*on/{last},1.0)"

    caption = esc_drawtext(wrap_text(caption))
    font_escaped = pick_font(caption).replace("\\", "/").replace(":", "\\:")
    vf = (
        f"scale={W * 2}:{H * 2}:flags=lanczos,"
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={W}x{H}:fps={FPS},"
        f"drawtext=fontfile='{font_escaped}':text='{caption}':"
        f"fontsize={FONTSIZE}:fontcolor=white:bordercolor=black@0.85:borderw={BORDERW}:"
        f"shadowcolor=black@0.5:shadowx=0:shadowy={SHADOWY}:"
        f"text_align=center:line_spacing=10:x=(w-text_w)/2:y=h-text_h-{CAPTION_MARGIN},"
        f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(dur - 0.3, 0):.2f}:d=0.3,format=yuv420p"
    )
    run([
        ffmpeg, "-y", "-i", str(img), "-i", str(audio),
        "-filter_complex", f"[0:v]{vf}[v];[1:a]apad[a]",
        "-map", "[v]", "-map", "[a]",
        "-t", f"{dur:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        str(out),
    ])


def compose(slug: str) -> Path:
    video_dir = OUTPUT_ROOT / slug
    vis = json.loads((video_dir / "visual_manifest.json").read_text(encoding="utf-8"))
    voi = json.loads((video_dir / "voice_manifest.json").read_text(encoding="utf-8"))
    script = json.loads((PROJECT_ROOT / "output" / "scripts" / f"{slug}.json").read_text(encoding="utf-8"))

    ffmpeg, ffprobe = find_ffmpeg("ffmpeg"), find_ffmpeg("ffprobe")
    audio_by_scene = {s["scene"]: s for s in voi["scenes"]}
    image_by_scene = {s["scene"]: s for s in vis["scenes"]}

    n = len(script["scenes"])
    clips = []
    for idx in range(1, n + 1):
        scene = script["scenes"][idx - 1]
        img = Path(image_by_scene[idx]["image"])
        aud = Path(audio_by_scene[idx]["audio"])
        if not img.is_file() or not aud.is_file():
            raise SystemExit(f"scene {idx}: missing {'image' if not img.is_file() else 'audio'} asset")
        dur = max(audio_by_scene[idx]["duration_seconds"] + PAD_SECONDS, 2.0)
        caption = script["hook"] if idx == 1 else scene["on_screen_text"]
        clip = video_dir / f"clip-{idx}.mp4"
        print(f"[{idx}/{n}] clip {dur:.1f}s  caption={caption!r}")
        build_clip(ffmpeg, img, aud, clip, dur, caption, zoom_in=(idx % 2 == 1))
        clips.append(clip)

    list_file = video_dir / "clips.txt"
    list_file.write_text("".join(f"file '{c.name}'\n" for c in clips), encoding="utf-8")
    final = video_dir / "final.mp4"
    raw = video_dir / "final_raw.mp4"
    print("concatenating...")
    run([
        ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        str(raw),
    ])

    # Optional music bed: drop any licensed track at assets/music/bed.mp3 and it
    # is looped under the voiceover at low volume with a fade-out at the end.
    bed = PROJECT_ROOT / "assets" / "music" / "bed.mp3"
    if bed.exists():
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(raw)],
            capture_output=True, text=True, check=True, shell=False,
        )
        total = float(json.loads(probe.stdout)["format"]["duration"])
        print(f"mixing music bed under {total:.1f}s of video...")
        run([
            ffmpeg, "-y", "-i", str(raw), "-stream_loop", "-1", "-i", str(bed),
            "-filter_complex",
            f"[1:a]volume=0.12,afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[bed];"
            f"[0:a][bed]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(final),
        ])
        raw.unlink()
    else:
        os.replace(raw, final)

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(final)],
        capture_output=True, text=True, check=True, shell=False,
    )
    info = json.loads(probe.stdout)["format"]
    print(f"Done: {final}")
    print(f"      {float(info['duration']):.1f}s, {int(info['size']) // 1024}KB, {n} clips")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Assemble scene images + voiceover into the final 9:16 MP4")
    ap.add_argument("script", type=Path, help="script JSON from Task 1 (slug drives asset lookup)")
    args = ap.parse_args()
    if not args.script.is_file():
        raise SystemExit(f"script not found: {args.script}")
    compose(args.script.stem)
