from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
_API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")


def _ensure_model_path(model: str) -> str:
    return model if model.startswith("models/") else f"models/{model}"


def _build_request(prompt: str, system: Optional[str], temperature: float, max_tokens: int) -> Dict[str, Any]:
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


async def call_gemini_json_async(prompt: str, *, system: Optional[str] = None, model: Optional[str] = None,
                                 temperature: float = 0.4, max_output_tokens: int = 2048,
                                 timeout_s: float = 30.0) -> Dict[str, Any]:
    api_key = _GEMINI_API_KEY
    if not api_key:
        return {}
    model_name = _ensure_model_path(model or _DEFAULT_MODEL)
    url = f"{_API_BASE}/{model_name}:generateContent?key={api_key}"
    payload = _build_request(prompt, system, temperature, max_output_tokens)
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            text = _parse_text(resp.json())
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
    except httpx.HTTPError as e:
        try:
            detail = e.response.text  # type: ignore[union-attr]
        except Exception:
            detail = str(e)
        print("Gemini HTTPError:", detail)
        return {}
    except Exception as e:
        print("Gemini error:", e)
        return {}


# Optional sync shim for compatibility (used nowhere by default)
def call_gemini_json(prompt: str, **kwargs: Any) -> Dict[str, Any]:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return {}
    return asyncio.run(call_gemini_json_async(prompt, **kwargs))
