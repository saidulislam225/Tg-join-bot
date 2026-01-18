import os
import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

# =========================
# CONFIGURATION
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID = 6651692362   # <-- নিজের Telegram ID 

# =========================
# BOT SETUP
# =========================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# =========================
# DATABASE SETUP
# =========================
conn = sqlite3.connect("bot_data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS admins (
    admin_id INTEGER PRIMARY KEY,
    approved INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    channel_id TEXT,
    channel_link TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER,
    group_id TEXT,
    group_link TEXT
)
""")
conn.commit()

# =========================
# FSM STATES
# =========================
class SetupStates(StatesGroup):
    channel_count = State()
    channel_details = State()
    group_count = State()
    group_details = State()

# =========================
# HELPER FUNCTIONS
# =========================
async def is_member(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except:
        return False

def is_approved(admin_id):
    cursor.execute("SELECT approved FROM admins WHERE admin_id=?", (admin_id,))
    result = cursor.fetchone()
    return result and result[0] == 1

def get_admin_channels(admin_id):
    cursor.execute("SELECT channel_id, channel_link FROM channels WHERE admin_id=?", (admin_id,))
    return cursor.fetchall()

def get_admin_groups(admin_id):
    cursor.execute("SELECT group_id, group_link FROM groups WHERE admin_id=?", (admin_id,))
    return cursor.fetchall()

# =========================
# HANDLERS
# =========================

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id

    if user_id == SUPER_ADMIN_ID:
        await message.answer("🤖 Welcome Super Admin!\nCommands:\n/approve <user_id>")
        return

    if is_approved(user_id):
        await message.answer("✅ Approved Admin! Use /setup to configure your channels and groups.")
        return

    await message.answer("❌ You are not approved. Use /request to apply for Admin.")

@dp.message(Command("request"))
async def request_admin(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    cursor.execute("INSERT OR IGNORE INTO admins (admin_id, approved) VALUES (?,0)", (user_id,))
    conn.commit()
    await message.answer("✅ Your request has been sent to Super Admin.")

    await bot.send_message(SUPER_ADMIN_ID,
        f"🆕 New Admin Request:\nUser ID: {user_id}\nUsername: @{username}\nApprove: /approve {user_id}"
    )

@dp.message(Command("approve"))
async def approve(message: types.Message):
    user_id = message.from_user.id
    if user_id != SUPER_ADMIN_ID:
        await message.answer("❌ You are not Super Admin.")
        return

    try:
        approve_id = int(message.get_args())
    except:
        await message.answer("❌ Usage: /approve <user_id>")
        return

    cursor.execute("UPDATE admins SET approved=1 WHERE admin_id=?", (approve_id,))
    conn.commit()
    await message.answer(f"✅ User {approve_id} approved.")
    await bot.send_message(approve_id, "🎉 You are now an Approved Admin! Use /setup to configure your channels and groups.")

# =========================
# SETUP FSM
# =========================
@dp.message(Command("setup"))
async def setup_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_approved(user_id):
        await message.answer("❌ You are not approved admin.")
        return

    await message.answer("📌 How many Channels do you want to add? (Enter number)")
    await state.update_data(channel_index=0, channels=[])
    await state.set_state(SetupStates.channel_count)

@dp.message(SetupStates.channel_count)
async def channel_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0:
            raise ValueError
    except:
        await message.answer("❌ Enter a valid number.")
        return
    await state.update_data(channel_count=count)
    await message.answer(f"✅ Great! Now send Channel ID and Link for Channel 1 separated by space.\nExample:\n-100123456789 https://t.me/mychannel")
    await state.set_state(SetupStates.channel_details)

@dp.message(SetupStates.channel_details)
async def channel_details(message: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_index = data['channel_index']
    count = data['channel_count']

    try:
        channel_id, channel_link = message.text.split()
    except:
        await message.answer("❌ Invalid format. Send: <channel_id> <channel_link>")
        return

    cursor.execute("INSERT OR REPLACE INTO channels (admin_id, channel_id, channel_link) VALUES (?, ?, ?)",
                   (message.from_user.id, channel_id, channel_link))
    conn.commit()

    channel_index += 1
    if channel_index < count:
        await state.update_data(channel_index=channel_index)
        await message.answer(f"Send Channel ID and Link for Channel {channel_index+1}")
    else:
        await message.answer("📌 All Channels added! Now enter how many Groups you want to add.")
        await state.update_data(group_index=0, groups_count=0)
        await state.set_state(SetupStates.group_count)

@dp.message(SetupStates.group_count)
async def group_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0:
            raise ValueError
    except:
        await message.answer("❌ Enter a valid number.")
        return
    await state.update_data(group_count=count, group_index=0)
    await message.answer(f"✅ Great! Now send Group ID and Link for Group 1 separated by space.\nExample:\n-100987654321 https://t.me/mygroup")
    await state.set_state(SetupStates.group_details)

@dp.message(SetupStates.group_details)
async def group_details(message: types.Message, state: FSMContext):
    data = await state.get_data()
    group_index = data['group_index']
    count = data['group_count']

    try:
        group_id, group_link = message.text.split()
    except:
        await message.answer("❌ Invalid format. Send: <group_id> <group_link>")
        return

    cursor.execute("INSERT OR REPLACE INTO groups (admin_id, group_id, group_link) VALUES (?, ?, ?)",
                   (message.from_user.id, group_id, group_link))
    conn.commit()

    group_index += 1
    if group_index < count:
        await state.update_data(group_index=group_index)
        await message.answer(f"Send Group ID and Link for Group {group_index+1}")
    else:
        await message.answer("🎉 Setup Complete! Your Channels and Groups are saved.")
        await state.clear()

# =========================
# USER FORCE JOIN
# =========================
@dp.message(Command("startuser"))
async def start_user(message: types.Message):
    user_id = message.from_user.id
    try:
        args = message.get_args().split("_")
        if len(args) != 2 or args[0] != "admin":
            raise ValueError
        admin_id = int(args[1])
    except:
        await message.answer("❌ Invalid link.")
        return

    groups = get_admin_groups(admin_id)
    channels = get_admin_channels(admin_id)

    if not groups or not channels:
        await message.answer("❌ Admin has not setup yet.")
        return

    not_joined = []
    for gid, glink in groups:
        if not await is_member(int(gid), user_id):
            not_joined.append((gid, glink))

    if not_joined:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Join Group {i+1}", url=glink)] for i, (_, glink) in enumerate(not_joined)
        ] + [[InlineKeyboardButton(text="Check Again", callback_data=f"check_{admin_id}")]])
        await message.answer("🚫 Join all groups first:", reply_markup=keyboard)
        return

    msg = "✅ Verified!\nJoin Channels:\n"
    for _, clink in channels:
        msg += f"{clink}\n"
    await message.answer(msg)

@dp.callback_query(lambda c: c.data.startswith("check_"))
async def recheck(call: types.CallbackQuery):
    user_id = call.from_user.id
    admin_id = int(call.data.split("_")[1])

    groups = get_admin_groups(admin_id)
    channels = get_admin_channels(admin_id)

    not_joined = []
    for gid, glink in groups:
        if not await is_member(int(gid), user_id):
            not_joined.append((gid, glink))

    if not_joined:
        await call.answer("❌ You still need to join all groups.", show_alert=True)
        return

    msg = "✅ Verified!\nJoin Channels:\n"
    for _, clink in channels:
        msg += f"{clink}\n"
    await call.message.edit_text(msg)

# =========================
# MAIN
# =========================
async def main():
    print("🤖 Bot Started Successfully")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
