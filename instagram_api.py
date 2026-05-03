import json
import os
import time
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, BadPassword, ChallengeRequired, TwoFactorRequired
from database import SessionLocal, InstagramAccount


class InstagramBot:
    def __init__(self, account_id: int = None):
        self.cl = Client()
        self.db = SessionLocal()
        self.account = None
        if account_id:
            self.account = self.db.query(InstagramAccount).filter(InstagramAccount.id == account_id).first()
            if self.account and self.account.session_data:
                try:
                    self.cl.set_settings(json.loads(self.account.session_data))
                    self.cl.login(self.account.username, self.account.password)
                except Exception as e:
                    print(f"Error loading session for {self.account.username}: {e}")
                    self.account.status = "session_expired"
                    self.db.commit()

    def login(self, username, password):
        try:
            self.cl.login(username, password)
            session_data = json.dumps(self.cl.get_settings())
            return True, session_data
        except BadPassword:
            return False, "Bad password"
        except ChallengeRequired:
            return False, "Challenge required"
        except TwoFactorRequired:
            return False, "Two-factor authentication required"
        except Exception as e:
            return False, str(e)

    def check_account_status(self):
        if not self.account:
            return "inactive", "No account loaded"
        try:
            self.cl.account_info()
            self.account.status = "active"
            self.db.commit()
            return "active", "Account is active"
        except LoginRequired:
            self.account.status = "login_required"
            self.db.commit()
            return "login_required", "Login required"
        except Exception as e:
            self.account.status = "error"
            self.db.commit()
            return "error", str(e)

    def view_reel(self, media_id):
        try:
            self.cl.media_info(media_id)
            # instagrapi doesn't have a direct 'view reel' function, media_info acts as a view
            return True, "Reel viewed"
        except Exception as e:
            return False, str(e)

    def like_media(self, media_id):
        try:
            self.cl.media_like(media_id)
            return True, "Media liked"
        except Exception as e:
            return False, str(e)

    def comment_media(self, media_id, text):
        try:
            self.cl.media_comment(media_id, text)
            return True, "Comment added"
        except Exception as e:
            return False, str(e)

    def close(self):
        self.db.close()


# Example usage (for testing purposes)
if __name__ == "__main__":
    # This part is for local testing and won't be part of the bot's main logic
    # It assumes you have a .env file with INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD
    from dotenv import load_dotenv
    load_dotenv()

    test_username = os.getenv("INSTAGRAM_USERNAME")
    test_password = os.getenv("INSTAGRAM_PASSWORD")

    if test_username and test_password:
        print(f"Attempting to log in with {test_username}...")
        bot = InstagramBot()
        success, message = bot.login(test_username, test_password)
        if success:
            print(f"Login successful: {message}")
            # Save session data to DB (this would be handled by the bot logic)
            # For testing, let's just print it
            print(f"Session data: {message}")

            # Example: Check status
            # For this to work, you'd need to save the account to DB first
            # and then initialize InstagramBot with account_id
            # For now, let's just use the logged-in client
            try:
                bot.cl.account_info()
                print("Account is active after login.")
            except Exception as e:
                print(f"Account status check failed: {e}")

            # Example: Perform actions (replace with actual media_id)
            # media_id = "YOUR_REEL_MEDIA_ID"
            # if media_id:
            #     print(f"Viewing reel {media_id}...")
            #     view_success, view_msg = bot.view_reel(media_id)
            #     print(f"View reel: {view_success}, {view_msg}")

            #     print(f"Liking media {media_id}...")
            #     like_success, like_msg = bot.like_media(media_id)
            #     print(f"Like media: {like_success}, {like_msg}")

            #     print(f"Commenting on media {media_id}...")
            #     comment_success, comment_msg = bot.comment_media(media_id, "Great reel!")
            #     print(f"Comment media: {comment_success}, {comment_msg}")

        else:
            print(f"Login failed: {message}")
        bot.close()
    else:
        print("Please set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your .env file for testing.")
