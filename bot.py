import asyncio
import logging
from datetime import datetime, date, timedelta
from aiogram.enums import ParseMode
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database
from config import BOT_TOKEN, ADMIN_IDS


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


bot = Bot(BOT_TOKEN)
bot.parse_mode = ParseMode.HTML
dp = Dispatcher(storage=MemoryStorage())

RU_WEEKDAY = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


def get_next_workdays(count: int = 6):
    days = []
    d = datetime.now().date()
    while len(days) < count:
        if d.weekday() != 6:  # 6 дней в неделю: пропускаем воскресенье
            days.append(d)
        d = d + timedelta(days=1)
    return days


def build_days_keyboard(days):
    kb = InlineKeyboardBuilder()
    for d in days:
        label = f"{RU_WEEKDAY[d.weekday()]} {d.strftime('%d.%m')}"
        kb.button(text=label, callback_data=f"bookday:{d.strftime('%Y-%m-%d')}")
    kb.adjust(3)
    return kb.as_markup()


def build_times_keyboard(date_yyyy_mm_dd: str, booked_times):
    kb = InlineKeyboardBuilder()
    for hour in range(10, 18):  # 10:00 .. 17:00
        t = f"{hour:02d}:00"
        if t in booked_times:
            kb.button(text=f"❌ {t}", callback_data=f"bookbusy:{t}")
        else:
            kb.button(text=t, callback_data=f"booktime:{t}")

    kb.button(text="⬅ К выбору дня", callback_data="book_back_days")
    kb.adjust(4, 1)
    return kb.as_markup()


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


class BookingStates(StatesGroup):
    waiting_for_day = State()
    waiting_for_time = State()
    waiting_for_name = State()
    waiting_for_phone = State()


class AddServiceStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_duration = State()


class UpdatePriceStates(StatesGroup):
    waiting_for_service_id = State()
    waiting_for_new_price = State()


class UpdateDurationStates(StatesGroup):
    waiting_for_service_id = State()
    waiting_for_new_duration = State()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="Прайс-лист 💅"),
            KeyboardButton(text="Записаться 🗓"),
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [
            KeyboardButton(text="📋 Услуги"),
            KeyboardButton(text="➕ Добавить услугу"),
        ],
        [
            KeyboardButton(text="💰 Обновить цену"),
            KeyboardButton(text="⏱ Обновить время"),
        ],
        [
            KeyboardButton(text="📆 Записи"),
            KeyboardButton(text="⬅ Назад в главное меню"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "Здравствуйте! 👋\n\n"
        "Я бот салона красоты.\n\n"
        "Вы можете:\n"
        "• посмотреть прайс-лист по услугам;\n"
        "• записаться на выбранную услугу.\n\n"
        "Выберите нужный раздел в меню ниже."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет доступа к админ-панели.")
        return

    text = (
        "Админ-панель салона 💼\n\n"
        "Вы можете управлять услугами и смотреть записи клиентов.\n"
        "Выберите действие на клавиатуре."
    )
    await message.answer(text, reply_markup=admin_menu_keyboard())


# ---------- User: price list ----------

@dp.message(F.text.startswith("Прайс-лист"))
async def show_price_categories(message: Message):
    categories = database.get_categories()
    if not categories:
        await message.answer(
            "Прайс-лист пока пуст. Обратитесь к администратору салона."
        )
        return

    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=cat, callback_data=f"category:{cat}")
    kb.adjust(1)

    await message.answer(
        "Выберите категорию услуг:", reply_markup=kb.as_markup()
    )


@dp.callback_query(F.data.startswith("category:"))
async def show_services_in_category(call: CallbackQuery):
    category = call.data.split(":", maxsplit=1)[1]
    services = database.get_services_by_category(category)
    if not services:
        await call.message.edit_text(
            f"В категории {category} пока нет услуг."
        )
        await call.answer()
        return

    kb = InlineKeyboardBuilder()
    text_lines = [f"Категория: {category}\n"]
    for s in services:
        line = (
            f"#{s['id']} {s['name']}\n"
            f"{s['description'] or 'Без описания'}\n"
            f"Цена: {s['price']:.0f} ₽, "
            f"время: {s['duration_minutes']} мин\n"
        )
        text_lines.append(line)
        kb.button(
            text=f"{s['name']} ({int(s['price'])} ₽)",
            callback_data=f"service:{s['id']}",
        )

    kb.adjust(1)
    await call.message.edit_text(
        "\n".join(text_lines), reply_markup=kb.as_markup()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("service:"))
async def show_service_details(call: CallbackQuery, state: FSMContext):
    try:
        service_id = int(call.data.split(":", maxsplit=1)[1])
    except ValueError:
        await call.answer("Ошибка в данных услуги.", show_alert=True)
        return

    service = database.get_service(service_id)
    if not service:
        await call.answer("Услуга не найдена.", show_alert=True)
        return

    text = (
        f"{service['name']}\n\n"
        f"{service['description'] or 'Без описания'}\n\n"
        f"Категория: {service['category']}\n"
        f"Цена: {service['price']:.0f} ₽\n"
        f"Время выполнения: {service['duration_minutes']} мин"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="Записаться на услугу 🗓", callback_data=f"book:{service_id}")
    kb.button(text="⬅ К списку категорий", callback_data="back_to_categories")
    kb.adjust(1)

    await call.message.edit_text(text, reply_markup=kb.as_markup())
    await call.answer()


@dp.callback_query(F.data == "back_to_categories")
async def back_to_categories(call: CallbackQuery):
    categories = database.get_categories()
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=cat, callback_data=f"category:{cat}")
    kb.adjust(1)
    await call.message.edit_text(
        "Выберите категорию услуг:", reply_markup=kb.as_markup()
    )
    await call.answer()


