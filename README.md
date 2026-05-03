# Instagram Bot

Bu bot Instagram akkauntlarini boshqarish va avtomatlashtirish uchun mo'ljallangan Telegram botidir. Bot faqat admin tomonidan boshqariladi va quyidagi funksiyalarni o'z ichiga oladi:

- Instagram akkauntlarini qo'shish.
- Akkauntlarning holatini tekshirish.
- Akkauntlarni o'chirish.
- Reels ko'rish, layk bosish va komment yozish vazifalarini avtomatlashtirish.
- Vazifalar va akkauntlar bo'yicha statistika.

## Texnologiyalar

- **Python**
- **aiogram**: Telegram bot API bilan ishlash uchun.
- **instagrapi**: Instagram API bilan ishlash uchun.
- **SQLAlchemy**: Ma'lumotlar bazasi (SQLite) bilan ishlash uchun.
- **python-dotenv**: Atrof-muhit o'zgaruvchilarini boshqarish uchun.
- **Docker**: Loyihani oson joylashtirish uchun.

## O'rnatish va Ishga Tushirish

### 1. Talablar

- Python 3.9+.
- Docker (agar Docker orqali ishga tushirmoqchi bo'lsangiz).
- Telegram Bot Token (BotFather orqali olingan).
- Sizning Telegram User ID'ingiz (admin sifatida).

### 2. Loyihani klonlash

```bash
git clone https://github.com/YOUR_USERNAME/instagram_bot.git # Bu yerga o'zingizning repo manzilingizni qo'ying
cd instagram_bot
```

### 3. `.env` faylini sozlash

Loyihaning asosiy katalogida `.env` nomli fayl yarating va quyidagilarni qo'shing:

```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_ID=YOUR_TELEGRAM_USER_ID
```

- `YOUR_TELEGRAM_BOT_TOKEN`: BotFather'dan olgan bot tokeningizni kiriting.
- `YOUR_TELEGRAM_USER_ID`: Sizning Telegram ID'ingiz. Bot faqat shu ID'ga ega foydalanuvchi tomonidan boshqariladi. O'zingizning ID'ingizni bilish uchun Telegramda `@userinfobot` ga yozishingiz mumkin.

### 4. Ma'lumotlar bazasini initsializatsiya qilish

```bash
python3 init_db.py
```

Bu `sql_app.db` nomli SQLite ma'lumotlar bazasini yaratadi.

### 5. Botni ishga tushirish (Docker orqali)

Docker yordamida botni ishga tushirish tavsiya etiladi:

```bash
docker build -t instagram_bot .
docker run -d --name instagram_bot_instance --restart always -v $(pwd)/sql_app.db:/app/sql_app.db -v $(pwd)/.env:/app/.env instagram_bot
```

- `-v $(pwd)/sql_app.db:/app/sql_app.db`: Ma'lumotlar bazasini saqlash uchun.
- `-v $(pwd)/.env:/app/.env`: `.env` faylini konteynerga ulash uchun.

### 6. Botni ishga tushirish (Python orqali)

Agar Docker ishlatmasangiz:

```bash
pip install -r requirements.txt
python3 bot.py
```

## Bot Buyruqlari

Botga `/start` yoki `/help` buyrug'ini yuborib, mavjud buyruqlar ro'yxatini olishingiz mumkin.

- `/add_account`: Instagram akkauntini qo'shish. Bot sizdan username va parolni so'raydi.
- `/list_accounts`: Qo'shilgan barcha Instagram akkauntlari ro'yxatini ko'rish.
- `/check_status`: Barcha akkauntlarning holatini tekshirish va ishlamayotganlarini ko'rsatish.
- `/delete_account <ID>`: Berilgan ID bo'yicha akkauntni o'chirish.
- `/loader`: Instagram Reels vazifasini boshlash. Bot sizdan Reels URL, kommentlar (vergul bilan ajratilgan), layk va ko'rishlarni yoqish/o'chirishni so'raydi.
- `/stats`: Botning umumiy statistikasi (akkauntlar soni, vazifalar holati).

## Muhim Eslatmalar

- **Xavfsizlik**: Instagram akkauntlaringizning login va parollari ma'lumotlar bazasida saqlanadi. Ma'lumotlar bazasi faylini (`sql_app.db`) xavfsiz joyda saqlang.
- **Instagram API cheklovlari**: Instagram API'dan foydalanishda cheklovlar mavjud. Haddan tashqari ko'p so'rovlar yuborish akkauntlarning bloklanishiga olib kelishi mumkin. `instagrapi` kutubxonasi bu cheklovlarni hisobga oladi, lekin ehtiyot bo'lish tavsiya etiladi.
- **Sessionlar**: Bot akkauntlarning session ma'lumotlarini saqlaydi, bu har safar qayta login qilishni oldini oladi. Agar session eskirsa, bot avtomatik ravishda qayta login qilishga urinadi yoki sizdan qayta qo'shishni so'raydi.

## Muallif

Manus AI
