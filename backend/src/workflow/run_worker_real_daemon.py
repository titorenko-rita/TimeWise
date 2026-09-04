from __future__ import annotations

import argparse
import asyncio

from src.text_generator.db import SessionMaker
from src.workflow.real_sender import real_sender
from src.workflow.worker_service import worker_process_job


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=10,
        help="How long to sleep when there are no pending/retry jobs ready to run",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=0,
        help="Optional limit for processed jobs; 0 means run forever",
    )
    args = parser.parse_args()

    processed = 0
    print(
        "Worker daemon started: "
        f"poll_interval_seconds={args.poll_interval_seconds}, max_jobs={args.max_jobs or 'infinite'}"
    )

    while True:
        async with SessionMaker() as session:
            result = await worker_process_job(session, real_sender)

        if result is None:
            await asyncio.sleep(max(1, args.poll_interval_seconds))
            continue

        processed += 1
        print(
            f"[{processed}] Processed real job: status={result.status}, "
            f"error={result.error_message}, duration_ms={result.duration_ms}"
        )

        if args.max_jobs and processed >= args.max_jobs:
            print(f"Reached max-jobs limit: {processed}")
            return


if __name__ == "__main__":
    asyncio.run(main())
