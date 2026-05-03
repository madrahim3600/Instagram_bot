import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from database import SessionLocal, InstagramAccount, InstagramTask, init_db
from instagram_api import InstagramBot
from tasks import run_loader_task, start_task_processor

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN", "8766717874:AAFy_4ZCjgOoCER8L54hwFPk9drLYBA1DBY") # User provided token
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # Admin user ID, default to 0 if not set

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Form(StatesGroup):
    username = State()
    password = State()


class LoaderForm(StatesGroup):
    reel_url = State()
    comments = State()
    likes_enabled = State()
    views_enabled = State()


@dp.message_handler(commands=["start", "help"])
async def send_welcome(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return
    await message.reply("Assalomu alaykum! Instagram botiga xush kelibsiz. \n\n" \
                        "Mavjud buyruqlar:\n" \
                        "/add_account - Instagram akkaunt qo'shish\n" \
                        "/list_accounts - Akkauntlar ro'yxatini ko'rish\n" \
                        "/check_status - Akkauntlar holatini tekshirish\n" \
                        "/loader - Barcha akkauntlarni uyg'otish (Reels vazifasini bajarishga tayyorlash)\n" \
                        "/stats - Statistika ko'rish")


@dp.message_handler(commands=["add_account"])
async def add_account_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return
    await Form.username.set()
    await message.reply("Instagram username kiriting:")


@dp.message_handler(state=Form.username)
async def process_username(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["username"] = message.text
    await Form.next()
    await message.reply("Instagram parolni kiriting:")


@dp.message_handler(state=Form.password)
async def process_password(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        await state.finish()
        return

    async with state.proxy() as data:
        username = data["username"]
        password = message.text

    await message.reply(f"Akkauntga kirishga urinilmoqda: {username}...")

    ig_bot = InstagramBot()
    success, session_data = ig_bot.login(username, password)
    ig_bot.close()

    if success:
        db = SessionLocal()
        account = InstagramAccount(username=username, password=password, session_data=session_data, status="active")
        db.add(account)
        db.commit()
        db.close()
        await message.reply("Akkaunt muvaffaqiyatli qo'shildi va tizimga kirdi!")
    else:
        await message.reply(f"Akkauntga kirishda xatolik: {session_data}")

    await state.finish()


@dp.message_handler(commands=["list_accounts"])
async def list_accounts(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return

    db = SessionLocal()
    accounts = db.query(InstagramAccount).all()
    db.close()

    if not accounts:
        await message.reply("Hozirda hech qanday Instagram akkaunt qo'shilmagan.")
        return

    response = "*Instagram Akkauntlar Ro'yxati:*\n\n"
    for account in accounts:
        response += f"ID: `{account.id}`\n"
        response += f"Username: `{account.username}`\n"
        response += f"Status: `{account.status}`\n"
        response += f"Oxirgi tekshiruv: `{account.last_checked.strftime('%Y-%m-%d %H:%M:%S')}`\n"
        response += "--------------------\n"
    await message.reply(response, parse_mode="Markdown")


@dp.message_handler(commands=["check_status"])
async def check_accounts_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return

    await message.reply("Akkauntlar holati tekshirilmoqda... Bu biroz vaqt olishi mumkin.")

    db = SessionLocal()
    accounts = db.query(InstagramAccount).filter(InstagramAccount.status != "banned").all()
    db.close()

    active_count = 0
    inactive_accounts = []

    for account in accounts:
        ig_bot = InstagramBot(account_id=account.id)
        status, msg = ig_bot.check_account_status()
        ig_bot.close()

        if status == "active":
            active_count += 1
        else:
            inactive_accounts.append(f"Username: `{account.username}` (ID: `{account.id}`), Holat: `{status}`, Sabab: {msg}")

    response = f"*Akkauntlar holati tekshiruvi yakunlandi:*\n\n"
    response += f"Ishlayotgan akkauntlar soni: `{active_count}`\n\n"

    if inactive_accounts:
        response += "*Ishlamayotgan akkauntlar:*\n"
        for acc_info in inactive_accounts:
            response += f"- {acc_info}\n"
        response += "\nIshlamayotgan akkauntni o'chirish uchun /delete_account <ID> buyrug'idan foydalaning."
    else:
        response += "Barcha akkauntlar faol!\n"

    await message.reply(response, parse_mode="Markdown")


@dp.message_handler(commands=["delete_account"])
async def delete_account(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return

    try:
        account_id = int(message.get_args())
    except ValueError:
        await message.reply("Iltimos, akkaunt ID'sini to'g'ri kiriting. Misol: `/delete_account 123`", parse_mode="Markdown")
        return

    db = SessionLocal()
    account = db.query(InstagramAccount).filter(InstagramAccount.id == account_id).first()

    if account:
        db.delete(account)
        db.commit()
        db.close()
        await message.reply(f"Akkaunt (ID: `{account_id}`, Username: `{account.username}`) muvaffaqiyatli o'chirildi.", parse_mode="Markdown")
    else:
        db.close()
        await message.reply(f"ID'si `{account_id}` bo'lgan akkaunt topilmadi.", parse_mode="Markdown")


@dp.message_handler(commands=["loader"])
async def loader_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return
    await LoaderForm.reel_url.set()
    await message.reply("Reels URL manzilini kiriting:")


@dp.message_handler(state=LoaderForm.reel_url)
async def process_reel_url(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["reel_url"] = message.text
    await LoaderForm.next()
    await message.reply("Izohlarni vergul bilan ajratib kiriting (masalan: Ajoyib, Zo'r, Super). Agar izoh bo'lmasa, 'yoq' deb yozing:")


@dp.message_handler(state=LoaderForm.comments)
async def process_comments(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        comments_raw = message.text
        data["comments"] = [c.strip() for c in comments_raw.split(',')] if comments_raw.lower() != 'yoq' else []
    await LoaderForm.next()
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("Ha", callback_data="likes_yes"),
                 InlineKeyboardButton("Yo'q", callback_data="likes_no"))
    await message.reply("Layk bosishni yoqish kerakmi?", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('likes_'), state=LoaderForm.likes_enabled)
async def process_likes_enabled(callback_query: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        data["likes_enabled"] = True if callback_query.data == "likes_yes" else False
    await bot.answer_callback_query(callback_query.id)
    await LoaderForm.next()
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("Ha", callback_data="views_yes"),
                 InlineKeyboardButton("Yo'q", callback_data="views_no"))
    await bot.send_message(callback_query.from_user.id, "Ko'rishlarni yoqish kerakmi?", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith('views_'), state=LoaderForm.views_enabled)
async def process_views_enabled(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID:
        await bot.send_message(callback_query.from_user.id, "Sizga botdan foydalanishga ruxsat berilmagan.")
        await state.finish()
        return

    async with state.proxy() as data:
        data["views_enabled"] = True if callback_query.data == "views_yes" else False
        reel_url = data["reel_url"]
        comments = data["comments"]
        likes_enabled = data["likes_enabled"]
        views_enabled = data["views_enabled"]

    await bot.answer_callback_query(callback_query.id, text="Vazifa yaratilmoqda...")
    await bot.send_message(callback_query.from_user.id, "Vazifa yaratilmoqda. Bu biroz vaqt olishi mumkin.")

    result_message = await run_loader_task(reel_url, comments, likes_enabled, views_enabled, ADMIN_ID)
    await bot.send_message(callback_query.from_user.id, result_message)

    await state.finish()


@dp.message_handler(commands=["stats"])
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("Sizga botdan foydalanishga ruxsat berilmagan.")
        return

    db = SessionLocal()
    total_accounts = db.query(InstagramAccount).count()
    active_accounts = db.query(InstagramAccount).filter(InstagramAccount.status == "active").count()
    total_tasks = db.query(InstagramTask).count()
    completed_tasks = db.query(InstagramTask).filter(InstagramTask.status == "completed").count()
    pending_tasks = db.query(InstagramTask).filter(InstagramTask.status == "pending").count()
    in_progress_tasks = db.query(InstagramTask).filter(InstagramTask.status == "in_progress").count()

    response = "*Statistika:*\n\n"
    response += f"Umumiy akkauntlar soni: `{total_accounts}`\n"
    response += f"Faol akkauntlar soni: `{active_accounts}`\n\n"
    response += f"Umumiy vazifalar soni: `{total_tasks}`\n"
    response += f"Bajarilgan vazifalar: `{completed_tasks}`\n"
    response += f"Kutilayotgan vazifalar: `{pending_tasks}`\n"
    response += f"Bajarilayotgan vazifalar: `{in_progress_tasks}`\n"

    db.close()
    await message.reply(response, parse_mode="Markdown")


async def main():
    init_db()
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write(f"BOT_TOKEN={API_TOKEN}\n")
            f.write(f"ADMIN_ID={ADMIN_ID}\n")
            f.write("INSTAGRAM_USERNAME=\n")
            f.write("INSTAGRAM_PASSWORD=\n")

    if ADMIN_ID == 0:
        print("WARNING: ADMIN_ID is not set in .env. Please set your Telegram User ID as ADMIN_ID in the .env file.")
        print("Example: ADMIN_ID=123456789")

    asyncio.create_task(start_task_processor())
    await dp.start_polling()


if __name__ == "__main__":
    asyncio.run(main())
