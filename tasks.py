import asyncio
import json
import random
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import SessionLocal, InstagramAccount, InstagramTask, TaskAccount
from instagram_api import InstagramBot


async def execute_instagram_task(task_id: int):
    db = SessionLocal()
    task = db.query(InstagramTask).filter(InstagramTask.id == task_id).first()
    if not task:
        db.close()
        return

    task.status = "in_progress"
    db.commit()

    accounts_for_task = db.query(TaskAccount).filter(TaskAccount.task_id == task_id).all()
    random.shuffle(accounts_for_task) # Shuffle to distribute load

    comments_list = json.loads(task.comments) if task.comments else []

    for task_account in accounts_for_task:
        account = db.query(InstagramAccount).filter(InstagramAccount.id == task_account.account_id).first()
        if not account or account.status != "active":
            task_account.status = "skipped_inactive"
            db.commit()
            continue

        ig_bot = InstagramBot(account_id=account.id)
        if not ig_bot.account or ig_bot.account.status != "active":
            task_account.status = "skipped_session_error"
            db.commit()
            ig_bot.close()
            continue

        try:
            # View reel
            if task.views_enabled:
                success, msg = ig_bot.view_reel(task.reel_url)
                if not success:
                    print(f"Error viewing reel for {account.username}: {msg}")

            # Like media
            if task.likes_enabled:
                success, msg = ig_bot.like_media(task.reel_url)
                if not success:
                    print(f"Error liking media for {account.username}: {msg}")

            # Comment media
            if comments_list:
                comment_text = random.choice(comments_list)
                success, msg = ig_bot.comment_media(task.reel_url, comment_text)
                if success:
                    task_account.comment_text = comment_text
                else:
                    print(f"Error commenting on media for {account.username}: {msg}")

            task_account.status = "completed"
            db.commit()

        except Exception as e:
            print(f"Unhandled error for {account.username} on task {task.id}: {e}")
            task_account.status = "failed"
            db.commit()
        finally:
            ig_bot.close()

        await asyncio.sleep(random.randint(10, 30)) # Simulate human-like delay

    task.status = "completed"
    task.completed_at = datetime.utcnow()
    db.commit()
    db.close()


async def start_task_processor():
    while True:
        db = SessionLocal()
        pending_tasks = db.query(InstagramTask).filter(InstagramTask.status == "pending").all()
        for task in pending_tasks:
            # This is a simplified approach. For real-world, use a proper task queue (e.g., Celery, Redis Queue)
            # For now, we'll just run it directly, but in a non-blocking way.
            asyncio.create_task(execute_instagram_task(task.id))
        db.close()
        await asyncio.sleep(60) # Check for new tasks every minute


async def run_loader_task(reel_url: str, comments: list, likes_enabled: bool, views_enabled: bool, admin_id: int):
    db = SessionLocal()
    active_accounts = db.query(InstagramAccount).filter(InstagramAccount.status == "active").all()

    if not active_accounts:
        db.close()
        return "Faol Instagram akkauntlari topilmadi."

    # Create a new task
    new_task = InstagramTask(
        reel_url=reel_url,
        comments=json.dumps(comments) if comments else None,
        likes_enabled=likes_enabled,
        views_enabled=views_enabled,
        status="pending"
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # Assign accounts to the task
    for account in active_accounts:
        task_account = TaskAccount(
            task_id=new_task.id,
            account_id=account.id,
            status="pending"
        )
        db.add(task_account)
    db.commit()
    db.close()

    return f"{len(active_accounts)} ta akkaunt uchun yangi vazifa (ID: {new_task.id}) yaratildi. Vazifa bajarilishi boshlandi."
