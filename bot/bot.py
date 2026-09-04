"""Точка входа TimeWise Bot."""

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db.schema_check import check_db_schema
from db.session import get_sessionmaker, init_db
from handlers import (
    admin,
    admin_contacts,
    admin_users,
    approvals,
    basic,
    blacklist,
    errors,
    holidays,
    job_queue,
    monitoring,
    templates,
    user,
    viewer,
)
from middleware import LoggingMiddleware, RoleCheckMiddleware
from services.proxy_session import ProxyAwareAiohttpSession
from services.scheduler_service import start_scheduler_service
from services.worker_service import run_worker_loop, stop_worker_task


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
    )

    bot_session = ProxyAwareAiohttpSession(proxy_url=settings.telegram_proxy)
    bot = Bot(
        token=settings.bot_token,
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    sessionmaker = get_sessionmaker()
    logging_middleware = LoggingMiddleware()
    role_middleware = RoleCheckMiddleware(settings.admin_ids)

    # Инициализация схемы БД (временный подход: create_all)
    await init_db()
    await check_db_schema()

    # Регистрация middleware (порядок важен: сначала логирование, потом проверка ролей)
    dp.message.middleware(logging_middleware)
    dp.callback_query.middleware(logging_middleware)
    dp.message.middleware(role_middleware)
    dp.callback_query.middleware(role_middleware)

    # Регистрация роутеров
    dp.include_router(errors.router)  # Обработчик ошибок первым
    dp.include_router(basic.router)
    dp.include_router(admin_users.router)
    dp.include_router(admin_contacts.router)
    dp.include_router(approvals.router)
    dp.include_router(blacklist.router)
    dp.include_router(holidays.router)
    dp.include_router(job_queue.router)
    dp.include_router(monitoring.router)
    dp.include_router(templates.router)
    dp.include_router(viewer.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    scheduler = None
    worker_stop_event = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None

    if settings.scheduler_enabled:
        scheduler = start_scheduler_service(
            sessionmaker,
            bot=bot,
            admin_ids=settings.admin_ids,
            daily_time=settings.scheduler_daily_time,
            run_on_startup=settings.scheduler_run_on_startup,
        )
    if settings.worker_enabled:
        worker_task = asyncio.create_task(
            run_worker_loop(
                sessionmaker,
                bot=bot,
                retry_delays_min=settings.retry_delays_min,
                poll_interval_sec=settings.worker_poll_interval_sec,
                stop_event=worker_stop_event,
                channel="Telegram",
            )
        )

    logging.info("Запускаем TimeWise bot...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        worker_stop_event.set()
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        if worker_task is not None:
            await stop_worker_task(worker_task)
        with suppress(Exception):
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен вручную.")
