from dataclasses import dataclass
import aiohttp
from .generation_types import GenerateRequest  # :contentReference[oaicite:8]{index=8}

@dataclass
class LLMConfig:
    base_url: str
    api_key: str | None = None
    timeout_sec: int = 8
    enabled: bool = True


class DeepSeekProvider:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg

    def _build_prompt(self, req: GenerateRequest) -> str:
        # структурированный промпт = стабильнее результаты
        wishes = ", ".join(req.wishes) if req.wishes else "успехов и благополучия"
        return (
            f"Сгенерируй поздравление на русском.\n"
            f"Стиль: {req.style}.\n"
            f"Канал: {req.channel}.\n"
            f"Повод: {req.holiday_name}.\n"
            f"Имя: {req.name}.\n"
            f"Пожелания: {wishes}.\n"
            f"Требования:\n"
            f"- Для business/official без эмодзи\n"
            f"- Для official используй вежливое обращение\n"
            f"- Без токсичных/грубых слов\n"
            f"Верни только готовый текст."
        )

    async def generate(self, req: GenerateRequest) -> str:
        if not self.cfg.enabled:
            raise RuntimeError("LLM disabled")

        prompt = self._build_prompt(req)

        headers = {}
        if self.cfg.api_key:
            headers["Authorization"] = f"Bearer {self.cfg.api_key}"

        # ВНИМАНИЕ: endpoint/формат подстроишь под ваш DeepSeek
        payload = {"prompt": prompt}

        timeout = aiohttp.ClientTimeout(total=self.cfg.timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.cfg.base_url, json=payload, headers=headers) as r:
                if r.status != 200:
                    raise RuntimeError(f"LLM http {r.status}")
                data = await r.json()

        # подстрой ключ под реальный ответ
        text = data.get("text") or data.get("result") or ""
        return text.strip()
