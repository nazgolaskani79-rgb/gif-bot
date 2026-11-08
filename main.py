import os
import asyncio
import io
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant
from PIL import Image

# --- تنظیمات از سرور خوانده می‌شود ---
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "")
INSTAGRAM_LINK = os.environ.get("INSTAGRAM_LINK", "")

app = Client("gif_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def init_db():
    conn = sqlite3.connect("bot.db")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, instagram_approved INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def set_instagram_approved(user_id, approved):
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE users SET instagram_approved = ? WHERE user_id = ?", (1 if approved else 0, user_id))
    conn.commit()
    conn.close()

def is_instagram_approved(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.execute("SELECT instagram_approved FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def create_gif_from_photo(photo_bytes):
    img = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    size = (480, 480)
    img = img.resize(size, Image.LANCZOS)
    gif_frames = []
    max_zoom = 1.25
    frames = 20
    for i in range(frames):
        zoom = 1.0 + (max_zoom - 1.0) * (i / (frames - 1))
        new_w, new_h = int(size[0] / zoom), int(size[1] / zoom)
        left, top = (size[0] - new_w) // 2, (size[1] - new_h) // 2
        cropped = img.crop((left, top, left + new_w, top + new_h))
        gif_frames.append(cropped.resize(size, Image.LANCZOS))
    out = io.BytesIO()
    gif_frames[0].save(out, format="GIF", save_all=True, append_images=gif_frames[1:], duration=60, loop=0, optimize=True)
    out.seek(0)
    return out

async def check_membership(user_id):
    try:
        member = await app.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("owner", "administrator", "member")
    except UserNotParticipant:
        return False
    except Exception:
        return False

def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 عضویت در کانال", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ عضو شدم، بررسی کن", callback_data="check_join")],
    ])

def instagram_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 رفتن به پیج اینستاگرام", url=INSTAGRAM_LINK)],
    ])

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message):
    user_id = message.from_user.id
    add_user(user_id)
    if not await check_membership(user_id):
        await message.reply_text("سلام! 👋\nبرای استفاده از ربات، ابتدا باید در کانال ما عضو شوید:", reply_markup=join_keyboard())
        return
    if not is_instagram_approved(user_id):
        await message.reply_text("عالی! حالا لطفاً:\n۱. به پیج اینستاگرام ما بروید.\n۲. ما را فالو کنید.\n۳. یک **اسکرین‌شات** از صفحه پیج که نشان می‌دهد ما را فالو کرده‌اید، برای ربات ارسال کنید.\n\n⏳ پس از تأیید ادمین، می‌توانید از ربات استفاده کنید.", reply_markup=instagram_keyboard())
        return
    await message.reply_text("🎉 خوش آمدید!\nحالا فقط کافی است یک **عکس** برای من بفرستید تا آن را به گیف تبدیل کنم.")

@app.on_callback_query(filters.regex("^check_join$"))
async def cb_check_join(client, cb: CallbackQuery):
    user_id = cb.from_user.id
    if await check_membership(user_id):
        await cb.message.edit_text("✅ عضویت شما تأیید شد!")
        if not is_instagram_approved(user_id):
            await cb.message.reply_text("حالا لطفاً پیج اینستاگرام ما را فالو کرده و **اسکرین‌شات** بفرستید:", reply_markup=instagram_keyboard())
        else:
            await cb.message.reply_text("یک عکس بفرستید تا به گیف تبدیل شود 🎞")
    else:
        await cb.answer("❌ هنوز عضو کانال نیستید!", show_alert=True)

@app.on_message(filters.private & filters.photo)
async def handle_photo(client, message):
    user_id = message.from_user.id
    if not await check_membership(user_id):
        await message.reply_text("ابتدا باید در کانال عضو شوید:", reply_markup=join_keyboard())
        return
    if not is_instagram_approved(user_id):
        await message.reply_text("⏳ اسکرین‌شات شما برای بررسی به ادمین ارسال شد...")
        try:
            await client.send_photo(ADMIN_ID, photo=message.photo.file_id, caption=f"🔔 درخواست تأیید\n👤 {message.from_user.first_name}\n🆔 `{user_id}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید", callback_data=f"approve_{user_id}"), InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id}")]]))
        except Exception as e:
            print(f"Admin send error: {e}")
        return
    status = await message.reply_text("🎨 در حال ساخت گیف... لطفاً صبر کنید.")
    try:
        photo_bytes = await client.download_media(message.photo.file_id, in_memory=True)
        gif_io = await asyncio.to_thread(create_gif_from_photo, photo_bytes.getvalue())
        await message.reply_animation(gif_io, caption="🎞 گیف شما آماده است!")
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ خطا: {e}")

@app.on_callback_query(filters.regex(r"^(approve|reject)_(\d+)$"))
async def cb_admin_action(client, cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔ دسترسی ندارید!", show_alert=True)
        return
    action, user_id = cb.data.split("_")
    user_id = int(user_id)
    if action == "approve":
        set_instagram_approved(user_id, True)
        await cb.message.edit_caption(cb.message.caption + "\n\n✅ تأیید شد")
        try: await client.send_message(user_id, "✅ تأیید شد! حالا عکس بفرست تا گیف بسازم.")
        except: pass
    else:
        await cb.message.edit_caption(cb.message.caption + "\n\n❌ رد شد")
        try: await client.send_message(user_id, "❌ متأسفانه درخواست شما رد شد.")
        except: pass

if __name__ == "__main__":
    init_db()
    print("🤖 ربات روشن شد...")
    app.run()
