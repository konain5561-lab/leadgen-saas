"""
Thin client for the Groq API.

Replaces the earlier local-Ollama integration with the official Groq SDK.
Groq serves fast hosted LLMs (including Llama 3.1) over a cloud API, so you
no longer need to run a local model -- just an API key.

Setup:
    1. Get a free API key at https://console.groq.com/keys
    2. Set it in the environment (recommended):
           $env:GROQ_API_KEY = "gsk_..."
       or paste it into GROQ_API_KEY_DEFAULT below (only for local dev, since
       it would otherwise be committed to the repo).

This module keeps the same public interface (generate / chat / extract_json /
LLMUnavailable) used by scoring.py, chat.py and outreach.py, so swapping from
Ollama to Groq didn't require changes anywhere else.
"""

import json
import os

from groq import Groq

# Model served by Groq. Change here or override with the GROQ_MODEL env var.
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# API key: prefer GROQ_API_KEY from the environment, fall back to the constant.
# Paste a real key into GROQ_API_KEY_DEFAULT if you're not using the env var.
GROQ_API_KEY_DEFAULT = "gsk_..."

GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip() or GROQ_API_KEY_DEFAULT


class LLMUnavailable(Exception):
    """Raised when the Groq API can't be reached or returns an error."""


def _complete(messages: list[dict], temperature: float, timeout: int) -> str:
    """Run a chat completion against Groq, mapping any failure to LLMUnavailable."""
    try:
        client = Groq(api_key=GROQ_API_KEY, timeout=timeout)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=temperature,
        )
        content = completion.choices[0].message.content
        return (content or "").strip()
    except Exception as e:
        raise LLMUnavailable(f"Groq API request failed (check GROQ_API_KEY/model): {e}") from e


def generate(prompt: str, system: str = "", temperature: float = 0.4, timeout: int = 120) -> str:
    """Single-turn generation. Returns the raw text response."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return _complete(messages, temperature, timeout)


def chat(messages: list[dict], temperature: float = 0.4, timeout: int = 120) -> str:
    """Multi-turn chat. `messages` is [{"role": "user"|"assistant"|"system", "content": "..."}]."""
    return _complete(messages, temperature, timeout)


def extract_json(text: str) -> dict:
    """
    LLMs often wrap JSON in prose or markdown fences even when told not to.
    Pull out the first {...} block and parse it, rather than assuming the
    whole response is clean JSON.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")
    return json.loads(text[start:end + 1])
