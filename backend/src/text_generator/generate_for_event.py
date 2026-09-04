import argparse
import asyncio
from datetime import date
import re
from time import perf_counter

from sqlalchemy import text

from .db import SessionMaker
from .generation_types import GenerateRequest
from .text_service import TextService


def to_percent(grammar_score):
    if grammar_score is None:
        return None
    return int(round(float(grammar_score) * 100))


def calc_age_years(birthday: date | None, event_date: date | None) -> int | None:
    if not birthday or not event_date:
        return None
    years = event_date.year - birthday.year
    if (event_date.month, event_date.day) < (birthday.month, birthday.day):
        years -= 1
    return years


def has_unresolved_placeholders(text_value: str | None) -> bool:
    return bool(re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", text_value or ""))


async def fetch_holiday_name(session, holiday_id: int) -> str | None:
    try:
        q = text(
            "SELECT name FROM public.holidays "
            "WHERE id = :id AND (is_deleted = false OR is_deleted IS NULL)"
        )
        r = await session.execute(q, {"id": holiday_id})
        row = r.first()
        return row[0] if row else None
    except Exception:
        return None


async def try_update_generation_state(session, params: dict) -> None:
    try:
        # Use a savepoint so a generation-metrics write failure does not poison
        # the surrounding transaction for messages / approval queue updates.
        async with session.begin_nested():
            result = await session.execute(
                text(
                    """
                    UPDATE public.events
                    SET generation_status = CAST(:generation_status AS VARCHAR(20)),
                        generation_error = CAST(:generation_error AS TEXT),
                        generation_duration_ms = :generation_duration_ms,
                        generation_cache_hit = :generation_cache_hit,
                        generation_engine = CAST(:generation_engine AS VARCHAR(64)),
                        generated_at = CASE
                            WHEN CAST(:generation_status AS VARCHAR(20)) = 'success' THEN CURRENT_TIMESTAMP
                            ELSE generated_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :event_id;
                    """
                ),
                params,
            )
            if result.rowcount == 0:
                print(f"event_id={params['event_id']}: generation state update matched 0 rows")
    except Exception as exc:
        print(f"event_id={params['event_id']}: generation state update failed: {exc}")


async def pick_responsible_editor_id(session) -> int | None:
    q_me = text(
        """
        SELECT id
        FROM public.users
        WHERE tg_id = :tg_id
          AND role = 'Editor'
          AND (is_deleted = false OR is_deleted IS NULL)
          AND (is_active = true OR is_active IS NULL)
        ORDER BY id ASC
        LIMIT 1;
        """
    )
    r_me = await session.execute(q_me, {"tg_id": 1215166843})
    row_me = r_me.first()
    if row_me:
        return int(row_me[0])

    q_any = text(
        """
        SELECT id
        FROM public.users
        WHERE role = 'Editor'
          AND (is_deleted = false OR is_deleted IS NULL)
          AND (is_active = true OR is_active IS NULL)
        ORDER BY id ASC
        LIMIT 1;
        """
    )
    r_any = await session.execute(q_any)
    row_any = r_any.first()
    return int(row_any[0]) if row_any else None


async def generate_one_event(session, event_id: int, force: bool = False):
    q = text(
        """
        SELECT
            e.id,
            e.contact_id,
            e.holiday_id,
            e.date,
            e.channel,
            e.style,
            e.status,
            c.first_name,
            c.last_name,
            c.middle_name,
            c.gender,
            c.birthday,
            c.position,
            c.company,
            c.tz,
            c.tg_username,
            c.email,
            c.preferred_channel,
            c.default_style,
            c.segment,
            c.notes,
            c.tg_chat_id,
            c.is_active,
            c.is_deleted,
            c.created_at,
            c.updated_at
        FROM public.events e
        JOIN public.contacts c ON c.id = e.contact_id
        WHERE e.id = :event_id
          AND e.is_deleted = false
          AND (c.is_deleted = false OR c.is_deleted IS NULL)
          AND (c.is_active = true OR c.is_active IS NULL)
        LIMIT 1;
        """
    )
    r = await session.execute(q, {"event_id": event_id})
    row = r.first()
    if not row:
        print(f"event_id={event_id}: not found")
        return

    (
        e_id,
        contact_id,
        holiday_id,
        e_date,
        channel,
        style,
        _status,
        first_name,
        last_name,
        middle_name,
        gender,
        birthday,
        position,
        company,
        tz,
        _tg_username,
        _email,
        preferred_channel,
        default_style,
        segment,
        notes,
        tg_chat_id,
        is_active,
        is_deleted,
        created_at,
        updated_at,
    ) = row

    q2 = text(
        """
        SELECT id, template_id, rendered_text, used_model, grammar_score
        FROM public.messages
        WHERE event_id = :event_id
          AND is_deleted = false
        ORDER BY id DESC
        LIMIT 1;
        """
    )
    r2 = await session.execute(q2, {"event_id": int(e_id)})
    existing_msg = r2.first()

    if existing_msg and not force:
        existing_rendered_text = str(existing_msg[2] or "")
        if has_unresolved_placeholders(existing_rendered_text):
            print(
                f"event_id={e_id}: message contains unresolved placeholders "
                f"(message_id={int(existing_msg[0])}), regenerating"
            )
            message_id = None
        else:
            message_id = int(existing_msg[0])
            print(f"event_id={e_id}: message already exists (message_id={message_id}), skipping generation")
    else:
        if existing_msg and force:
            print(f"event_id={e_id}: force enabled, regenerating message")
        message_id = None

    style_norm = (style or "business").strip().lower()
    channel_norm = (channel or "telegram").strip().lower()

    name = (first_name or "").strip() or "Коллега"
    full_name = " ".join(
        part for part in [last_name, first_name, middle_name] if part and str(part).strip()
    )
    age = calc_age_years(birthday, e_date)

    if holiday_id is None:
        category = "birthday"
        holiday_name = "днём рождения"
    else:
        category = "holiday"
        holiday_name = await fetch_holiday_name(session, int(holiday_id)) or "праздником"

    req = GenerateRequest(
        contact_id=int(contact_id),
        name=name,
        style=style_norm,
        channel=channel_norm,
        holiday_id=category,
        holiday_name=holiday_name,
        wishes=["счастья", "здоровья", "успехов"],
        full_name=full_name or name,
        gender=(gender or "").strip() or None,
        age=age,
        position=(position or "").strip() or None,
        company=(company or "").strip() or None,
        first_name=(first_name or "").strip() or None,
        last_name=(last_name or "").strip() or None,
        middle_name=(middle_name or "").strip() or None,
        birthday=birthday,
        tz=(tz or "").strip() or None,
        tg_username=(_tg_username or "").strip() or None,
        email=(_email or "").strip() or None,
        preferred_channel=(preferred_channel or "").strip() or None,
        default_style=(default_style or "").strip() or None,
        segment=(segment or "").strip() or None,
        notes=(notes or "").strip() or None,
        tg_chat_id=str(tg_chat_id).strip() if tg_chat_id is not None else None,
        is_active=is_active,
        is_deleted=is_deleted,
        created_at=created_at,
        updated_at=updated_at,
    )

    if message_id is None:
        svc = TextService(session)
        generation_started = perf_counter()
        try:
            res = await svc.generate(req)
            generation_duration_ms = int((perf_counter() - generation_started) * 1000)
        except Exception as exc:
            generation_duration_ms = int((perf_counter() - generation_started) * 1000)
            await try_update_generation_state(
                session,
                {
                    "event_id": int(e_id),
                    "generation_status": "failed",
                    "generation_error": str(exc),
                    "generation_duration_ms": generation_duration_ms,
                    "generation_cache_hit": False,
                    "generation_engine": "unknown",
                },
            )
            await session.commit()
            raise

        grammar_percent = to_percent(res.grammar_score)
        fallback_reason = (res.fallback_reason or "").strip() or None
        if res.used_model == "templates":
            engine = "template_fallback" if fallback_reason else "template"
        else:
            engine = "llm"

        upsert = text(
            """
            INSERT INTO public.messages (
                event_id,
                template_id,
                rendered_text,
                used_model,
                grammar_score,
                is_deleted,
                created_at
            )
            VALUES (
                :event_id,
                :template_id,
                :rendered_text,
                :used_model,
                :grammar_score,
                false,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (event_id) DO UPDATE
            SET template_id   = EXCLUDED.template_id,
                rendered_text = EXCLUDED.rendered_text,
                used_model    = EXCLUDED.used_model,
                grammar_score = EXCLUDED.grammar_score,
                is_deleted    = false,
                created_at    = CURRENT_TIMESTAMP
            RETURNING id;
            """
        )

        rr = await session.execute(
            upsert,
            {
                "event_id": int(e_id),
                "template_id": int(res.template_id) if res.template_id else None,
                "rendered_text": res.rendered_text,
                "used_model": res.used_model,
                "grammar_score": grammar_percent,
            },
        )
        message_id = int(rr.scalar_one())

        await try_update_generation_state(
            session,
            {
                "event_id": int(e_id),
                "generation_status": "success",
                "generation_error": fallback_reason,
                "generation_duration_ms": generation_duration_ms,
                "generation_cache_hit": bool(res.cache_hit),
                "generation_engine": engine,
            },
        )
        if fallback_reason:
            print(
                f"event_id={e_id}: created messages.id={message_id}, "
                f"used_model={res.used_model}, fallback_reason={fallback_reason}"
            )
        else:
            print(f"event_id={e_id}: created messages.id={message_id}, used_model={res.used_model}")

    upd = text(
        """
        UPDATE public.events
        SET status = 'partial', updated_at = CURRENT_TIMESTAMP
        WHERE id = :event_id
          AND status IN ('pending', 'retry');
        """
    )
    await session.execute(upd, {"event_id": int(e_id)})

    q_appr = text(
        """
        SELECT id, status
        FROM public.approval_queue
        WHERE event_id = :event_id
          AND is_deleted = false
        ORDER BY id DESC
        LIMIT 1;
        """
    )
    r_appr = await session.execute(q_appr, {"event_id": int(e_id)})
    existing_appr = r_appr.first()

    if existing_appr:
        print(f"event_id={e_id}: approval_queue already exists id={existing_appr[0]}")
    else:
        ins_appr = text(
            """
            INSERT INTO public.approval_queue (event_id, responsible_id, status, comment, is_deleted)
            VALUES (:event_id, :responsible_id, 'pending', NULL, false)
            RETURNING id;
            """
        )
        responsible_id = await pick_responsible_editor_id(session)
        rr_appr = await session.execute(
            ins_appr,
            {
                "event_id": int(e_id),
                "responsible_id": responsible_id,
            },
        )
        appr_id = rr_appr.scalar_one()

        if responsible_id is None:
            print(f"event_id={e_id}: created approval_queue.id={appr_id} without responsible_id")
        else:
            print(f"event_id={e_id}: created approval_queue.id={appr_id}, responsible_id={responsible_id}")

    await session.commit()
    print(f"event_id={e_id}: done. messages.id={message_id}")
    print("-" * 60)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-id", type=int, default=None, help="Process a single event_id")
    parser.add_argument("--today", action="store_true", help="Process all today events with pending/retry")
    parser.add_argument("--force", action="store_true", help="Regenerate even if message already exists")

    args = parser.parse_args()

    async with SessionMaker() as session:
        if args.event_id:
            await generate_one_event(session, args.event_id, force=args.force)
            return

        q = text(
            """
            SELECT id
            FROM public.events
            WHERE date = CURRENT_DATE
              AND status IN ('pending', 'retry')
              AND is_deleted = false
            ORDER BY id ASC;
            """
        )
        r = await session.execute(q)
        ids = [row[0] for row in r.fetchall()]

        if not ids:
            print("No today events with pending/retry status")
            return

        for eid in ids:
            try:
                await generate_one_event(session, int(eid), force=args.force)
            except Exception as e:
                await session.rollback()
                print(f"event_id={eid}: generation error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
