"""Model router — sends prompts to Ollama (fast/smart) or Claude (judge)."""
import json
import os
from typing import Any

import httpx


class ModelRouter:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.fast = cfg["router"]["fast"]
        self.smart = cfg["router"]["smart"]
        self.judge = cfg["router"]["judge"]
        self.ollama_base = cfg["ollama_base"]
        self.claude_key = os.getenv(cfg["claude_env"])
        self._client = httpx.Client(timeout=120.0)
        self._anthropic = None
        if self.claude_key:
            try:
                import anthropic
                self._anthropic = anthropic.Anthropic(api_key=self.claude_key)
            except Exception:
                self._anthropic = None

    def call(self, tier: str, system: str, user: str, json_mode: bool = False) -> str:
        model = {"fast": self.fast, "smart": self.smart, "judge": self.judge}[tier]
        provider, name = model.split(":", 1)
        if provider == "ollama":
            return self._ollama(name, system, user, json_mode)
        if provider == "claude":
            return self._claude(name, system, user, json_mode)
        raise ValueError(f"unknown provider: {provider}")

    def _ollama(self, model: str, system: str, user: str, json_mode: bool) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if json_mode:
            payload["format"] = "json"
        r = self._client.post(f"{self.ollama_base}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _claude(self, model: str, system: str, user: str, json_mode: bool) -> str:
        if not self._anthropic:
            raise RuntimeError("ANTHROPIC_API_KEY not set — judge tier unavailable")
        if json_mode:
            user = user + "\n\nRespond with valid JSON only, no preamble."
        resp = self._anthropic.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    @staticmethod
    def extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0]
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"no JSON object in: {text[:200]}")
        return json.loads(text[start : end + 1])
