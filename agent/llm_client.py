"""
Shared LLM client wrapping Anthropic Python SDK.
Uses the same ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL env vars as Claude Code CLI.
"""
import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (works even under cron's minimal environment)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

from anthropic import Anthropic


_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN in environment")
        _client = Anthropic(
            api_key=api_key,
            base_url=os.environ.get("ANTHROPIC_BASE_URL"),
        )
    return _client


def _model_name() -> str:
    return os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro")


def chat(system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
    """Send a chat completion and return the text response."""
    client = _get_client()
    resp = client.messages.create(
        model=_model_name(),
        max_tokens=4096,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return resp.content[0].text


def chat_json(system_prompt: str, user_message: str, temperature: float = 0.3) -> dict:
    """Send a chat completion and parse the response as JSON."""
    raw = chat(system_prompt, user_message, temperature)
    raw = raw.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        nl = raw.find("\n")
        if nl != -1:
            raw = raw[nl + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a JSON object/array in the text
        match = re.search(r"(\[.*\]|\{.*\})", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Failed to parse JSON from response: {raw[:200]}")
