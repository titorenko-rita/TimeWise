from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from src.text_generator.db import SessionMaker


async def anonymize_contact(contact_id: int, soft_delete: bool) -> None:
    async with SessionMaker() as session:
        await session.execute(
            text(
                """
                UPDATE public.contacts
                SET
                    first_name = CONCAT('Удалённый контакт #', id),
                    last_name = NULL,
                    middle_name = NULL,
                    tg_username = NULL,
                    tg_chat_id = NULL,
                    email = NULL,
                    position = NULL,
                    company = NULL,
                    notes = NULL,
                    is_active = false,
                    is_deleted = :is_deleted,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :contact_id;
                """
            ),
            {
                "contact_id": int(contact_id),
                "is_deleted": bool(soft_delete),
            },
        )
        await session.commit()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-id", type=int, required=True, help="Contact id to anonymize")
    parser.add_argument(
        "--soft-delete",
        action="store_true",
        help="Also set is_deleted = true after anonymization",
    )
    args = parser.parse_args()

    await anonymize_contact(args.contact_id, soft_delete=args.soft_delete)
    print(
        f"Contact {args.contact_id} anonymized. "
        f"is_deleted={'true' if args.soft_delete else 'false'}"
    )


if __name__ == "__main__":
    asyncio.run(main())
