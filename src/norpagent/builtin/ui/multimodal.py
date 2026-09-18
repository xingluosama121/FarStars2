# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Multimodal backends (v0.9.9): vision (image understanding) + sound (TTS / STT).

Zero third-party dependency (standard library only), so the Web UI works
out of the box on any platform:

- vision: POST the image to an external vision service (JSON protocol
  compatible with the standalone ``vision.py`` adapters: OpenAI-compatible /
  Anthropic / llama.cpp endpoints behind a thin HTTP service);
- TTS (text → speech): when ``tts_service_url`` is configured, an
  OpenAI-compatible ``/audio/speech`` request is used; otherwise the OS-native
  synthesizer runs locally — Windows SAPI via PowerShell (System.Speech),
  macOS ``say``, Linux ``espeak-ng`` / ``espeak``. No API key required for the
  native path;
- STT (speech → text): when ``stt_service_url`` is configured, an
  OpenAI-compatible ``/audio/transcriptions`` request is used; otherwise the
  Windows local recognizer (SAPI via PowerShell, DictationGrammar) runs on the
  uploaded WAV. Other platforms without a configured service report a clear
  error suggesting the service URL.

All heavy lifting happens on the backend; the browser only records audio and
plays back the returned bytes — nothing depends on browser-native speech APIs.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

_UA = "norpagent-multimodal/2.2.4 (FarStars)"


class MultimodalError(Exception):
    """A multimodal operation failed (vision / TTS / STT) with a human-readable reason."""


# ── HTTP helpers (stdlib) ────────────────────────────────────────────────

def _http_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST JSON → parse JSON response."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", _UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"HTTP request failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"response is not valid JSON: {raw[:200]!r}") from exc


