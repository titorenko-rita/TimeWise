from __future__ import annotations

import asyncio

from src.text_generator.db import SessionMaker
from src.workflow.demo_sender import demo_sender
from src.workflow.worker_service import worker_process_job


async def main() -> None:
    async with SessionMaker() as session:
        result = await worker_process_job(session, demo_sender)
        if result is None:
            print("No pending/retry jobs available")
            return

        print(
            f"Processed job with result: status={result.status}, "
            f"error={result.error_message}, duration_ms={result.duration_ms}"
        )


if __name__ == "__main__":
    asyncio.run(main())
