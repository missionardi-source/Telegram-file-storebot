"""
═══════════════════════════════════════════════════════════
  COMPLETE TELEGRAM FILE STORE BOT - SINGLE FILE
  SQLite database (MongoDB ki zaroorat NAHI)
  Bas ise run karo, sab kuch chalega!
═══════════════════════════════════════════════════════════
"""

import logging
import re
import sqlite3
import json
import random
import string
import os
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
from telegram.error import TelegramError
from telegram.constants import ChatMemberStatus
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════
#  CONFIG (bas .env se padhta hai)
# ═══════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("8256203760:AAFSJPjyEj2xYV_Qzk0tYy12iGnvjneRLpI")
OWNER_ID = int(os.getenv("9197767409", "0"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Yamrajjix")
DB_FILE = os.getenv("DB_FILE", "filestore.db")

COINS_PER_FILE = 1
COINS_PER_REFERRAL = 1
DAILY_BONUS = 5

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  SQLITE DATABASE
# ═══════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        code TEXT PRIMARY KEY, file_id TEXT, file_type TEXT,
        file_name TEXT, caption TEXT, admin_id INTEGER,
        clicks INTEGER DEFAULT 0, price INTEGER DEFAULT 0,
        purchases INTEGER DEFAULT 0, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        coins INTEGER DEFAULT 0, referrals INTEGER DEFAULT 0,
        referred_by INTEGER, files_opened INTEGER DEFAULT 0,
        purchased_files TEXT DEFAULT '[]', banned INTEGER DEFAULT 0,
        joined_at TEXT, last_bonus TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id INTEGER, first_name TEXT,
        rupees INTEGER, coins INTEGER, screenshot TEXT,
        status TEXT DEFAULT 'pending', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY, discount INTEGER,
        max_uses INTEGER DEFAULT 100, used INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id INTEGER,
        buyer_name TEXT, file_code TEXT, file_name TEXT,
        price INTEGER, sold_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

def gen_code(n=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

# ═══════════════════════════════════════════════════════════
#  SETTINGS
# ═══════════════════════════════════════════════════════════
def get_setting(key, default=None):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row: return default
    try: return json.loads(row["value"])
    except: return row["value"]

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                 (key, json.dumps(value) if not isinstance(value, str) else value))
    conn.commit(); conn.close()

def get_qr(): return get_setting("qr_file_id")
def set_qr(fid): set_setting("qr_file_id", fid)
def get_coin_rate(): return get_setting("coin_rate", {"rupees": 10, "coins": 100})
def set_coin_rate(r, c): set_setting("coin_rate", {"rupees": r, "coins": c})
def get_force_channels(): return get_setting("force_channels", [])
def set_force_channels(ch): set_setting("force_channels", ch)

# ═══════════════════════════════════════════════════════════
#  FILES
# ═══════════════════════════════════════════════════════════
def save_file(fid, ftype, fname, cap, admin_id, price=0):
    code = gen_code()
    conn = get_db()
    conn.execute("INSERT INTO files (code, file_id, file_type, file_name, caption, admin_id, price, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (code, fid, ftype, fname, cap, admin_id, int(price), datetime.now().isoformat()))
    conn.commit(); conn.close()
    return code

def get_file(code):
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE code=?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None

def inc_clicks(code):
    conn = get_db()
    conn.execute("UPDATE files SET clicks = clicks + 1 WHERE code=?", (code,))
    conn.commit(); conn.close()

def inc_purchases(code):
    conn = get_db()
    conn.execute("UPDATE files SET purchases = purchases + 1 WHERE code=?", (code,))
    conn.commit(); conn.close()

def upd_price(code, p):
    conn = get_db()
    conn.execute("UPDATE files SET price=? WHERE code=?", (int(p), code))
    conn.commit(); conn.close()

def get_all_files():
    conn = get_db()
    rows = conn.execute("SELECT * FROM files ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ═══════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════
def save_user(uid, uname, fname, ref_by=None):
    conn = get_db()
    exist = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if exist:
        conn.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (uname, fname, uid))
        conn.commit(); conn.close()
        return False, False
    conn.execute("INSERT INTO users (user_id, username, first_name, referred_by, joined_at) VALUES (?, ?, ?, ?, ?)",
                 (uid, uname, fname, None, datetime.now().isoformat()))
    ref_ok = False
    if ref_by and ref_by != uid:
        referrer = conn.execute("SELECT * FROM users WHERE user_id=?", (ref_by,)).fetchone()
        if referrer:
            conn.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref_by, uid))
            conn.execute("UPDATE users SET coins = coins + ?, referrals = referrals + 1 WHERE user_id=?",
                         (COINS_PER_REFERRAL, ref_by))
            ref_ok = True
    conn.commit(); conn.close()
    return True, ref_ok

def get_user(uid):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not row: return None
    u = dict(row)
    try: u["purchased_files"] = json.loads(u.get("purchased_files") or "[]")
    except: u["purchased_files"] = []
    return u

def add_coins(uid, amt):
    conn = get_db()
    conn.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amt, uid))
    conn.commit(); conn.close()

def get_balance(uid):
    u = get_user(uid)
    return u.get("coins", 0) if u else 0

def has_purchased(uid, code):
    u = get_user(uid)
    if not u: return False
    return code in u.get("purchased_files", [])

def mark_purchased(uid, code):
    u = get_user(uid)
    if not u: return
    files = u.get("purchased_files", [])
    if code not in files: files.append(code)
    conn = get_db()
    conn.execute("UPDATE users SET purchased_files=? WHERE user_id=?", (json.dumps(files), uid))
    conn.commit(); conn.close()

