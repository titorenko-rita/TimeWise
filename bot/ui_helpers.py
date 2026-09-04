"""Вспомогательные функции для работы с экранными сообщениями Telegram."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

_temp_message_ids: dict[int, list[int]] = defaultdict(list)
_temp_context_chats: set[int] = set()


def _remember_temp_message(chat_id: int, message_id: int) -> None:
    ids = _temp_message_ids[chat_id]
    if message_id not in ids:
        ids.append(message_id)
    _temp_context_chats.add(chat_id)


async def send_temp_message(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    disable_web_page_preview: bool | None = None,
) -> Message:
    sent = await message.answer(
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_web_page_preview,
    )
    _remember_temp_message(message.chat.id, sent.message_id)
    return sent


async def clear_temp_messages(message: Message | None) -> None:
    if message is None:
        return
    chat_id = message.chat.id
    ids = _temp_message_ids.get(chat_id, [])
    if not ids:
        return

    async def _delete_one(message_id: int) -> None:
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest:
            pass
        except Exception as e:
            logger.debug("Не удалось удалить временное сообщение %s/%s: %s", chat_id, message_id, e)

    # Delete helper messages concurrently to avoid multi-second UI delays
    # when a screen accumulated several previews/chunks.
    await asyncio.gather(*(_delete_one(message_id) for message_id in ids[:]), return_exceptions=True)
    _temp_message_ids.pop(chat_id, None)


def has_temp_context(message: Message | None) -> bool:
    return message is not None and message.chat.id in _temp_context_chats


def reset_temp_context(message: Message | None) -> None:
    if message is None:
        return
    _temp_context_chats.discard(message.chat.id)


async def safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise
