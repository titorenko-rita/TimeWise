import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.text_generator.db import SessionMaker


async def import_cache(cache_path: Path) -> int:
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("cache.json must contain a JSON object of hash -> text")

    imported = 0
    async with SessionMaker() as session:
        for hash_key, generated_text in payload.items():
            if not hash_key or not isinstance(generated_text, str):
                continue
            await session.execute(
                text(
                    """
                    INSERT INTO public.text_cache (
                        hash_key,
                        generated_text,
                        created_at,
                        updated_at,
                        used_count,
                        is_deleted
                    )
                    VALUES (
                        :hash_key,
                        :generated_text,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        0,
                        false
                    )
                    ON CONFLICT (hash_key) DO UPDATE
                    SET generated_text = EXCLUDED.generated_text,
                        updated_at = CURRENT_TIMESTAMP,
                        is_deleted = false;
                    """
                ),
                {
                    "hash_key": str(hash_key),
                    "generated_text": generated_text,
                },
            )
            imported += 1
        await session.commit()
    return imported


def archive_cache_file(cache_path: Path) -> Path:
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    archived_path = cache_path.with_name(f"{cache_path.name}.archived-{suffix}")
    cache_path.replace(archived_path)
    return archived_path


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-file",
        default="cache.json",
        help="Path to legacy cache.json file",
    )
    parser.add_argument(
        "--archive-source",
        action="store_true",
        help="Archive cache.json after successful import",
    )
    args = parser.parse_args()

    cache_path = Path(args.cache_file).resolve()
    if not cache_path.exists():
        raise FileNotFoundError(f"Legacy cache file not found: {cache_path}")

    imported = await import_cache(cache_path)
    print(f"Imported cache rows: {imported}")

    if args.archive_source:
        archived_path = archive_cache_file(cache_path)
        print(f"Archived legacy cache to: {archived_path}")


if __name__ == "__main__":
    asyncio.run(main())