def ban_user(uid):
    conn = get_db(); conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (uid,))
    conn.commit(); conn.close()

def unban_user(uid):
    conn = get_db(); conn.execute("UPDATE users SET banned=0 WHERE user_id=?", (uid,))
    conn.commit(); conn.close()

def get_leaderboard(lim=10):
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY coins DESC LIMIT ?", (lim,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_users():
    conn = get_db()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_users(lim=10):
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT ?", (lim,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def can_claim_bonus(uid):
    u = get_user(uid)
    if not u: return False
    last = u.get("last_bonus")
    if not last: return True
    try:
        return datetime.now() - datetime.fromisoformat(last) > timedelta(hours=24)
    except:
        return True

def claim_bonus(uid):
    conn = get_db()
    conn.execute("UPDATE users SET coins = coins + ?, last_bonus=? WHERE user_id=?",
                 (DAILY_BONUS, datetime.now().isoformat(), uid))
    conn.commit(); conn.close()

# ═══════════════════════════════════════════════════════════
#  PAYMENTS
# ═══════════════════════════════════════════════════════════
def create_payment(uid, fname, rupees, coins, screen):
    pid = gen_code(10)
    conn = get_db()
    conn.execute("INSERT INTO payments (id, user_id, first_name, rupees, coins, screenshot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (pid, uid, fname, rupees, coins, screen, datetime.now().isoformat()))
    conn.commit(); conn.close()
    return pid

def get_payment(pid):
    conn = get_db()
    row = conn.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_pending_payments():
    conn = get_db()
    rows = conn.execute("SELECT * FROM payments WHERE status='pending' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def approve_payment(pid):
    p = get_payment(pid)
    if not p or p["status"] != "pending": return None
    conn = get_db()
    conn.execute("UPDATE payments SET status='approved' WHERE id=?", (pid,))
    conn.commit(); conn.close()
    add_coins(p["user_id"], p["coins"])
    return p

def reject_payment(pid):
    p = get_payment(pid)
    if not p or p["status"] != "pending": return None
    conn = get_db()
    conn.execute("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return p

def get_revenue():
    conn = get_db()
    row = conn.execute("SELECT SUM(rupees) as total FROM payments WHERE status='approved'").fetchone()
    conn.close()
    return row["total"] if row and row["total"] else 0

# ═══════════════════════════════════════════════════════════
#  COUPONS
# ═══════════════════════════════════════════════════════════
def create_coupon(code, pct, uses=100):
    code = code.upper()
    conn = get_db()
    if conn.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone():
        conn.close(); return False
    conn.execute("INSERT INTO coupons (code, discount, max_uses) VALUES (?, ?, ?)", (code, pct, uses))
    conn.commit(); conn.close()
    return True

def get_coupon(code):
    conn = get_db()
    row = conn.execute("SELECT * FROM coupons WHERE code=?", (code.upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def apply_coupon(code):
    c = get_coupon(code)
    if not c or not c["active"] or c["used"] >= c["max_uses"]: return None
    conn = get_db()
    conn.execute("UPDATE coupons SET used = used + 1 WHERE code=?", (code.upper(),))
    conn.commit(); conn.close()
    return c

def delete_coupon(code):
    conn = get_db(); conn.execute("DELETE FROM coupons WHERE code=?", (code.upper(),))
    conn.commit(); conn.close()

def get_all_coupons():
    conn = get_db()
    rows = conn.execute("SELECT * FROM coupons").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ═══════════════════════════════════════════════════════════
#  SALES
# ═══════════════════════════════════════════════════════════
def record_sale(uid, name, code, fname, price):
    conn = get_db()
    conn.execute("INSERT INTO sales (buyer_id, buyer_name, file_code, file_name, price, sold_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (uid, name, code, fname, price, datetime.now().isoformat()))
    conn.commit(); conn.close()

def get_recent_sales(lim=15):
    conn = get_db()
    rows = conn.execute("SELECT * FROM sales ORDER BY sold_at DESC LIMIT ?", (lim,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_total_sold():
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as c FROM sales").fetchone()
    conn.close()
    return row["c"] if row else 0

# ═══════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════
def get_stats():
    conn = get_db()
    return {
        "files": conn.execute("SELECT COUNT(*) as c FROM files").fetchone()["c"],
        "users": conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"],
        "clicks": conn.execute("SELECT SUM(clicks) as s FROM files").fetchone()["s"] or 0,
        "purchases": conn.execute("SELECT SUM(purchases) as s FROM files").fetchone()["s"] or 0,
        "coins": conn.execute("SELECT SUM(coins) as s FROM users").fetchone()["s"] or 0,
        "pending": conn.execute("SELECT COUNT(*) as c FROM payments WHERE status='pending'").fetchone()["c"],
        "revenue": get_revenue(),
    }
    conn.close()

# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════
def is_owner(uid): return uid == OWNER_ID
def is_admin(uid): return uid == OWNER_ID or uid in ADMIN_IDS

UPLOAD_STATE = {}
PENDING = {}

# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════
def owner_kb():
    return ReplyKeyboardMarkup([
        ["📤 Upload", "🖼️ QR"],
        ["💰 Rate", "📢 Broadcast"],
        ["📊 Stats", "💳 Payments"],
        ["👥 Users", "📂 Files"],
        ["🎫 Coupons", "🏆 Sales"],
        ["🔔 Force Sub", "🎁 Add Coins"],
        ["❌ Close"]
    ], resize_keyboard=True)

def user_kb():
    return ReplyKeyboardMarkup([
        ["💰 Balance", "🎁 Refer"],
        ["🎁 Daily Bonus", "🏆 Top"],
        ["🆘 Support", "💳 Buy Coins"]
    ], resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)

# ═══════════════════════════════════════════════════════════
#  FORCE SUB
# ═══════════════════════════════════════════════════════════
async def check_joined_all(bot, uid):
    channels = get_force_channels()
    if not channels: return True, []
    not_joined = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                not_joined.append(ch)
        except TelegramError:
            not_joined.append(ch)
    return len(not_joined) == 0, not_joined

async def send_join_msg(target, not_joined):
    buttons = []
    for ch in not_joined:
        clean = ch.replace("@", "").replace("https://t.me/", "").replace("t.me/", "")
        if clean.lstrip("-").isdigit(): continue
        buttons.append([InlineKeyboardButton(f"📢 Join {clean}", url=f"https://t.me/{clean}")])
    buttons.append([InlineKeyboardButton("✅ Verify / Joined", callback_data="check_joined")])
    text = "🔔 **Channel Join Zaroori Hai!**\n\nPehle in channels ko join karein:\n\n"
    for i, ch in enumerate(not_joined, 1):
        text += f"{i}. {ch}\n"
    text += "\n✅ Join ke baad **Verify** dabayein."
    await target.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

async def require_joined(update, context):
    uid = update.effective_user.id
    if is_owner(uid) or is_admin(uid): return True
    if not get_force_channels(): return True
    joined, not_joined = await check_joined_all(context.bot, uid)
    if not joined:
        target = update.effective_message or (update.callback_query.message if update.callback_query else None)
        if target: await send_join_msg(target, not_joined)
        return False
    return True

# ═══════════════════════════════════════════════════════════
#  START
# ═══════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await require_joined(update, context): return

    args = context.args
    ref_id = file_code = None
    if args:
        a = args[0]
        if a.startswith("ref_"):
            try: ref_id = int(a.replace("ref_", ""))
            except: pass
        else:
            file_code = a

    is_new, ref_ok = save_user(user.id, user.username, user.first_name, ref_id)
    u = get_user(user.id)

    if u and u.get("banned"):
        return await update.message.reply_text("🚫 Aap ban ho chuke hain.")

    if is_new and ref_ok:
        try:
            await context.bot.send_message(ref_id,
                f"🎉 New referral!\n👤 {user.first_name}\n💰 +{COINS_PER_REFERRAL} coin!")
        except: pass

    if file_code:
        return await send_file(update, context, file_code)

    if is_owner(user.id):
        return await update.message.reply_text(
            f"👑 **Owner Panel**\n\n🪙 Coins: {get_balance(user.id)}\n💵 Revenue: ₹{get_revenue()}",
            parse_mode="Markdown", reply_markup=owner_kb())

    await update.message.reply_text(
        f"👋 Hello {user.first_name}!\n\n💰 Coins: **{get_balance(user.id)}**\n\nButtons use karein 👇",
        parse_mode="Markdown", reply_markup=user_kb())

# ═══════════════════════════════════════════════════════════
#  SEND FILE (STRICT)
# ═══════════════════════════════════════════════════════════
async def send_file(update, context, code):
    if not await require_joined(update, context): return
    uid = update.effective_user.id
    fd = get_file(code)
    if not fd:
        return await update.message.reply_text("❌ File not found.")
    user = get_user(uid)
    if not user:
        return await update.message.reply_text("Pehle /start karein.")
    if user.get("banned"):
        return await update.message.reply_text("🚫 Banned.")

    price = int(fd.get("price", 0))
    coins = int(user.get("coins", 0))

    if price == 0:
        inc_clicks(code)
        return await deliver(update.message, fd, "🆓 Free")

    if has_purchased(uid, code) or is_admin(uid):
        inc_clicks(code)
        return await deliver(update.message, fd, "✅ Already owned")

    if coins < price:
        shortage = price - coins
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Buy Coins", callback_data="buy_coins")],
            [InlineKeyboardButton("🎁 Refer & Earn", callback_data="ref_show")]
        ])
        return await update.message.reply_text(
            f"🔒 **FILE LOCKED**\n\n"
            f"📁 `{fd['file_name']}`\n"
            f"💰 **Price: {price} coins**\n"
            f"🪙 **Aapke: {coins} coins**\n\n"
            f"❌ **{shortage} coins kam hain!**\n\n"
            f"⚠️ Jab tak coins poore nahi honge, file nahi milegi.\n\n"
            f"**Coins kamayein:**\n"
            f"• 🎁 Refer = +{COINS_PER_REFERRAL}\n"
            f"• 🎁 Daily = +{DAILY_BONUS}\n"
            f"• 💳 Buy from owner\n"
            f"• 📂 Free files = +{COINS_PER_FILE}",
            reply_markup=kb, parse_mode="Markdown")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Buy for {price} coins", callback_data=f"buy_{code}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    await update.message.reply_text(
        f"💰 **Paid File**\n\n📁 `{fd['file_name']}`\n"
        f"💵 Price: **{price} coins**\n"
        f"🪙 Balance: **{coins}**\n"
        f"➡️ After: **{coins - price}**\n\nConfirm karein:",
        reply_markup=kb, parse_mode="Markdown")

async def deliver(message, fd, note=""):
    try:
        cap = (fd.get("caption") or "") + (f"\n\n{note}" if note else "")
        f, fid = fd["file_type"], fd["file_id"]
        if f == "document": await message.reply_document(fid, caption=cap)
        elif f == "video": await message.reply_video(fid, caption=cap)
        elif f == "photo": await message.reply_photo(fid, caption=cap)
        elif f == "audio": await message.reply_audio(fid, caption=cap)
    except Exception as e:
        logger.error(f"Deliver: {e}")
        await message.reply_text("⚠️ File bhejne mein error.")

# ═══════════════════════════════════════════════════════════
#  CALLBACKS
# ═══════════════════════════════════════════════════════════
async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if q.data == "check_joined":
        await q.answer("Checking...")
        joined, not_joined = await check_joined_all(context.bot, q.from_user.id)
        if joined:
            await q.answer("✅ Verified!", show_alert=True)
            try: await q.message.delete()
            except: pass
            await context.bot.send_message(
                q.from_user.id,
                "✅ **Verified!**\n\nAb /start dabayein.",
                reply_markup=user_kb())
        else:
            await q.answer("❌ Abhi join nahi kiya!", show_alert=True)
            await send_join_msg(q.message, not_joined)
        return

    await q.answer()
    if not await require_joined(update, context): return

    d = q.data
    uid = q.from_user.id

    if d == "cancel":
        return await q.edit_message_text("❌ Cancelled.")

    if d == "buy_coins":
        rate = get_coin_rate(); qr = get_qr()
        await q.edit_message_text(
            f"💳 **Buy Coins**\n\n₹{rate['rupees']} = {rate['coins']} coins\n\n"
            f"**Steps:**\n1. QR scan\n2. Pay ₹{rate['rupees']}\n3. Screenshot bhejein\n4. Owner approve",
            parse_mode="Markdown")
        if qr:
            try:
                await q.message.reply_photo(qr, caption="💳 Scan to pay")
                PENDING[uid] = {"wait_payment": True}
            except: pass
        return

    if d == "ref_show":
        bn = (await context.bot.get_me()).username
        return await q.edit_message_text(
            f"🎁 `https://t.me/{bn}?start=ref_{uid}`\n\nHar referral = +{COINS_PER_REFERRAL}",
            parse_mode="Markdown")

    if d.startswith("coupon_"):
        code = d.replace("coupon_", "")
        PENDING[uid] = {"wait_coupon": True, "coupon_for": code}
        return await q.message.reply_text("🎫 Coupon code bhejein:")

    if d.startswith("buy_"):
        code = d.replace("buy_", "")
        fd = get_file(code)
        if not fd: return await q.edit_message_text("❌ File not found.")
        user = get_user(uid)
        if not user: return await q.edit_message_text("❌ User not found.")
        if user.get("banned"): return await q.edit_message_text("🚫 Banned.")

        price = int(fd.get("price", 0))
        if has_purchased(uid, code):
            return await q.edit_message_text("✅ Already purchased!")

        ud = PENDING.get(uid, {})
        discount = ud.get("coupon_discount", 0)
        if discount:
            PENDING[uid] = {k: v for k, v in ud.items() if k != "coupon_discount"}
        final = max(1, int(price * (100 - discount) / 100)) if discount else price

        if int(user.get("coins", 0)) < final:
            return await q.edit_message_text(
                f"❌ **Coins kam!**\nPrice: {final}\nBalance: {user.get('coins',0)}")

        # ⭐ ATOMIC DEDUCT - SQLite conditional update
        conn = get_db()
        cur = conn.execute(
            "UPDATE users SET coins = coins - ? WHERE user_id=? AND coins >= ?",
            (final, uid, final))
        conn.commit()
        affected = cur.rowcount
        conn.close()

        if affected == 0:
            return await q.edit_message_text("❌ Transaction failed. Try again.")

        mark_purchased(uid, code)
        inc_purchases(code)
        inc_clicks(code)
        record_sale(uid, q.from_user.first_name, code, fd["file_name"], final)

        for a in ADMIN_IDS:
            try:
                await context.bot.send_message(a,
                    f"💰 **SALE!**\n📁 {fd['file_name']}\n💵 {final}\n👤 {q.from_user.first_name} (`{uid}`)")
            except: pass

        await q.edit_message_text(
            f"✅ **PURCHASED!**\n\n📁 `{fd['file_name']}`\n💸 -{final}\n🪙 Balance: **{get_balance(uid)}**")
        await deliver(q.message, fd, "✅ Purchased!")
        return

    if d.startswith("approve_"):
        if not is_owner(uid): return
        p = approve_payment(d.replace("approve_", ""))
        if p:
            await q.edit_message_text(f"✅ Approved {p['coins']} for {p['first_name']}")
            try:
                await context.bot.send_message(p["user_id"],
                    f"✅ Payment approved!\n+{p['coins']} coins\n🪙 Total: {get_balance(p['user_id'])}")
            except: pass
        else:
            await q.edit_message_text("⚠️ Already processed.")

    if d.startswith("reject_"):
        if not is_owner(uid): return
        p = reject_payment(d.replace("reject_", ""))
        if p:
            await q.edit_message_text(f"❌ Rejected {p['first_name']}")
            try:
                await context.bot.send_message(p["user_id"], f"❌ Payment rejected.")
            except: pass
        else:
            await q.edit_message_text("⚠️ Already processed.")

# ═══════════════════════════════════════════════════════════
#  OWNER HANDLERS
# ═══════════════════════════════════════════════════════════
async def owner_upload(update, context):
    if not is_owner(update.effective_user.id): return
    UPLOAD_STATE[OWNER_ID] = {"files": [], "state": "uploading"}
    await update.message.reply_text(
        "📤 **Upload Mode**\n\nFiles bhejein (caption: `price:50`)\n/done jab complete",
        parse_mode="Markdown", reply_markup=cancel_kb())

async def handle_file_upload(update, context):
    if not is_admin(update.effective_user.id): return
    st = UPLOAD_STATE.get(update.effective_user.id)
    if not st or st["state"] != "uploading": return

    m = update.message
    fd = None
    if m.document: fd = ("document", m.document.file_id, m.document.file_name or "file")
    elif m.video: fd = ("video", m.video.file_id, "video")
    elif m.photo: fd = ("photo", m.photo[-1].file_id, "photo")
    elif m.audio: fd = ("audio", m.audio.file_id, m.audio.file_name or "audio")
    if not fd: return await m.reply_text("⚠️ Sirf file bhejein.")

    ft, fid, fn = fd
    cap = m.caption or ""
    price = 0
    mt = re.search(r"price\s*[:=]\s*(\d+)", cap, re.I)
    if mt:
        price = int(mt.group(1))
        cap = re.sub(r"price\s*[:=]\s*\d+", "", cap, flags=re.I).strip()

    code = save_file(fid, ft, fn, cap, update.effective_user.id, price)
    st["files"].append({"code": code, "name": fn, "price": price})
    bn = (await context.bot.get_me()).username
    p = f"💰{price}" if price else "🆓"
    await m.reply_text(
        f"✅ `{fn}` [{p}]\n🔗 `https://t.me/{bn}?start={code}`\nTotal: {len(st['files'])}",
        parse_mode="Markdown")

async def owner_done(update, context):
    if not is_owner(update.effective_user.id): return
    st = UPLOAD_STATE.get(OWNER_ID)
    if not st or not st["files"]:
        return await update.message.reply_text("⚠️ No files.", reply_markup=owner_kb())
    bn = (await context.bot.get_me()).username
    txt = f"✅ **Done!** {len(st['files'])} files\n\n"
    for f in st["files"]:
        p = f"💰{f['price']}" if f.get("price", 0) else "🆓"
        txt += f"• `{f['name']}` [{p}]\n`https://t.me/{bn}?start={f['code']}`\n\n"
    UPLOAD_STATE.pop(OWNER_ID, None)
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=owner_kb())

async def owner_qr(update, context):
    if not is_owner(update.effective_user.id): return
    PENDING[OWNER_ID] = {"wait_qr": True}
    await update.message.reply_text("🖼️ QR photo bhejein:", reply_markup=cancel_kb())

async def owner_rate(update, context):
    if not is_owner(update.effective_user.id): return
    c = get_coin_rate()
    PENDING[OWNER_ID] = {"wait_rate": True}
    await update.message.reply_text(
        f"💰 Current: ₹{c['rupees']}={c['coins']}\n\nFormat: `10 100`",
        parse_mode="Markdown", reply_markup=cancel_kb())

async def owner_broadcast(update, context):
    if not is_owner(update.effective_user.id): return
    PENDING[OWNER_ID] = {"wait_broadcast": True}
    await update.message.reply_text(
        "📢 Sabko message bhejein:", reply_markup=cancel_kb())

async def owner_stats(update, context):
    if not is_owner(update.effective_user.id): return
    s = get_stats()
    await update.message.reply_text(
        f"📊 **Stats**\n\n👥 Users: {s['users']}\n📁 Files: {s['files']}\n"
        f"👁 Clicks: {s['clicks']}\n🛒 Purchases: {s['purchases']}\n"
        f"💰 Revenue: ₹{s['revenue']}\n⏳ Pending: {s['pending']}\n🪙 Coins: {s['coins']}",
        parse_mode="Markdown", reply_markup=owner_kb())

async def owner_payments(update, context):
    if not is_owner(update.effective_user.id): return
    pending = get_pending_payments()
    if not pending:
        return await update.message.reply_text("✅ No pending.", reply_markup=owner_kb())
    await update.message.reply_text(f"💳 {len(pending)} pending:")
    for p in pending[:10]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅", callback_data=f"approve_{p['id']}"),
            InlineKeyboardButton("❌", callback_data=f"reject_{p['id']}")
        ]])
        try:
            await context.bot.send_photo(update.effective_user.id, p["screenshot"],
                caption=f"👤 {p['first_name']} (`{p['user_id']}`)\n₹{p['rupees']}={p['coins']}",
                reply_markup=kb)
        except: pass

async def owner_users(update, context):
    if not is_owner(update.effective_user.id): return
    users = get_all_users()
    txt = f"👥 **Users: {len(users)}**\n\n"
    for u in get_recent_users(15):
        txt += f"• {u.get('first_name','?')} — 🪙{u.get('coins',0)} (`{u['user_id']}`)\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=owner_kb())

async def owner_files(update, context):
    if not is_owner(update.effective_user.id): return
    files = get_all_files()
    if not files:
        return await update.message.reply_text("📂 No files.", reply_markup=owner_kb())
    bn = (await context.bot.get_me()).username
    txt = "📂 **Files**\n\n"
    for f in files[:20]:
        p = f"💰{f.get('price',0)}" if f.get('price',0) > 0 else "🆓"
        txt += f"• `{f['file_name']}` [{p}]\n  `https://t.me/{bn}?start={f['code']}`\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=owner_kb())

async def owner_coupons(update, context):
    if not is_owner(update.effective_user.id): return
    coupons = get_all_coupons()
    txt = "🎫 **Coupons**\n\n"
    if not coupons:
        txt += "No coupons.\n\n"
    else:
        for c in coupons:
            txt += f"• `{c['code']}` — {c['discount']}% ({c['used']}/{c['max_uses']})\n"
    txt += "\n**Create:** `/addcoupon CODE %`\n**Delete:** `/delcoupon CODE`"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=owner_kb())

async def owner_sales(update, context):
    if not is_owner(update.effective_user.id): return
    sales = get_recent_sales(15)
    txt = f"🏆 **Sales**\n\n📦 Total: {get_total_sold()}\n\nRecent:\n"
    for s in sales:
        txt += f"• {s['file_name']} — {s['price']} by {s['buyer_name']}\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=owner_kb())

async def owner_addcoins(update, context):
    if not is_owner(update.effective_user.id): return
    PENDING[OWNER_ID] = {"wait_addcoins": True}
    await update.message.reply_text(
        "🎁 Format: `user_id amount`\nExample: `123456789 100`",
        parse_mode="Markdown", reply_markup=cancel_kb())

async def owner_forcesub(update, context):
    if not is_owner(update.effective_user.id): return
    channels = get_force_channels()
    if not channels:
        txt = "🔔 **Force Subscribe: OFF**\n\n➕ Add Channel dabayein\n\n⚠️ Bot ko channel ka Admin banana zaroori hai!"
    else:
        txt = f"🔔 **Force Sub ({len(channels)})**\n\n"
        for i, ch in enumerate(channels, 1):
            txt += f"{i}. `{ch}`\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Channel", callback_data="fs_add")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data="fs_remove")],
        [InlineKeyboardButton("🧪 Test Check", callback_data="fs_test")]
    ])
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)

