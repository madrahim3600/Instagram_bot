import json
import os
import time
import random
import logging
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired,
    BadPassword,
    ChallengeRequired,
    TwoFactorRequired,
    MediaNotFound,
    ClientError,
)
from database import SessionLocal, InstagramAccount, TaskLog

logger = logging.getLogger(__name__)

# Real Android qurilmalar (Instagram ban qilmasligi uchun)
DEVICES = [
    {
        "app_version": "269.0.0.18.75",
        "android_version": 26,
        "android_release": "8.0.0",
        "dpi": "480dpi",
        "resolution": "1080x1920",
        "manufacturer": "OnePlus",
        "device": "ONEPLUS A3003",
        "model": "OnePlus3",
        "cpu": "qcom",
        "version_code": "314665256",
    },
    {
        "app_version": "269.0.0.18.75",
        "android_version": 28,
        "android_release": "9.0",
        "dpi": "560dpi",
        "resolution": "1440x2960",
        "manufacturer": "samsung",
        "device": "SM-G965F",
        "model": "star2qltecs",
        "cpu": "samsungexynos9810",
        "version_code": "314665256",
    },
    {
        "app_version": "269.0.0.18.75",
        "android_version": 29,
        "android_release": "10.0",
        "dpi": "420dpi",
        "resolution": "1080x2340",
        "manufacturer": "xiaomi",
        "device": "Mi 9",
        "model": "cepheus",
        "cpu": "qcom",
        "version_code": "314665256",
    },
]


def build_client() -> Client:
    """Tasodifiy real qurilma sozlamalari bilan Client yaratish."""
    cl = Client()
    cl.delay_range = [2, 5]
    device = random.choice(DEVICES)
    cl.set_device(device)
    cl.set_user_agent(
        f"Instagram {device['app_version']} Android "
        f"({device['android_version']}/{device['android_release']}; "
        f"{device['dpi']}; {device['resolution']}; "
        f"{device['manufacturer']}; {device['model']}; "
        f"{device['device']}; {device['cpu']}; en_US; {device['version_code']})"
    )
    return cl


