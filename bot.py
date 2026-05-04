import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from database import init_db, SessionLocal, InstagramAccount
from instagram_api import InstagramBot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8766717874:AAFy_4ZCjgOoCER8L54hwFPk9drLYBA1DBY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7740552653"))

(
    WAITING_USERNAME,
    WAITING_PASSWORD,
    WAITING_MEDIA_URL,
    WAITING_COMMENT_TEXT,
) = range(4)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_main_keyboard(is_admin_user: bool = False):
    buttons = [
        [InlineKeyboardButton("➕ Akkaunt qo'shish", callback_data="add_account")],
        [InlineKeyboardButton("📋 Akkauntlar ro'yxati", callback_data="list_accounts")],
        [InlineKeyboardButton("▶️ Reel ko'rish", callback_data="view_reel")],
        [InlineKeyboardButton("❤️ Like bosish", callback_data="like_media")],
        [InlineKeyboardButton("💬 Izoh qoldirish", callback_data="comment_media")],
    ]
    if is_admin_user:
        buttons.append([InlineKeyboardButton("👑 Admin panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    admin = is_admin(user.id)
    text = (
        f"👋 Salom, {user.first_name}!\n\n"
        "🤖 Instagram Bot ga xush kelibsiz.\n"
        "Quyidagi tugmalardan birini tanlang:"
    )
    await update.message.reply_text(text, reply_markup=get_main_keyboard(admin))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Yordam*\n\n"
        "/start — Botni ishga tushirish\n"
        "/accounts — Akkauntlar ro'yxati\n"
        "/addaccount — Yangi akkaunt qo'shish\n"
        "/cancel — Amalni bekor qilish\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Amal bekor qilindi.",
        reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
    )
    return ConversationHandler.END


# ── Akkaunt qo'shish ──────────────────────────────────────────────────────────

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.reply_text(
            "📝 Instagram foydalanuvchi nomini kiriting (username):"
        )
    else:
        await update.message.reply_text(
            "📝 Instagram foydalanuvchi nomini kiriting (username):"
        )
    return WAITING_USERNAME


async def add_account_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().lstrip("@")
    context.user_data["ig_username"] = username
    await update.message.reply_text(
        f"🔑 `{username}` uchun parolni kiriting:\n\n"
        "⚠️ Xabaringiz yuborilgandan so'ng o'chiriladi (xavfsizlik uchun)",
        parse_mode="Markdown",
    )
    return WAITING_PASSWORD


async def add_account_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    username = context.user_data.get("ig_username")

    try:
        await update.message.delete()
    except Exception:
        pass

    msg = await update.message.reply_text("⏳ Login qilinmoqda, iltimos kuting...")

    # Login ni async thread da bajarish (blocking call)
    loop = asyncio.get_event_loop()
    bot_ig = InstagramBot()

    def do_login():
        return bot_ig.login(username, password)

    success, result = await loop.run_in_executor(None, do_login)

    if success:
        db = SessionLocal()
        try:
            existing = db.query(InstagramAccount).filter(
                InstagramAccount.username == username
            ).first()
            if existing:
                existing.password = password
                existing.session_data = result
                existing.status = "active"
                existing.telegram_user_id = str(update.effective_user.id)
            else:
                account = InstagramAccount(
                    telegram_user_id=str(update.effective_user.id),
                    username=username,
                    password=password,
                    session_data=result,
                    status="active",
                )
                db.add(account)
            db.commit()
            await msg.edit_text(
                f"✅ `{username}` muvaffaqiyatli qo'shildi!",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
            )
        except Exception as e:
            logger.error(f"DB xatosi: {e}")
            await msg.edit_text(f"❌ Bazaga saqlashda xato: {e}")
        finally:
            db.close()
    else:
        await msg.edit_text(
            f"❌ Login muvaffaqiyatsiz:\n\n{result}\n\nQaytadan urinib ko'ring.",
            reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
        )

    bot_ig.close()
    context.user_data.clear()
    return ConversationHandler.END


# ── Akkauntlar ro'yxati ───────────────────────────────────────────────────────

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(update.effective_user.id)
    if query:
        await query.answer()

    db = SessionLocal()
    try:
        if is_admin(update.effective_user.id):
            accounts = db.query(InstagramAccount).all()
        else:
            accounts = db.query(InstagramAccount).filter(
                InstagramAccount.telegram_user_id == user_id
            ).all()

        if not accounts:
            text = "📭 Hech qanday akkaunt topilmadi."
        else:
            lines = ["📋 *Akkauntlar ro'yxati:*\n"]
            for acc in accounts:
                status_emoji = {
                    "active": "🟢",
                    "inactive": "⚫",
                    "login_required": "🔴",
                    "session_expired": "🟡",
                    "error": "❌",
                }.get(acc.status, "⚪")
                lines.append(f"{status_emoji} `{acc.username}` — {acc.status} (ID: {acc.id})")
            text = "\n".join(lines)

        send = query.message.reply_text if query else update.message.reply_text
        await send(text, parse_mode="Markdown")
    finally:
        db.close()


# ── Media amallar ─────────────────────────────────────────────────────────────

async def media_action_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    context.user_data["media_action"] = action

    action_text = {
        "view_reel": "▶️ Ko'rish",
        "like_media": "❤️ Like bosish",
        "comment_media": "💬 Izoh qoldirish",
    }.get(action, "Amal")

    await query.message.reply_text(
        f"🔗 {action_text} uchun Instagram post/reel URL manzilini yuboring:\n\n"
        "Masalan: `https://www.instagram.com/reel/ABC123/`",
        parse_mode="Markdown",
    )
    return WAITING_MEDIA_URL


async def media_action_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    action = context.user_data.get("media_action")
    user_id = str(update.effective_user.id)

    db = SessionLocal()
    try:
        if is_admin(update.effective_user.id):
            accounts = db.query(InstagramAccount).filter(
                InstagramAccount.status == "active"
            ).all()
        else:
            accounts = db.query(InstagramAccount).filter(
                InstagramAccount.telegram_user_id == user_id,
                InstagramAccount.status == "active",
            ).all()

        if not accounts:
            await update.message.reply_text(
                "❌ Faol akkaunt topilmadi. Avval akkaunt qo'shing.",
                reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
            )
            context.user_data.clear()
            return ConversationHandler.END

        account = accounts[0]
        account_id = account.id
    finally:
        db.close()

    context.user_data["media_url"] = url
    context.user_data["account_id"] = account_id

    if action == "comment_media":
        await update.message.reply_text("💬 Izoh matnini kiriting:")
        return WAITING_COMMENT_TEXT

    msg = await update.message.reply_text("⏳ Amal bajarilmoqda...")

    loop = asyncio.get_event_loop()

    def do_action():
        bot_ig = InstagramBot(account_id=account_id)
        try:
            ok, media_id = bot_ig.get_media_id_from_url(url)
            if not ok:
                return False, f"URL dan media ID olib bo'lmadi: {media_id}"
            if action == "view_reel":
                return bot_ig.view_reel(media_id)
            elif action == "like_media":
                return bot_ig.like_media(media_id)
            return False, "Noma'lum amal"
        finally:
            bot_ig.close()

    success, message = await loop.run_in_executor(None, do_action)
    emoji = "✅" if success else "❌"
    await msg.edit_text(
        f"{emoji} {message}",
        reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def media_action_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment_text = update.message.text.strip()
    url = context.user_data.get("media_url")
    account_id = context.user_data.get("account_id")

    msg = await update.message.reply_text("⏳ Izoh qo'shilmoqda...")

    loop = asyncio.get_event_loop()

    def do_comment():
        bot_ig = InstagramBot(account_id=account_id)
        try:
            ok, media_id = bot_ig.get_media_id_from_url(url)
            if not ok:
                return False, f"URL dan media ID olib bo'lmadi: {media_id}"
            return bot_ig.comment_media(media_id, comment_text)
        finally:
            bot_ig.close()

    success, message = await loop.run_in_executor(None, do_comment)
    emoji = "✅" if success else "❌"
    await msg.edit_text(
        f"{emoji} {message}",
        reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── Admin panel ───────────────────────────────────────────────────────────────

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update.effective_user.id):
        await query.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    await query.answer()

    db = SessionLocal()
    try:
        total = db.query(InstagramAccount).count()
        active = db.query(InstagramAccount).filter(
            InstagramAccount.status == "active"
        ).count()
    finally:
        db.close()

    text = (
        f"👑 *Admin Panel*\n\n"
        f"📊 Jami akkauntlar: `{total}`\n"
        f"🟢 Faol akkauntlar: `{active}`\n"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Barcha akkauntlar", callback_data="list_accounts")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="main_menu")],
    ])
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=buttons)


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🏠 Asosiy menyu:",
        reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
    )


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Tushunmadim. /start buyrug'ini yuboring.",
        reply_markup=get_main_keyboard(is_admin(update.effective_user.id)),
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Xato: {context.error}", exc_info=context.error)


def main():
    init_db()
    logger.info("Ma'lumotlar bazasi tayyor.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        # Conflict xatosini oldini olish uchun
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_error_handler(error_handler)

    add_account_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_account_start, pattern="^add_account$"),
            CommandHandler("addaccount", add_account_start),
        ],
        states={
            WAITING_USERNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_username)
            ],
            WAITING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_account_password)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    media_action_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                media_action_start,
                pattern="^(view_reel|like_media|comment_media)$"
            ),
        ],
        states={
            WAITING_MEDIA_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, media_action_url)
            ],
            WAITING_COMMENT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, media_action_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("accounts", list_accounts))
    app.add_handler(add_account_conv)
    app.add_handler(media_action_conv)
    app.add_handler(CallbackQueryHandler(list_accounts, pattern="^list_accounts$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    logger.info("Bot ishga tushdi...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # Eski xabarlarni o'tkazib yuborish
        close_loop=False,
    )


if __name__ == "__main__":
    main()
    