# ═══════════════════════════════════════════════════════════
#  USER HANDLERS
# ═══════════════════════════════════════════════════════════
async def user_balance(update, context):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(
        f"💰 **Balance**\n\n🪙 Coins: **{u.get('coins',0)}**\n"
        f"👥 Referrals: **{u.get('referrals',0)}**\n"
        f"📂 Files: **{u.get('files_opened',0)}**\n"
        f"🛒 Purchased: **{len(u.get('purchased_files',[]))}**",
        parse_mode="Markdown", reply_markup=user_kb())

async def user_refer(update, context):
    uid = update.effective_user.id
    bn = (await context.bot.get_me()).username
    await update.message.reply_text(
        f"🎁 **Aapka Link**\n\n`https://t.me/{bn}?start=ref_{uid}`\n\nHar referral = +{COINS_PER_REFERRAL}",
        parse_mode="Markdown", reply_markup=user_kb())

async def user_daily(update, context):
    uid = update.effective_user.id
    if not can_claim_bonus(uid):
        return await update.message.reply_text("⏰ Aaj bonus le chuke.\n24h baad milega.", reply_markup=user_kb())
    claim_bonus(uid)
    await update.message.reply_text(
        f"🎁 **Daily Bonus!**\n\n+{DAILY_BONUS} coins\n🪙 Total: {get_balance(uid)}",
        parse_mode="Markdown", reply_markup=user_kb())

