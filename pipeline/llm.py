"""
Tiny provider-agnostic LLM client for the ClipFactory pipeline.

Zero dependencies (stdlib urllib only). Provider auto-detection, first match wins:

  1. LLM_BASE_URL + LLM_API_KEY   -> any OpenAI-compatible endpoint (custom)
  2. NVIDIA_API_KEY or NVAPI_KEY  -> https://integrate.api.nvidia.com/v1
  3. ZAI_API_KEY                  -> https://api.z.ai/api/paas/v4
  4. OPENAI_API_KEY               -> https://api.openai.com/v1
  5. GEMINI_API_KEY               -> Google Gemini REST (generativelanguage.googleapis.com)

Override the default model of the detected provider with LLM_MODEL.
Optionally loads a .env file from the project root (KEY=VALUE lines) if present.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MODELS = {
    "nvidia": "nvidia/nemotron-3-ultra-550b-a55b",
    "zai": "GLM-5.3-Flash",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}

OPENAI_COMPAT_BASE_URLS = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "openai": "https://api.openai.com/v1",
}


# SSRF guard: base URLs come from operator config (env/.env), never end users —
# so pin every request to the configured host and refuse redirects that leave it.
def _guard_target(url: str, allowed_host: str, allow_http: bool) -> None:
    parts = urlsplit(url)
    ok_scheme = parts.scheme == "https" or (allow_http and parts.scheme == "http")
    if (parts.hostname or "") != allowed_host or not ok_scheme:
        raise RuntimeError(
            f"blocked request to non-configured target: {parts.scheme}://{parts.hostname}"
        )


def _pin_opener(allowed_host: str, allow_http: bool):
    """Opener that refuses redirects leaving the configured provider host."""

    class _Pinned(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            parts = urlsplit(newurl)
            ok_scheme = parts.scheme == "https" or (allow_http and parts.scheme == "http")
            if (parts.hostname or "") != allowed_host or not ok_scheme:
                return None  # refuse: urllib surfaces the 30x as an HTTPError
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_Pinned)

_last_meta = {}


def _load_dotenv():
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def detect_provider():
    """Return (provider_name, base_url, api_key) or (None, None, None)."""
    if os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_API_KEY"):
        return "custom", os.environ["LLM_BASE_URL"].rstrip("/"), os.environ["LLM_API_KEY"]
    for name, env_vars in (
        ("nvidia", ("NVIDIA_API_KEY", "NVAPI_KEY")),
        ("zai", ("ZAI_API_KEY",)),
        ("openai", ("OPENAI_API_KEY",)),
    ):
        for var in env_vars:
            if os.environ.get(var):
                return name, OPENAI_COMPAT_BASE_URLS[name], os.environ[var]
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini", "https://generativelanguage.googleapis.com/v1beta", os.environ["GEMINI_API_KEY"]
    return None, None, None


def describe():
    provider, base_url, _ = detect_provider()
    model = os.environ.get("LLM_MODEL", DEFAULT_MODELS.get(provider, "?"))
    return f"{provider}:{model}" if provider else "no provider configured"


def _chat_openai_compat(base_url, api_key, messages, model, temperature, max_tokens, json_mode):
    """OpenAI-compatible chat completion with a no-json-mode retry fallback."""
    allowed_host = urlsplit(base_url).hostname or ""
    # Custom LLM_BASE_URL may legitimately be http (local runtimes like ollama).
    allow_http = urlsplit(base_url).scheme == "http"
    opener = _pin_opener(allowed_host, allow_http)
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    def post(payload):
        _guard_target(f"{base_url}/chat/completions", allowed_host, allow_http)
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with opener.open(req, timeout=180) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"LLM API error {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"Network error calling LLM: {type(e).__name__}: {e}")

    attempts = 2
    for attempt in range(1, attempts + 1):
        try:
            data = post(body)
            break
        except RuntimeError as e:
            msg = str(e)
            if json_mode and "response_format" in msg:
                # Some OpenAI-compatible endpoints reject response_format; retry without it.
                body.pop("response_format", None)
                json_mode = False
                continue
            transient = "Network error" in msg or any(
                f"error {code}" in msg for code in ("429", "500", "502", "503", "504")
            )
            if attempt < attempts and transient:
                time.sleep(2)
                continue
            raise

    _last_meta.update(
        model=data.get("model", model),
        total_tokens=data.get("usage", {}).get("total_tokens"),
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected LLM response: {json.dumps(data)[:400]}")


def _chat_gemini(api_key, messages, model, temperature, max_tokens, json_mode):
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        {"role": "user" if m["role"] != "assistant" else "model", "parts": [{"text": m["content"]}]}
        for m in messages
        if m["role"] != "system"
    ]
    gen_config = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"
    payload = {"contents": contents, "generationConfig": gen_config}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    allowed_host = urlsplit(base_url_gemini()).hostname or ""
    gemini_url = f"{base_url_gemini()}/models/{model}:generateContent"
    _guard_target(gemini_url, allowed_host, False)
    req = urllib.request.Request(
        gemini_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with _pin_opener(allowed_host, False).open(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API error {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    _last_meta.update(model=model, total_tokens=data.get("usageMetadata", {}).get("totalTokenCount"))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def base_url_gemini():
    return "https://generativelanguage.googleapis.com/v1beta"


def chat(messages, *, model=None, temperature=0.8, max_tokens=2000, json_mode=False):
    """Send messages ([{role, content}, ...]) and return the assistant text."""
    provider, base_url, api_key = detect_provider()
    if not provider:
        raise SystemExit(
            "No LLM provider configured. Set one of these (env or .env file):\n"
            "  NVIDIA_API_KEY   (integrate.api.nvidia.com)\n"
            "  ZAI_API_KEY      (api.z.ai, OpenAI-compatible)\n"
            "  OPENAI_API_KEY   (api.openai.com)\n"
            "  GEMINI_API_KEY   (aistudio.google.com)\n"
            "  LLM_BASE_URL + LLM_API_KEY (any OpenAI-compatible endpoint)\n"
            "Optional: LLM_MODEL to override the default model."
        )
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    _last_meta.update(provider=provider)
    if provider == "gemini":
        return _chat_gemini(api_key, messages, model, temperature, max_tokens, json_mode)
    return _chat_openai_compat(base_url, api_key, messages, model, temperature, max_tokens, json_mode)


def extract_json(text: str):
    """Pull a JSON object out of an LLM reply.

    Handles: <think>...</think> reasoning blocks, markdown fences,
    prose around the JSON, and nested braces.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in LLM response:\n{text[:300]}")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    raise ValueError(f"Could not parse JSON from LLM response:\n{text[:300]}")