class InstagramBot:
    def __init__(self, account_id: int = None):
        self.cl = build_client()
        self.db = SessionLocal()
        self.account = None

        if account_id:
            self.account = (
                self.db.query(InstagramAccount)
                .filter(InstagramAccount.id == account_id)
                .first()
            )
            if self.account and self.account.session_data:
                try:
                    settings = json.loads(self.account.session_data)
                    self.cl.set_settings(settings)
                    self.cl.get_timeline_feed()
                    self.account.status = "active"
                    self.db.commit()
                    logger.info(f"Session yuklandi: {self.account.username}")
                except LoginRequired:
                    logger.warning(f"Session eskirgan: {self.account.username}")
                    self._relogin()
                except Exception as e:
                    logger.error(f"Session xatosi ({self.account.username}): {e}")
                    self._relogin()

    def _relogin(self):
        """Session eskirganda qayta login qilish."""
        if not self.account:
            return False
        try:
            old_settings = json.loads(self.account.session_data or "{}")
            self.cl = build_client()
            # Qurilma UUID larini saqlab qolish
            if old_settings.get("uuids"):
                self.cl.set_settings({"uuids": old_settings["uuids"]})
            self.cl.login(self.account.username, self.account.password)
            self.account.session_data = json.dumps(self.cl.get_settings())
            self.account.status = "active"
            self.db.commit()
            logger.info(f"Qayta login ok: {self.account.username}")
            return True
        except Exception as e:
            logger.error(f"Qayta login xatosi ({self.account.username}): {e}")
            self.account.status = "login_required"
            self.db.commit()
            return False

    def login(self, username: str, password: str):
        """Yangi akkauntga login qilish."""
        try:
            self.cl = build_client()
            self.cl.login(username, password)
            session_data = json.dumps(self.cl.get_settings())
            logger.info(f"Login ok: {username}")
            return True, session_data
        except BadPassword:
            # Boshqa qurilma bilan qayta urinish
            try:
                time.sleep(3)
                self.cl = build_client()
                self.cl.login(username, password)
                session_data = json.dumps(self.cl.get_settings())
                return True, session_data
            except BadPassword:
                return False, "Parol noto'g'ri. Instagram parolingizni tekshiring."
            except ChallengeRequired:
                return False, (
                    "⚠️ Instagram tekshiruvi talab qilmoqda.\n\n"
                    "Instagram ilovasini oching → bildirishnomani tasdiqlang → qaytadan urinib ko'ring."
                )
            except Exception as e:
                return False, f"Login xatosi: {str(e)}"
        except ChallengeRequired:
            return False, (
                "⚠️ Instagram hisobingizni tasdiqlashni talab qilmoqda.\n\n"
                "1️⃣ Instagram ilovasini oching\n"
                "2️⃣ Kelib tushgan bildirishnomani tasdiqlang\n"
                "3️⃣ So'ng qaytadan urinib ko'ring"
            )
        except TwoFactorRequired:
            return False, (
                "🔐 Ikki bosqichli tasdiqlash (2FA) yoqilgan.\n\n"
                "Instagram → Sozlamalar → Xavfsizlik → 2FA ni o'chiring,\n"
                "so'ng qaytadan urinib ko'ring."
            )
        except Exception as e:
            logger.error(f"Login xatosi ({username}): {e}")
            err = str(e).lower()
            if "400" in str(e) or "bad_password" in err:
                return False, "Parol noto'g'ri. Instagram parolingizni tekshiring."
            if "checkpoint" in err or "challenge" in err:
                return False, (
                    "⚠️ Instagram hisobingizni tasdiqlashni talab qilmoqda.\n"
                    "Instagram ilovasini oching va tasdiqlang."
                )
            if "wait" in err or "few minutes" in err:
                return False, "Instagram vaqtincha blokladi. 10 daqiqa kuting."
            return False, f"Xato: {str(e)}"

    def check_account_status(self):
        """Akkaunt holatini tekshirish."""
        if not self.account:
            return "inactive", "Akkaunt yuklanmagan"
        try:
            self.cl.account_info()
            self.account.status = "active"
            self.db.commit()
            return "active", "Akkaunt faol"
        except LoginRequired:
            relogin_ok = self._relogin()
            if relogin_ok:
                return "active", "Qayta login muvaffaqiyatli"
            return "login_required", "Login talab qilinmoqda"
        except Exception as e:
            self.account.status = "error"
            self.db.commit()
            return "error", str(e)

    def view_reel(self, media_id: str):
        """Reelni ko'rish."""
        try:
            self.cl.media_info(media_id)
            self._log_task("view", media_id, True, "Ko'rildi")
            return True, "Reel ko'rildi"
        except MediaNotFound:
            self._log_task("view", media_id, False, "Media topilmadi")
            return False, "Media topilmadi"
        except LoginRequired:
            if self._relogin():
                return self.view_reel(media_id)
            return False, "Login talab qilinmoqda"
        except Exception as e:
            self._log_task("view", media_id, False, str(e))
            return False, str(e)

    def like_media(self, media_id: str):
        """Mediaga like bosish."""
        try:
            result = self.cl.media_like(media_id)
            if result:
                self._log_task("like", media_id, True, "Like bosildi")
                return True, "Like bosildi"
            self._log_task("like", media_id, False, "Like bosilmadi")
            return False, "Like bosilmadi"
        except MediaNotFound:
            return False, "Media topilmadi"
        except LoginRequired:
            if self._relogin():
                return self.like_media(media_id)
            return False, "Login talab qilinmoqda"
        except ClientError as e:
            self._log_task("like", media_id, False, str(e))
            return False, f"Instagram xatosi: {e}"
        except Exception as e:
            self._log_task("like", media_id, False, str(e))
            return False, str(e)

    def comment_media(self, media_id: str, text: str):
        """Mediaga izoh qoldirish."""
        if not text or not text.strip():
            return False, "Izoh matni bo'sh bo'lishi mumkin emas"
        try:
            comment = self.cl.media_comment(media_id, text.strip())
            if comment:
                self._log_task("comment", media_id, True, f"Izoh: {text[:50]}")
                return True, "Izoh qo'shildi"
            return False, "Izoh qo'shilmadi"
        except MediaNotFound:
            return False, "Media topilmadi"
        except LoginRequired:
            if self._relogin():
                return self.comment_media(media_id, text)
            return False, "Login talab qilinmoqda"
        except ClientError as e:
            self._log_task("comment", media_id, False, str(e))
            return False, f"Instagram xatosi: {e}"
        except Exception as e:
            self._log_task("comment", media_id, False, str(e))
            return False, str(e)

    def follow_user(self, user_id: str):
        """Foydalanuvchini kuzatish."""
        try:
            result = self.cl.user_follow(user_id)
            if result:
                self._log_task("follow", user_id, True, "Kuzatildi")
                return True, "Kuzatildi"
            return False, "Kuzatilmadi"
        except LoginRequired:
            if self._relogin():
                return self.follow_user(user_id)
            return False, "Login talab qilinmoqda"
        except Exception as e:
            self._log_task("follow", user_id, False, str(e))
            return False, str(e)

    def get_media_id_from_url(self, url: str):
        """URL dan media ID olish."""
        try:
            media_id = self.cl.media_id(self.cl.media_pk_from_url(url))
            return True, media_id
        except Exception as e:
            return False, str(e)

    def _log_task(self, task_type: str, media_id: str, success: bool, message: str):
        """Vazifa natijasini bazaga yozish."""
        try:
            if self.account:
                log = TaskLog(
                    account_id=self.account.id,
                    task_type=task_type,
                    media_id=media_id,
                    success=success,
                    message=message,
                )
                self.db.add(log)
                self.db.commit()
        except Exception as e:
            logger.error(f"Log yozishda xato: {e}")

    def close(self):
        """DB ulanishini yopish."""
        try:
            self.db.close()
        except Exception as e:
            logger.error(f"DB yopishda xato: {e}")
                                
