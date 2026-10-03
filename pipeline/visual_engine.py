"""
Task 2 - Visual Engine (ClipFactory pipeline)

Reads a script JSON (Task 1 output) and generates one 9:16 image per scene.

Backends (auto, first that works per scene):
  nvidia        -> FLUX.1-dev on ai.api.nvidia.com  (needs NVIDIA_API_KEY, best quality)
  pollinations  -> image.pollinations.ai            (no key, native 9:16)

All images are post-processed to exactly 720x1280 (9:16) with Pillow.

Usage:
  python pipeline/visual_engine.py output/scripts/<slug>.json [--backend auto|nvidia|pollinations]

Output:
  output/videos/<slug>/scene-<n>.png
  output/videos/<slug>/visual_manifest.json
"""

import argparse
import base64
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

try:  # package import (web app) vs direct CLI execution
    from pipeline import llm
except ImportError:  # running as a script: pipeline/ itself is on sys.path
    import llm  # noqa: F401  (loads .env on import)

from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "output" / "videos"

TARGET_W, TARGET_H = 1080, 1920  # exact 9:16, full-HD vertical

FLUX_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"

# SSRF guard: this worker runs server-side (Task 6) and builds requests from
# user-derived topics, so pin targets to https + an explicit host allowlist
# and refuse any redirect that leaves it.
ALLOWED_HOSTS = {"ai.api.nvidia.com", "image.pollinations.ai"}