async def user_top(update, context):
    top = get_leaderboard(10)
    medals = ["🥇", "🥈", "🥉"]
    txt = "🏆 **Top 10**\n\n"
    for i, u in enumerate(top):
        m = medals[i] if i < 3 else f"{i+1}."
        txt += f"{m} {u.get('first_name','?')} — {u.get('coins',0)} 🪙\n"
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=user_kb())

async def user_support(update, context):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 Contact", url=f"https://t.me/{SUPPORT_USERNAME.replace('@','')}")
    ]])
    await update.message.reply_text(
        f"🆘 **Support**\n\n👤 {SUPPORT_USERNAME}",
        parse_mode="Markdown", reply_markup=kb)

async def user_buycoins(update, context):
    rate = get_coin_rate(); qr = get_qr()
    await update.message.reply_text(
        f"💳 **Buy Coins**\n\n₹{rate['rupees']} = {rate['coins']} coins\n\n"
        f"**Steps:**\n1. QR scan\n2. Pay ₹{rate['rupees']}\n3. Screenshot bhejein\n4. Owner approve",
        parse_mode="Markdown")
    if qr:
        try:
            await update.message.reply_photo(qr, caption="💳 Scan to pay")
            PENDING[update.effective_user.id] = {"wait_payment": True}
        except: pass

