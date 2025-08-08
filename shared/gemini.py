from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")


def _ensure_model_path(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _build_request(model: str, prompt: str, system: Optional[str], temperature: float, max_tokens: int) -> Dict[str, Any]:
    req: Dict[str, Any] = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    if system:
        req["systemInstruction"] = {"parts": [{"text": system}]}
    return req


def _parse_text(response_obj: Dict[str, Any]) -> str:
    try:
        return response_obj["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return json.dumps({"error": "no_text"})


def call_gemini_json(prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
                      temperature: float = 0.4, max_output_tokens: int = 2048) -> Dict[str, Any]:
    api_key = _GEMINI_API_KEY
    if not api_key:
        return {}

    model_name = _ensure_model_path(model or _DEFAULT_MODEL)
    url = f"{_API_BASE}/{model_name}:generateContent?key={api_key}"
    payload = _build_request(model_name, prompt, system, temperature, max_output_tokens)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            text = _parse_text(json.loads(body))
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start:end+1])
                    except Exception:
                        pass
                return {}
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except Exception:
            err = str(e)
        print("Gemini HTTPError:", err)
        return {}
    except Exception as e:
        print("Gemini error:", e)
        return {}