def _http_bytes(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 120.0,
) -> bytes:
    """POST JSON → return raw response bytes (for audio)."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", _UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"HTTP request failed: {exc}") from exc


def _multipart(
    url: str,
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    filedata: bytes,
    file_mime: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """POST multipart/form-data → parse JSON response (OpenAI-compatible STT)."""
    boundary = "----norpagent" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n".encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: {file_mime}\r\n\r\n'
        ).encode("utf-8")
    )
    parts.append(filedata)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("User-Agent", _UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"HTTP request failed: {exc}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"response is not valid JSON: {raw[:200]!r}") from exc


# ── Vision: image understanding ──────────────────────────────────────────

def describe_image(
    image_base64: str,
    ext: str,
    mime: str,
    service_url: str,
    prompt: str,
    timeout: float = 120.0,
    api_key: str = "",
) -> str:
    """Send one image to the external vision service and return its text description.

    Protocol (compatible with the standalone vision.py): POST JSON to
    ``service_url`` with ``{image_base64, ext, mime, prompt}``; the service
    replies ``{"description": "..."}`` (``{"ok": true, "description": ...}`` and
    ``{"text": ...}`` are also accepted). Optional ``api_key`` is sent as a
    ``Bearer`` Authorization header (the vision configuration carries an
    API key slot).
    """
    service_url = (service_url or "").strip()
    if not service_url:
        raise MultimodalError("vision service URL is not configured (Settings → Vision API)")
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = _http_json(
        service_url,
        {
            "image_base64": image_base64,
            "ext": ext,
            "mime": mime,
            "prompt": prompt,
        },
        headers=headers,
        timeout=timeout,
    )
    if isinstance(body, dict):
        for key in ("description", "text", "result", "content"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        if body.get("ok") is True and isinstance(body.get("data"), dict):
            val = body["data"].get("description") or body["data"].get("text")
            if isinstance(val, str) and val.strip():
                return val.strip()
    raise MultimodalError(f"vision service response is missing the description field: {str(body)[:200]}")


def media_describe(
    kind: str,
    data_base64: str,
    ext: str,
    mime: str,
    service_url: str,
    prompt: str = "",
    api_key: str = "",
    timeout: float = 120.0,
) -> str:
    """Send an audio / video payload to an external media service, return its text.

    Generalizes the vision protocol so each modality can route through an
    external service (per-modality ``direct`` / ``service`` routing

    - request: POST JSON ``{"kind": "audio"|"video", "data_base64": ...,
      "ext": ..., "mime": ..., "prompt": ...}``;
    - response accepts ``description`` / ``text`` / ``transcript`` /
      ``content`` / ``result`` (first non-empty wins; ``data`` sub-dict also
      accepted), covering both speech transcription and non-speech audio
      understanding (music / environment - audio is not limited to
      speech) as well as video understanding;
    - optional ``api_key`` is sent as a ``Bearer`` Authorization header.
    """
    service_url = (service_url or "").strip()
    if not service_url:
        raise MultimodalError("media service URL is not configured (Settings → Multimodal → audio/video service)")
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = _http_json(
        service_url,
        {
            "kind": kind,
            "data_base64": data_base64,
            "ext": ext,
            "mime": mime,
            "prompt": prompt,
        },
        headers=headers,
        timeout=timeout,
    )
    if isinstance(body, dict):
        for key in ("description", "text", "transcript", "content", "result"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        if body.get("ok") is True and isinstance(body.get("data"), dict):
            for key in ("description", "text", "transcript"):
                val = body["data"].get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    raise MultimodalError(f"media service response is missing the description field: {str(body)[:200]}")


# ── TTS: text → speech ───────────────────────────────────────────────────

def _ps_encoded(script: str) -> List[str]:
    """Wrap a PowerShell script into a -EncodedCommand argument (no quoting issues)."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc]


def _win_tts_wav(text: str, voice: str, rate: float, out_path: str) -> bool:
    """Windows SAPI (System.Speech) → WAV. Pure stdlib via subprocess."""
    text_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    path_b64 = base64.b64encode(os.path.abspath(out_path).encode("utf-8")).decode("ascii")
    rate_int = max(-10, min(10, int(round((float(rate) - 1.0) * 10))))
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "$s.Rate = %d\n" % rate_int
        + (('try { $s.SelectVoice("%s") } catch {}\n' % voice) if voice else "")
        + "$out = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))\n" % path_b64
        + "$txt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))\n" % text_b64
        + "$s.SetOutputToWaveFile($out)\n"
        + "$s.Speak($txt)\n"
        + "$s.Dispose()\n"
    )
    try:
        proc = subprocess.run(
            _ps_encoded(script),
            capture_output=True,
            timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"Windows TTS call failed: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise MultimodalError(f"Windows TTS failed: {err or 'unknown error'}")
    return os.path.exists(out_path) and os.path.getsize(out_path) > 44


def _mac_tts_wav(text: str, voice: str, rate: float, out_path: str) -> bool:
    """macOS ``say`` → WAV (LEI16@22050)."""
    args = ["say", "-o", out_path, "--data-format=LEI16@22050"]
    if voice:
        args += ["-v", voice]
    if rate:
        args += ["-r", str(int(round(175.0 * float(rate))))]
    args.append(text)
    try:
        proc = subprocess.run(args, capture_output=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"macOS TTS call failed: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise MultimodalError(f"macOS TTS failed: {err or 'unknown error'}")
    return os.path.exists(out_path) and os.path.getsize(out_path) > 44


def _linux_tts_wav(text: str, voice: str, rate: float, out_path: str) -> bool:
    """Linux ``espeak-ng`` / ``espeak`` → WAV."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise MultimodalError(
            "espeak-ng / espeak not found; install it (apt install espeak-ng) or configure a TTS service URL"
        )
    args = [exe, "-w", out_path]
    if voice:
        args += ["-v", voice]
    if rate:
        args += ["-s", str(int(round(175.0 * float(rate))))]
    args.append(text)
    try:
        proc = subprocess.run(args, capture_output=True, timeout=60)
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"Linux TTS call failed: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise MultimodalError(f"Linux TTS failed: {err or 'unknown error'}")
    return os.path.exists(out_path) and os.path.getsize(out_path) > 44


def text_to_speech(
    text: str,
    service_url: str = "",
    api_key: str = "",
    voice: str = "",
    rate: float = 1.0,
    timeout: float = 120.0,
) -> Tuple[bytes, str]:
    """Synthesize speech for ``text`` → ``(audio_bytes, mime)``.

    Priority: configured OpenAI-compatible ``/audio/speech`` service → OS-native
    synthesizer (Windows SAPI / macOS say / Linux espeak-ng).
    """
    text = (text or "").strip()
    if not text:
        raise MultimodalError("no text to read aloud")
    service_url = (service_url or "").strip()
    if service_url:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload: Dict[str, Any] = {
            "model": "tts-1",
            "input": text,
            "voice": voice or "alloy",
            "response_format": "wav",
        }
        if rate:
            payload["speed"] = max(0.25, min(4.0, float(rate)))
        audio = _http_bytes(service_url, payload, headers=headers, timeout=timeout)
        if not audio:
            raise MultimodalError("TTS service returned empty audio")
        return audio, "audio/wav"

    # OS-native path
    with tempfile.TemporaryDirectory(prefix="norp_tts_") as tmp:
        out = os.path.join(tmp, "out.wav")
        if sys.platform.startswith("win"):
            _win_tts_wav(text, voice, rate, out)
        elif sys.platform == "darwin":
            _mac_tts_wav(text, voice, rate, out)
        else:
            _linux_tts_wav(text, voice, rate, out)
        with open(out, "rb") as f:
            data = f.read()
    return data, "audio/wav"


# ── STT: speech → text ───────────────────────────────────────────────────

def _win_stt_text(wav_path: str, language: str, timeout: float) -> str:
    """Windows SAPI local recognition (DictationGrammar) on a WAV file."""
    path_b64 = base64.b64encode(os.path.abspath(wav_path).encode("utf-8")).decode("ascii")
    lang_arg = ""
    if language:
        lang_arg = (
            "try {{ $r = New-Object System.Speech.Recognition.SpeechRecognitionEngine"
            "('{0}'); $r.Dispose() }} catch {{ $lang_ok = $false }}\n".format(language)
        )
    script = (
        "Add-Type -AssemblyName System.Speech\n"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "$p = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))\n" % path_b64
        + "$r = New-Object System.Speech.Recognition.SpeechRecognitionEngine\n"
        + lang_arg
        + "$r.SetInputToWaveFile($p)\n"
        + "$g = New-Object System.Speech.Recognition.DictationGrammar\n"
        + "$r.LoadGrammar($g)\n"
        + "$res = $r.Recognize()\n"
        + "if ($res) { Write-Output $res.Text } else { Write-Output '' }\n"
        + "$r.Dispose()\n"
    )
    try:
        proc = subprocess.run(
            _ps_encoded(script),
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise MultimodalError("local speech recognition timed out (recording too long or engine unresponsive)") from None
    except Exception as exc:  # noqa: BLE001
        raise MultimodalError(f"Windows speech recognition call failed: {exc}") from exc
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise MultimodalError(f"Windows speech recognition failed: {err or 'unknown error'}")
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    return text


def speech_to_text(
    audio: bytes,
    mime: str,
    service_url: str = "",
    api_key: str = "",
    model: str = "",
    language: str = "",
    timeout: float = 120.0,
) -> str:
    """Transcribe speech audio → text.

    Priority: configured OpenAI-compatible ``/audio/transcriptions`` service →
    Windows local SAPI recognizer (WAV input).
    """
    if not audio:
        raise MultimodalError("no audio data received")
    service_url = (service_url or "").strip()
    if service_url:
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        ext = "wav" if "wav" in (mime or "") else "webm"
        fields: Dict[str, str] = {"model": model or "whisper-1"}
        if language:
            fields["language"] = language
        body = _multipart(
            service_url,
            fields,
            "file",
            f"audio.{ext}",
            audio,
            mime or "audio/wav",
            headers=headers,
            timeout=timeout,
        )
        if isinstance(body, dict):
            text = body.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
        raise MultimodalError(f"STT service response is missing text: {str(body)[:200]}")

    # OS-native path
    if not sys.platform.startswith("win"):
        raise MultimodalError(
            "no local speech recognition engine on this platform; configure an "
            "STT service URL in Settings (OpenAI-compatible /audio/transcriptions)"
        )
    with tempfile.TemporaryDirectory(prefix="norp_stt_") as tmp:
        wav = os.path.join(tmp, "in.wav")
        with open(wav, "wb") as f:
            f.write(audio)
        return _win_stt_text(wav, language or "", timeout)


# ── audio beep (backend-generated notification tone, WAV) ────────────────

def beep_wav(duration_ms: int = 120, freq: int = 880, volume: float = 0.35) -> bytes:
    """Generate a short sine-wave beep as WAV (used for new-message notifications).

    Pure stdlib; no audio files shipped. Browser plays it back via <audio>.
    """
    import math
    import struct

    rate = 22050
    n = max(1, int(rate * duration_ms / 1000))
    data = bytearray()
    for i in range(n):
        t = i / rate
        # gentle fade in/out to avoid clicks
        env = min(1.0, i / (rate * 0.01), (n - i) / (rate * 0.01))
        val = int(32767 * volume * env * math.sin(2 * math.pi * freq * t))
        data += struct.pack("<h", val)
    header = bytearray()
    header += b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return bytes(header) + bytes(data)
