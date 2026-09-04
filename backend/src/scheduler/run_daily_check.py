import asyncio

from src.scheduler.daily_check import daily_check


if __name__ == "__main__":
    asyncio.run(daily_check())