# ---------- User: booking ----------

@dp.message(F.text.startswith("Записаться"))
async def start_booking_from_menu(message: Message):
    categories = database.get_categories()
    if not categories:
        await message.answer(
            "Пока нет доступных услуг для записи. Обратитесь к администратору."
        )
        return

    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=cat, callback_data=f"category:{cat}")
    kb.adjust(1)

    await message.answer(
        "Выберите категорию и затем услугу, на которую хотите записаться.",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data.startswith("book:"))
async def book_selected_service(call: CallbackQuery, state: FSMContext):
    try:
        service_id = int(call.data.split(":", maxsplit=1)[1])
    except ValueError:
        await call.answer("Ошибка в данных услуги.", show_alert=True)
        return

    service = database.get_service(service_id)
    if not service:
        await call.answer("Услуга не найдена.", show_alert=True)
        return

    await state.update_data(service_id=service_id)
    await state.set_state(BookingStates.waiting_for_day)

    days = get_next_workdays(6)
    await call.message.edit_text(
        f"Вы выбрали услугу {service['name']}.\n\n"
        "Выберите день для записи (6 дней в неделю):",
        reply_markup=build_days_keyboard(days),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("bookday:"))
async def booking_pick_day(call: CallbackQuery, state: FSMContext):
    date_str = call.data.split(":", maxsplit=1)[1]
    await state.update_data(date_str=date_str)
    await state.set_state(BookingStates.waiting_for_time)

    booked = database.get_booked_times_for_date(date_str)
    pretty_day = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    await call.message.edit_text(
        f"Выбран день: {pretty_day}\n\nВыберите время:",
        reply_markup=build_times_keyboard(date_str, booked),
    )
    await call.answer()


@dp.callback_query(F.data == "book_back_days")
async def booking_back_to_days(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    service_id = data.get("service_id")
    service = database.get_service(service_id) if service_id else None

    await state.set_state(BookingStates.waiting_for_day)
    days = get_next_workdays(6)
    await call.message.edit_text(
        f"Вы выбрали услугу {service['name'] if service else ''}.\n\n"
        "Выберите день для записи (6 дней в неделю):",
        reply_markup=build_days_keyboard(days),
    )
    await call.answer()


@dp.callback_query(F.data.startswith("bookbusy:"))
async def booking_busy_time(call: CallbackQuery):
    time_str = call.data.split(":", maxsplit=1)[1]
    await call.answer(f"{time_str} уже занято.", show_alert=True)


@dp.callback_query(F.data.startswith("booktime:"))
async def booking_pick_time(call: CallbackQuery, state: FSMContext):
    time_str = call.data.split(":", maxsplit=1)[1]
    data = await state.get_data()
    date_str = data.get("date_str")
    if not date_str:
        await call.answer("Сначала выберите день.", show_alert=True)
        return

    booked = database.get_booked_times_for_date(date_str)
    if time_str in booked:
        await call.answer("Это время уже занято. Выберите другое.", show_alert=True)
        return

    await state.update_data(datetime_str=f"{date_str} {time_str}")
    await state.set_state(BookingStates.waiting_for_name)

    pretty_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").strftime(
        "%d.%m.%Y %H:%M"
    )
    await call.message.edit_text(
        f"Запись на {pretty_dt}.\n\nВведите, пожалуйста, ваше имя и фамилию."
    )
    await call.answer()


@dp.message(BookingStates.waiting_for_name)
async def booking_get_name(message: Message, state: FSMContext):
    full_name = message.text.strip()
    if len(full_name) < 2:
        await message.answer("Имя слишком короткое. Пожалуйста, введите ещё раз.")
        return

    await state.update_data(full_name=full_name)
    await state.set_state(BookingStates.waiting_for_phone)
    await message.answer(
        "Теперь введите, пожалуйста, ваш номер телефона для связи."
    )


