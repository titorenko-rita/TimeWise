from __future__ import annotations

import argparse
import asyncio

from src.text_generator.db import SessionMaker
from src.workflow.real_sender import real_sender
from src.workflow.worker_service import worker_process_job


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=100,
        help="Maximum number of jobs to process in one run",
    )
    args = parser.parse_args()

    processed = 0

    while processed < args.max_jobs:
        async with SessionMaker() as session:
            result = await worker_process_job(session, real_sender)

        if result is None:
            print(f"No more pending/retry jobs. Processed: {processed}")
            return

        processed += 1
        print(
            f"[{processed}] Processed real job: status={result.status}, "
            f"error={result.error_message}, duration_ms={result.duration_ms}"
        )

    print(f"Reached max-jobs limit: {processed}")


if __name__ == "__main__":
    asyncio.run(main())