def _guard(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise RuntimeError(f"blocked request to non-allowlisted target: {parts.scheme}://{parts.hostname}")


class _PinnedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _guard(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_PinnedRedirects)


def nvidia_key() -> str | None:
    return llm.os.environ.get("NVIDIA_API_KEY")


def _is_image(raw: bytes) -> bool:
    return raw[:4] == b"\x89PNG" or raw[:3] == b"\xff\xd8\xff"


def gen_nvidia(prompt: str, seed: int, timeout: int = 150) -> bytes:
    """FLUX.1-dev -> raw image bytes. Endpoint returns either raw image data
    or JSON {'artifacts': [{'base64': ...}]} depending on its mood - sniff both."""
    key = nvidia_key()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY not set")
    payload = {"prompt": prompt, "steps": 28, "cfg_scale": 3.5, "seed": seed}
    req = urllib.request.Request(
        FLUX_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "image/png, image/jpeg, application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    _guard(FLUX_URL)
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read()
    if _is_image(raw):
        return raw
    # json.loads accepts bytes and auto-detects UTF-8/16/32 (with BOM) per RFC.
    # Manual .decode("utf-8") explodes on UTF-16 JSON error bodies (0xff BOM).
    data = json.loads(raw)
    b64 = data["artifacts"][0]["base64"]
    return base64.b64decode(b64)


def gen_pollinations(prompt: str, seed: int, timeout: int = 150) -> bytes:
    """Pollinations -> raw JPEG bytes, no key, native 9:16.
    Minimal params only: model/nologo cause 402 paywall errors."""
    q = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{q}?width={TARGET_W}&height={TARGET_H}&seed={seed}"
    req = urllib.request.Request(url, headers={"User-Agent": "clipfactory-pipeline/0.1"})
    _guard(url)
    with _OPENER.open(req, timeout=timeout) as resp:
        return resp.read()


BACKENDS = {
    "nvidia": gen_nvidia,
    "pollinations": gen_pollinations,
}


def to_916(raw: bytes) -> Image.Image:
    """Decode, center-crop to 9:16, resize to 720x1280."""
    # Image.open treats a bare bytes arg as a *filename* (Pillow's isPath
    # includes bytes) -> UTF-8 decode crash on binary data. Wrap in BytesIO.
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    w, h = img.size
    target_ratio = TARGET_W / TARGET_H
    ratio = w / h
    if ratio > target_ratio:  # too wide -> crop sides
        new_w = int(h * target_ratio)
        x0 = (w - new_w) // 2
        img = img.crop((x0, 0, x0 + new_w, h))
    elif ratio < target_ratio:  # too tall -> crop top/bottom
        new_h = int(w / target_ratio)
        y0 = (h - new_h) // 2
        img = img.crop((0, y0, w, y0 + new_h))
    return img.resize((TARGET_W, TARGET_H), Image.LANCZOS)


def stable_seed(slug: str, scene_no: int) -> int:
    return zlib.crc32(f"{slug}-{scene_no}".encode()) % (2**31)


def generate_images(script_path: Path, backend: str = "auto") -> dict:
    script = json.loads(script_path.read_text(encoding="utf-8"))
    slug = script_path.stem
    scenes = script["scenes"]
    out_dir = OUTPUT_ROOT / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    available = list(BACKENDS) if backend == "auto" else [backend]
    if backend != "auto" and backend == "nvidia" and not nvidia_key():
        raise SystemExit("backend=nvidia but NVIDIA_API_KEY is not set (.env)")

    manifest = {
        "slug": slug,
        "script": str(script_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target": f"{TARGET_W}x{TARGET_H}",
        "scenes": [],
    }

    for idx, scene in enumerate(scenes, 1):
        prompt = scene.get("image_prompt")
        style = script.get("visual_style") or "cinematic photograph, rich colour grade, soft dramatic lighting, high detail, consistent look across all scenes"
        if style:
            prompt = f"{style}. {prompt}"
        if not prompt:
            print(f"[{idx}/{len(scenes)}] scene {idx}: SKIPPED (no image_prompt)")
            manifest["scenes"].append({"scene": idx, "status": "skipped"})
            continue

        seed = stable_seed(slug, idx)
        img_path = out_dir / f"scene-{idx}.png"
        used = None
        errors = []
        t0 = time.time()

        for name in available:
            try:
                raw = BACKENDS[name](prompt, seed)
                img = to_916(raw)
                img.save(img_path, "PNG")
                used = name
                break
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
                print(f"        {name} failed: {type(e).__name__}: {str(e)[:100]}")

        if used is None:
            print(f"[{idx}/{len(scenes)}] scene {idx}: FAILED (all backends)")
            manifest["scenes"].append({"scene": idx, "status": "failed", "seed": seed, "errors": errors})
            continue

        kb = img_path.stat().st_size // 1024
        print(
            f"[{idx}/{len(scenes)}] scene {idx}: {img_path.name} "
            f"{TARGET_W}x{TARGET_H} {kb}KB | {used} | seed {seed} | {time.time()-t0:.1f}s"
        )
        manifest["scenes"].append(
            {
                "scene": idx,
                "status": "ok",
                "image": str(img_path),
                "backend": used,
                "model": "flux.1-dev" if used == "nvidia" else "flux (pollinations)",
                "seed": seed,
                "prompt": prompt,
            }
        )

    # Second pass: one more try for scenes whose backends all failed — transient
    # upstream degradation (rate limits, slow endpoints) often clears in seconds.
    for s in [e for e in manifest["scenes"] if e.get("status") == "failed"]:
        idx = s["scene"]
        prompt = scenes[idx - 1].get("image_prompt")
        if not prompt:
            continue
        seed = stable_seed(slug, idx)
        for name in available:
            try:
                raw = BACKENDS[name](prompt, seed)
                img = to_916(raw)
                img.save(out_dir / f"scene-{idx}.png", "PNG")
                s["status"], s["backend"], s["image"] = "ok", name, str(out_dir / f"scene-{idx}.png")
                s["model"] = "flux.1-dev" if name == "nvidia" else "flux (pollinations)"
                s["seed"], s["prompt"] = seed, prompt
                print(f"        scene {idx}: recovered on retry via {name}")
                break
            except Exception as e:
                s.setdefault("errors", []).append(f"retry {name}: {type(e).__name__}: {str(e)[:80]}")

    man_path = out_dir / "visual_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for s in manifest["scenes"] if s.get("status") == "ok")
    print(f"Done: {ok}/{len(scenes)} scenes rendered -> {out_dir}")
    print(f"Manifest: {man_path}")
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Generate 9:16 scene images from a script JSON")
    ap.add_argument("script", type=Path, help="script JSON from Task 1")
    ap.add_argument("--backend", choices=["auto", "nvidia", "pollinations"], default="auto")
    args = ap.parse_args()
    if not args.script.is_file():
        raise SystemExit(f"script not found: {args.script}")
    generate_images(args.script, args.backend)