@dp.message(BookingStates.waiting_for_phone)
async def booking_get_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if len(phone) < 5:
        await message.answer("Похоже, номер слишком короткий. Введите ещё раз.")
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    service = database.get_service(service_id) if service_id else None

    if not service:
        await message.answer(
            "Произошла ошибка при выборе услуги. Попробуйте записаться ещё раз."
        )
        await state.clear()
        return

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    booking_id = database.add_booking(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=data["full_name"],
        phone=phone,
        service_id=service_id,
        dt=data["datetime_str"],
        created_at=created_at,
    )

    await state.clear()

    confirm_text = (
        "Спасибо! Ваша заявка на запись отправлена администратору. ✅\n\n"
        f"Номер заявки: #{booking_id}\n"
        f"Услуга: {service['name']}\n"
        f"Дата и время: {data['datetime_str']}\n"
        f"Имя: {data['full_name']}\n"
        f"Телефон: {phone}\n\n"
        "Администратор свяжется с вами для подтверждения времени."
    )
    await message.answer(confirm_text, reply_markup=main_menu_keyboard())

    notify_text = (
        f"Новая заявка #{booking_id} 📩\n\n"
        f"Услуга: {service['name']} ({service['category']})\n"
        f"Дата и время: {data['datetime_str']}\n"
        f"Клиент: {data['full_name']}\n"
        f"Телефон: {phone}\n"
        f"Telegram: @{message.from_user.username or 'нет'} "
        f"(id: {message.from_user.id})"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notify_text)
        except Exception:
            logging.exception("Не удалось отправить уведомление админу %s", admin_id)


# ---------- Admin: services ----------

@dp.message(F.text == "📋 Услуги")
async def admin_list_services(message: Message):
    if not is_admin(message.from_user.id):
        return

    services = database.get_all_services()
    if not services:
        await message.answer("Список услуг пуст. Добавьте первую услугу.")
        return

    lines = ["Текущий прайс-лист:\n"]
    for s in services:
        lines.append(
            f"#{s['id']} [{s['category']}]\n"
            f"{s['name']}\n"
            f"{s['description'] or 'Без описания'}\n"
            f"Цена: {s['price']:.0f} ₽, время: {s['duration_minutes']} мин\n"
        )
    await message.answer("\n".join(lines))


@dp.message(F.text == "➕ Добавить услугу")
async def admin_add_service_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AddServiceStates.waiting_for_category)
    await message.answer(
        "Добавление новой услуги.\n\n"
        "Введите категорию (например: Маникюр, Педикюр, Уход за кожей)."
    )


@dp.message(AddServiceStates.waiting_for_category)
async def admin_add_service_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddServiceStates.waiting_for_name)
    await message.answer("Введите название услуги.")


@dp.message(AddServiceStates.waiting_for_name)
async def admin_add_service_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddServiceStates.waiting_for_description)
    await message.answer(
        "Введите описание услуги (или '-' если без описания)."
    )


@dp.message(AddServiceStates.waiting_for_description)
async def admin_add_service_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    await state.update_data(description=desc)
    await state.set_state(AddServiceStates.waiting_for_price)
    await message.answer(
        "Введите цену услуги (только число, без валюты)."
    )


@dp.message(AddServiceStates.waiting_for_price)
async def admin_add_service_price(message: Message, state: FSMContext):
    text = message.text.replace(",", ".").strip()
    try:
        price = float(text)
    except ValueError:
        await message.answer("Не удалось распознать цену. Введите число, например 1500.")
        return

    await state.update_data(price=price)
    await state.set_state(AddServiceStates.waiting_for_duration)
    await message.answer(
        "Введите время выполнения в минутах (например, 60)."
    )


@dp.message(AddServiceStates.waiting_for_duration)
async def admin_add_service_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.answer(
            "Не удалось распознать время. Введите целое число минут, например 60."
        )
        return

    data = await state.get_data()
    service_id = database.add_service(
        category=data["category"],
        name=data["name"],
        description=data["description"],
        price=data["price"],
        duration_minutes=duration,
    )
    await state.clear()

    await message.answer(
        "Услуга успешно добавлена ✅\n\n"
        f"ID: #{service_id}\n"
        f"Категория: {data['category']}\n"
        f"Название: {data['name']}\n"
        f"Цена: {data['price']:.0f} ₽\n"
        f"Время: {duration} мин"
    )


