import json
import os
import time
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


class InstagramBot:
    def __init__(self, account_id: int = None):
        self.cl = Client()
        # instagrapi so'rovlar orasiga kichik delay qo'shish (ban oldini olish)
        self.cl.delay_range = [1, 3]
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
                    self.cl.set_settings(json.loads(self.account.session_data))
                    self.cl.login(self.account.username, self.account.password)
                    self.account.status = "active"
                    self.db.commit()
                    logger.info(f"Session yuklandi: {self.account.username}")
                except LoginRequired:
                    logger.warning(f"Session eskirgan: {self.account.username}, qayta login qilinmoqda...")
                    self._relogin()
                except Exception as e:
                    logger.error(f"Session yuklab bo'lmadi ({self.account.username}): {e}")
                    self.account.status = "session_expired"
                    self.db.commit()

    def _relogin(self):
        """Session eskirganda qayta login qilish."""
        if not self.account:
            return False
        try:
            self.cl.set_settings({})
            self.cl.login(self.account.username, self.account.password)
            self.account.session_data = json.dumps(self.cl.get_settings())
            self.account.status = "active"
            self.db.commit()
            logger.info(f"Qayta login muvaffaqiyatli: {self.account.username}")
            return True
        except Exception as e:
            logger.error(f"Qayta login xatosi ({self.account.username}): {e}")
            self.account.status = "login_required"
            self.db.commit()
            return False

    def login(self, username: str, password: str):
        """Yangi akkauntga login qilish."""
        try:
            self.cl.login(username, password)
            session_data = json.dumps(self.cl.get_settings())
            logger.info(f"Login muvaffaqiyatli: {username}")
            return True, session_data
        except BadPassword:
            return False, "Parol noto'g'ri"
        except ChallengeRequired:
            return False, "Instagram tekshiruvi talab qilinmoqda (challenge)"
        except TwoFactorRequired:
            return False, "Ikki bosqichli tasdiqlash talab qilinmoqda"
        except Exception as e:
            logger.error(f"Login xatosi ({username}): {e}")
            return False, str(e)

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
            logger.warning(f"Login talab qilinmoqda: {self.account.username}")
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
            else:
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
