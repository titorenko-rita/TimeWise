from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class LLMResponse:
    content: str
    raw: Dict[str, Any]


class LLMClient:
    """
    Минимальный async-клиент под OpenAI-compatible Chat Completions.
    DeepSeek обычно работает через base_url + path.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        completions_path: str = "/chat/completions",
        timeout_s: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.completions_path = completions_path if completions_path.startswith("/") else "/" + completions_path
        self.timeout_s = timeout_s

    @staticmethod
    def from_env() -> Optional["LLMClient"]:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            return None

        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        completions_path = os.environ.get("DEEPSEEK_COMPLETIONS_PATH", "/chat/completions")
        timeout_s = float(os.environ.get("DEEPSEEK_TIMEOUT_S", "60"))

        return LLMClient(
            api_key=api_key,
            base_url=base_url,
            completions_path=completions_path,
            timeout_s=timeout_s,
        )

    async def chat_completions(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 300,
        extra_body: Optional[dict[str, Any]] = None,
    ) -> LLMResponse:
        url = f"{self.base_url}{self.completions_path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if extra_body:
            payload.update(extra_body)

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text}")
            data = resp.json()

        content = (
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
        )
        if not content or not isinstance(content, str):
            raise RuntimeError(f"LLM вернул пустой content: {data}")

        return LLMResponse(content=content.strip(), raw=data)