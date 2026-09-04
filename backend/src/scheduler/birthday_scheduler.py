import asyncio
import os
from datetime import datetime, time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.scheduler.daily_check import daily_check
from src.logging.logger import setup_logging, get_logger


setup_logging()
logger = get_logger("scheduler")


SCHEDULE_TIME = time(
    int(os.environ.get("SCHEDULE_HOUR", "14")),
    int(os.environ.get("SCHEDULE_MINUTE", "30")),
)
POLL_MINUTES = max(1, int(os.environ.get("SCHEDULER_POLL_MINUTES", "5")))


async def check_missed_run():
    """
    Проверяем — не пропустили ли сегодняшнюю проверку.
    """

    now = datetime.now().time()

    if now > SCHEDULE_TIME:
        logger.info("⏰ Возможен пропущенный запуск. Проверяем события...")
        await daily_check()
    else:
        logger.info("Сегодняшний запуск ещё впереди")


async def start_scheduler():

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        daily_check,
        "cron",
        hour=SCHEDULE_TIME.hour,
        minute=SCHEDULE_TIME.minute,
        id="daily_check_cron",
    )

    scheduler.add_job(
        daily_check,
        "interval",
        minutes=POLL_MINUTES,
        id="daily_check_poll",
    )

    scheduler.start()

    logger.info("📅 Планировщик запущен")
    logger.info(
        "⏰ Проверка событий каждый день в %02d:%02d",
        SCHEDULE_TIME.hour,
        SCHEDULE_TIME.minute,
    )
    logger.info(
        "🔁 Дополнительная проверка новых событий каждые %d минут",
        POLL_MINUTES,
    )

    while True:
        await asyncio.sleep(3600)


async def main():

    logger.info("🚀 Сервис запускается")

    await check_missed_run()

    await start_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
