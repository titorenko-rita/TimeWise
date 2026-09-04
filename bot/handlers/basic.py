from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import settings
from keyboards.panels import panel_by_role
from roles import UserRole, resolve_role


router = Router(name="basic_handlers")

HELP_TEXT = (
    "<b>TimeWise</b> — бот для автоматизации поздравлений и уведомлений.\n\n"
    "Доступные команды:\n"
    "/start — приветственное сообщение и быстрый доступ к панели задач\n"
    "/help — подсказка по функциям и ролям\n"
    "/menu — открыть вашу панель ещё раз\n"
    "/about — кратко о проекте и ссылках\n"
)

def _panel_by_role(role: UserRole):
    return panel_by_role(role)


@router.message(CommandStart())
async def start(message: Message, role: UserRole | None = None) -> None:
    user = message.from_user
    if user is None:
        return

    if role is None:
        role = resolve_role(user.id, settings.admin_ids)
    greeting = (
        "👋 <b>TimeWise</b> приветствует вас!\n"
        "Мы напоминаем о днях рождения, формируем поздравления и следим за качеством рассылок.\n\n"
    )

    if role == UserRole.ADMIN:
        greeting += (
            "Вы отмечены как <b>администратор</b>. "
            "Используйте панель ниже, чтобы управлять контактами, шаблонами и мониторингом."
        )
    elif role == UserRole.EDITOR:
        greeting += (
            "Ваша роль — <b>редактор</b>. "
            "Вы можете работать с контактами и контентом (шаблоны/согласования)."
        )
    else:
        greeting += (
            "Ваша роль — <b>наблюдатель</b>. "
            "Доступен только просмотр отчётов/статистики и списков событий/сообщений."
        )

    await message.answer(greeting, reply_markup=_panel_by_role(role))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP_TEXT, disable_web_page_preview=True)


@router.message(Command("menu"))
async def menu_command(message: Message, role: UserRole | None = None) -> None:
    user = message.from_user
    if user is None:
        return

    if role is None:
        role = resolve_role(user.id, settings.admin_ids)
    await message.answer("Меню обновлено 👇", reply_markup=_panel_by_role(role))


@router.message(Command("about"))
async def about_command(message: Message) -> None:
    text = (
        "«TimeWise» — интеллектуальный планировщик поздравлений и уведомлений.\n"
        "Бот объединяет планировщик событий, генератор текстов и систему мониторинга.\n"
        "Подробнее о целях и архитектуре см. в ТЗ или спросите разработчиков."
    )
    await message.answer(text)