# ═══════════════════════════════════════════════════════════
#  CANCEL
# ═══════════════════════════════════════════════════════════
async def cancel_handler(update, context):
    uid = update.effective_user.id
    PENDING.pop(uid, None)
    UPLOAD_STATE.pop(uid, None)
    await update.message.reply_text("❌ Cancelled.",
        reply_markup=owner_kb() if is_owner(uid) else user_kb())

# ═══════════════════════════════════════════════════════════
#  MENU ROUTER
# ═══════════════════════════════════════════════════════════
async def menu_router(update, context):
    if not await require_joined(update, context): return
    txt = update.message.text
    uid = update.effective_user.id

    if is_owner(uid):
        if txt == "📤 Upload": return await owner_upload(update, context)
        if txt == "🖼️ QR": return await owner_qr(update, context)
        if txt == "💰 Rate": return await owner_rate(update, context)
        if txt == "📢 Broadcast": return await owner_broadcast(update, context)
        if txt == "📊 Stats": return await owner_stats(update, context)
        if txt == "💳 Payments": return await owner_payments(update, context)
        if txt == "👥 Users": return await owner_users(update, context)
        if txt == "📂 Files": return await owner_files(update, context)
        if txt == "🎫 Coupons": return await owner_coupons(update, context)
        if txt == "🏆 Sales": return await owner_sales(update, context)
        if txt == "🔔 Force Sub": return await owner_forcesub(update, context)
        if txt == "🎁 Add Coins": return await owner_addcoins(update, context)
        if txt == "❌ Close":
            return await update.message.reply_text("Closed.", reply_markup=user_kb())

    if txt == "💰 Balance": return await user_balance(update, context)
    if txt == "🎁 Refer": return await user_refer(update, context)
    if txt == "🎁 Daily Bonus": return await user_daily(update, context)
    if txt == "🏆 Top": return await user_top(update, context)
    if txt == "🆘 Support": return await user_support(update, context)
    if txt == "💳 Buy Coins": return await user_buycoins(update, context)

