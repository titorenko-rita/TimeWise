import asyncio
from typing import Any, AsyncGenerator, Dict, Optional, cast

from aiohttp import ClientError
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import TelegramType
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import TelegramMethod

if False:  # pragma: no cover
    from aiogram.client.bot import Bot


class ProxyAwareAiohttpSession(AiohttpSession):
    def __init__(self, proxy_url: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.proxy_url = proxy_url.strip()

    async def make_request(
        self, bot: "Bot", method: TelegramMethod[TelegramType], timeout: Optional[int] = None
    ) -> TelegramType:
        session = await self.create_session()

        url = self.api.api_url(token=bot.token, method=method.__api_method__)
        form = self.build_form_data(bot=bot, method=method)

        try:
            async with session.post(
                url,
                data=form,
                timeout=self.timeout if timeout is None else timeout,
                proxy=self.proxy_url or None,
            ) as resp:
                raw_result = await resp.text()
        except asyncio.TimeoutError:
            raise TelegramNetworkError(method=method, message="Request timeout error")
        except ClientError as e:
            raise TelegramNetworkError(method=method, message=f"{type(e).__name__}: {e}")
        response = self.check_response(
            bot=bot, method=method, status_code=resp.status, content=raw_result
        )
        return cast(TelegramType, response.result)

    async def stream_content(
        self,
        url: str,
        headers: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if headers is None:
            headers = {}

        session = await self.create_session()

        async with session.get(
            url,
            timeout=timeout,
            headers=headers,
            raise_for_status=raise_for_status,
            proxy=self.proxy_url or None,
        ) as resp:
            async for chunk in resp.content.iter_chunked(chunk_size):
                yield chunk