@dp.message(F.text == "💰 Обновить цену")
async def admin_update_price_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    services = database.get_all_services()
    if not services:
        await message.answer("Список услуг пуст.")
        return

    lines = ["Выберите услугу для изменения цены.\n"]
    for s in services:
        lines.append(
            f"#{s['id']} [{s['category']}] {s['name']} — {s['price']:.0f} ₽"
        )
    await message.answer(
        "\n".join(lines) + "\n\nОтправьте ID услуги, у которой нужно изменить цену."
    )
    await state.set_state(UpdatePriceStates.waiting_for_service_id)


@dp.message(UpdatePriceStates.waiting_for_service_id)
async def admin_update_price_get_id(message: Message, state: FSMContext):
    try:
        service_id = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно ввести числовой ID услуги.")
        return

    service = database.get_service(service_id)
    if not service:
        await message.answer("Услуга с таким ID не найдена. Попробуйте ещё раз.")
        return

    await state.update_data(service_id=service_id)
    await state.set_state(UpdatePriceStates.waiting_for_new_price)
    await message.answer(
        f"Текущая цена услуги {service['name']}: {service['price']:.0f} ₽.\n"
        "Введите новую цену (только число)."
    )


@dp.message(UpdatePriceStates.waiting_for_new_price)
async def admin_update_price_set_new(message: Message, state: FSMContext):
    text = message.text.replace(",", ".").strip()
    try:
        price = float(text)
    except ValueError:
        await message.answer("Не удалось распознать цену. Введите число, например 1700.")
        return

    data = await state.get_data()
    service_id = data["service_id"]
    database.update_service_price(service_id, price)

    service = database.get_service(service_id)
    await state.clear()

    await message.answer(
        "Цена успешно обновлена ✅\n\n"
        f"Услуга: {service['name']}\n"
        f"Новая цена: {service['price']:.0f} ₽"
    )




@dp.message(F.text == "⏱ Обновить время")
async def admin_update_duration_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    services = database.get_all_services()
    if not services:
        await message.answer("Список услуг пуст.")
        return

    lines = ["Выберите услугу для изменения времени.\n"]
    for s in services:
        lines.append(
            f"#{s['id']} [{s['category']}] {s['name']} — {s['duration_minutes']} мин"
        )
    await message.answer(
        "\n".join(lines) + "\n\nОтправьте ID услуги, у которой нужно изменить время."
    )
    await state.set_state(UpdateDurationStates.waiting_for_service_id)


@dp.message(UpdateDurationStates.waiting_for_service_id)
async def admin_update_duration_get_id(message: Message, state: FSMContext):
    try:
        service_id = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно ввести числовой ID услуги.")
        return

    service = database.get_service(service_id)
    if not service:
        await message.answer("Услуга с таким ID не найдена. Попробуйте ещё раз.")
        return

    await state.update_data(service_id=service_id)
    await state.set_state(UpdateDurationStates.waiting_for_new_duration)
    await message.answer(
        f"Текущее время услуги {service['name']}: {service['duration_minutes']} мин.\n"
        "Введите новое время в минутах (целое число)."
    )


@dp.message(UpdateDurationStates.waiting_for_new_duration)
async def admin_update_duration_set_new(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
    except ValueError:
        await message.answer(
            "Не удалось распознать время. Введите целое число минут, например 90."
        )
        return

    data = await state.get_data()
    service_id = data["service_id"]
    database.update_service_duration(service_id, duration)

    service = database.get_service(service_id)
    await state.clear()

    await message.answer(
        "Время услуги успешно обновлено ✅\n\n"
        f"Услуга: {service['name']}\n"
        f"Новое время: {service['duration_minutes']} мин"
    )


@dp.message(F.text == "📆 Записи")
async def admin_show_bookings(message: Message):
    if not is_admin(message.from_user.id):
        return

    bookings = database.get_last_bookings(limit=20)
    if not bookings:
        await message.answer("Пока нет заявок на запись.")
        return

    lines = ["Последние заявки клиентов:\n"]
    for b in bookings:
        lines.append(
            f"#{b['id']} — {b['created_at']}\n"
            f"Услуга: {b['service_name']} ({b['service_category']})\n"
            f"Дата и время: {b['datetime']}\n"
            f"Клиент: {b['full_name']} — {b['phone']}\n"
            f"Telegram: @{b['username'] or 'нет'} (id: {b['user_id']})\n"
            f"Статус: {b['status']}\n"
        )

    await message.answer("\n".join(lines))


@dp.message(F.text == "⬅ Назад в главное меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await cmd_start(message)


async def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PASTE_"):
        raise RuntimeError(
            "Сначала укажите корректный BOT_TOKEN в файле config.py."
        )

    database.init_db()
    logging.info("База данных инициализирована.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