# ═══════════════════════════════════════════════════════════
#  FORCE SUB CALLBACK
# ═══════════════════════════════════════════════════════════
async def forcesub_callback(update, context):
    q = update.callback_query
    await q.answer()
    if not is_owner(q.from_user.id): return
    d = q.data

    if d == "fs_add":
        PENDING[OWNER_ID] = {"wait_fs_add": True}
        await q.edit_message_text(
            "➕ **Add Channel**\n\nChannel username bhejein:\n"
            "• Public: `@mychannel`\n• Private: `-1001234567890`\n\n"
            "**⚠️ Bot ko admin banana zaroori hai!**\n\n"
            "Multiple: `@ch1,@ch2`\n\nCancel: ❌ Cancel", parse_mode="Markdown")

    elif d == "fs_remove":
        channels = get_force_channels()
        if not channels:
            return await q.edit_message_text("⚠️ Koi channel nahi.")
        buttons = [[InlineKeyboardButton(f"❌ {ch}", callback_data=f"fs_del_{i}")]
                   for i, ch in enumerate(channels)]
        await q.edit_message_text("➖ **Remove**", reply_markup=InlineKeyboardMarkup(buttons))

    elif d.startswith("fs_del_"):
        idx = int(d.replace("fs_del_", ""))
        channels = get_force_channels()
        if 0 <= idx < len(channels):
            removed = channels.pop(idx)
            set_force_channels(channels)
            await q.edit_message_text(f"✅ Removed `{removed}`", parse_mode="Markdown")

    elif d == "fs_test":
        channels = get_force_channels()
        if not channels:
            return await q.edit_message_text("⚠️ Koi channel nahi.")
        bot_me = await context.bot.get_me()
        results = []
        for ch in channels:
            try:
                bm = await context.bot.get_chat_member(ch, bot_me.id)
                if bm.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                    results.append(f"✅ `{ch}` - Admin ✅")
                else:
                    results.append(f"⚠️ `{ch}` - Bot admin NAHI!")
            except TelegramError as e:
                results.append(f"❌ `{ch}` - {str(e)[:40]}")
        await q.edit_message_text("🧪 **Test**\n\n" + "\n".join(results), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════
async def addcoupon_cmd(update, context):
    if not is_owner(update.effective_user.id): return
    if len(context.args) < 2:
        return await update.message.reply_text("Usage: `/addcoupon CODE %`", parse_mode="Markdown")
    try: pct = int(context.args[1])
    except: return await update.message.reply_text("❌ Invalid.")
    if create_coupon(context.args[0], pct):
        await update.message.reply_text(f"✅ `{context.args[0].upper()}` created")
    else:
        await update.message.reply_text("❌ Exists.")

async def delcoupon_cmd(update, context):
    if not is_owner(update.effective_user.id): return
    if context.args:
        delete_coupon(context.args[0])
        await update.message.reply_text("✅ Deleted.")

async def setprice_cmd(update, context):
    if not is_owner(update.effective_user.id): return
    if len(context.args) != 2:
        return await update.message.reply_text("Usage: `/setprice CODE PRICE`", parse_mode="Markdown")
    try: p = int(context.args[1])
    except: return await update.message.reply_text("❌ Invalid.")
    if not get_file(context.args[0]):
        return await update.message.reply_text("❌ Not found.")
    upd_price(context.args[0], p)
    await update.message.reply_text(f"✅ Price: {p} coins")

async def ban_cmd(update, context):
    if not is_owner(update.effective_user.id): return
    if not context.args: return
    try: uid = int(context.args[0])
    except: return
    ban_user(uid)
    await update.message.reply_text(f"🚫 Banned `{uid}`", parse_mode="Markdown")

async def unban_cmd(update, context):
    if not is_owner(update.effective_user.id): return
    if not context.args: return
    try: uid = int(context.args[0])
    except: return
    unban_user(uid)
    await update.message.reply_text(f"✅ Unbanned `{uid}`", parse_mode="Markdown")

async def help_cmd(update, context):
    await update.message.reply_text(
        "📖 **Help**\n\n"
        "**User:** /start /balance /refer\n\n"
        "**Owner:** /setprice /addcoupon /delcoupon /ban /unban",
        parse_mode="Markdown")

async def done_cmd(update, context):
    await owner_done(update, context)

# ═══════════════════════════════════════════════════════════
#  SMART ROUTER
# ═══════════════════════════════════════════════════════════
async def smart_router(update, context):
    uid = update.effective_user.id
    msg = update.message
    ud = PENDING.get(uid, {})
    txt = msg.text or ""

    if txt == "❌ Cancel":
        return await cancel_handler(update, context)

    # Force sub add
    if is_owner(uid) and ud.get("wait_fs_add") and msg.text:
        PENDING.pop(uid, None)
        raw = msg.text.replace(" ", "")
        new_channels = [c.strip() for c in raw.split(",") if c.strip()]
        if not new_channels:
            return await msg.reply_text("❌ No channels.", reply_markup=owner_kb())

        bot_me = await context.bot.get_me()
        valid = []
        errors = []
        for ch in new_channels:
            try:
                bm = await context.bot.get_chat_member(ch, bot_me.id)
                if bm.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                    valid.append(ch)
                else:
                    errors.append(f"⚠️ `{ch}`: Bot admin NAHI")
            except TelegramError as e:
                errors.append(f"❌ `{ch}`: {str(e)[:50]}")

        if valid:
            current = get_force_channels()
            for v in valid:
                if v not in current: current.append(v)
            set_force_channels(current)

        result_txt = ""
        if valid: result_txt += f"✅ **Added {len(valid)}**\n\n"
        if errors: result_txt += "**Errors:**\n" + "\n".join(errors) + "\n\n"
        result_txt += f"Total: {len(get_force_channels())}"
        return await msg.reply_text(result_txt, parse_mode="Markdown", reply_markup=owner_kb())

    if is_owner(uid):
        if ud.get("wait_qr") and msg.photo:
            PENDING.pop(uid, None)
            set_qr(msg.photo[-1].file_id)
            return await msg.reply_text("✅ QR saved!", reply_markup=owner_kb())

        if ud.get("wait_rate") and msg.text:
            PENDING.pop(uid, None)
            try:
                p = msg.text.split()
                set_coin_rate(int(p[0]), int(p[1]))
                return await msg.reply_text(f"✅ ₹{p[0]}={p[1]}", reply_markup=owner_kb())
            except:
                return await msg.reply_text("❌ Format: `10 100`", parse_mode="Markdown")

        if ud.get("wait_broadcast"):
            PENDING.pop(uid, None)
            users = get_all_users()
            status = await msg.reply_text(f"📢 Sending to {len(users)}...")
            sent = failed = 0
            for u in users:
                try:
                    await msg.copy(u["user_id"]); sent += 1
                except: failed += 1
            await status.edit_text(f"✅ Done!\n✅ {sent} | ❌ {failed}")
            return await msg.reply_text("Panel:", reply_markup=owner_kb())

        if ud.get("wait_addcoins") and msg.text:
            PENDING.pop(uid, None)
            try:
                p = msg.text.split()
                target, amt = int(p[0]), int(p[1])
                add_coins(target, amt)
                await msg.reply_text(f"✅ {amt} added to `{target}`\nBalance: {get_balance(target)}",
                    parse_mode="Markdown", reply_markup=owner_kb())
                try: await context.bot.send_message(target, f"🎁 Admin ne {amt} coins diye!")
                except: pass
                return
            except:
                return await msg.reply_text("❌ Format: `123456789 100`", parse_mode="Markdown")

        if UPLOAD_STATE.get(uid, {}).get("state") == "uploading":
            if msg.document or msg.video or msg.photo or msg.audio:
                return await handle_file_upload(update, context)

    if ud.get("wait_payment") and msg.photo:
        PENDING.pop(uid, None)
        rate = get_coin_rate()
        pid = create_payment(uid, update.effective_user.first_name,
                             rate["rupees"], rate["coins"], msg.photo[-1].file_id)
        await msg.reply_text(f"✅ Request sent!\nID: `{pid}`", parse_mode="Markdown")
        for a in ADMIN_IDS:
            try:
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅", callback_data=f"approve_{pid}"),
                    InlineKeyboardButton("❌", callback_data=f"reject_{pid}")
                ]])
                await context.bot.send_photo(a, msg.photo[-1].file_id,
                    caption=f"💳 Payment\n👤 {update.effective_user.first_name} (`{uid}`)\n"
                            f"₹{rate['rupees']}={rate['coins']}\nID: `{pid}`",
                    reply_markup=kb, parse_mode="Markdown")
            except: pass
        return

    if ud.get("wait_coupon") and msg.text:
        code = msg.text.strip().upper()
        c = get_coupon(code)
        fc = ud.get("coupon_for")
        if not c or not c["active"] or c["used"] >= c["max_uses"]:
            PENDING.pop(uid, None)
            return await msg.reply_text("❌ Invalid/expired coupon.")
        apply_coupon(code)
        PENDING[uid] = {"coupon_discount": c["discount"], "coupon_for": fc}
        await msg.reply_text(f"✅ Applied: **{c['discount']}% OFF**", parse_mode="Markdown")
        if fc:
            fd = get_file(fc)
            if fd:
                price = fd["price"]
                final = max(1, int(price * (100 - c['discount']) / 100))
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(f"✅ Buy for {final} coins", callback_data=f"buy_{fc}")
                ]])
                await msg.reply_text(f"🎫 {final} coins", reply_markup=kb)
        return

    if is_admin(uid) and (msg.document or msg.video or msg.photo or msg.audio):
        if UPLOAD_STATE.get(uid, {}).get("state") == "uploading":
            return await handle_file_upload(update, context)

    if txt and not txt.startswith("/"):
        return await menu_router(update, context)

# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("addcoupon", addcoupon_cmd))
    app.add_handler(CommandHandler("delcoupon", delcoupon_cmd))
    app.add_handler(CommandHandler("setprice", setprice_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))

    app.add_handler(CallbackQueryHandler(buy_callback,
        pattern="^(buy_|approve_|reject_|cancel|buy_coins|ref_show|coupon_|check_joined)"))
    app.add_handler(CallbackQueryHandler(forcesub_callback, pattern="^fs_"))

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, smart_router))

    print(f"🤖 Bot running (SQLite: {DB_FILE})")
    print(f"👑 Owner: {OWNER_ID}")
    print(f"📢 Force Sub: {len(get_force_channels())} channels")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()