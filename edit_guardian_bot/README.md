# 🛡️ Edit Guardian Telegram Bot

A feature-complete Telegram moderation bot built in Python (`python-telegram-bot` v21+) designed to protect Telegram groups by deleting edited messages, restricting/auto-deleting unapproved media and adult/NSFW stickers, and providing separate member authorization commands.

---

## 🌟 Key Features

1. **🚫 Edited Message Deletion**: Automatically detects and deletes edited messages sent by unapproved users in group chats to maintain discussion integrity and transparency.
2. **🔞 NSFW & Sticker Moderation**:
   - Detects explicit/18+ adult stickers sent by unapproved users and deletes them immediately.
   - `/sticker_guard <nsfw_only|all|off>`: Choose sticker moderation rules.
3. **⏱️ Configurable Media Auto-Delete**:
   - `/set_delay <minutes>`: Automatically deletes photos, videos, animations, and audio sent by unapproved users after a set delay (default 60 mins, or 0 for instant deletion).
4. **🔐 Dual Member Authentication Commands**:
   - **Edit Authorization**: `/auth_edit` & `/unauth_edit` grant or revoke message editing permissions for trusted members.
   - **Sticker/Media Authorization**: `/auth_sticker` & `/unauth_sticker` grant or revoke full sticker and media posting privileges.
   - `/list_approved`: Lists all authorized group members.

---

## 🤖 Bot Description for @BotFather

### **Short Description / What can this bot do?:**
> 🛡️ A powerful edit guardian bot designed to protect your Telegram group by managing edited messages, auto-deleting media, and removing adult/18+ NSFW stickers. Features dual member authentication for trusted users!

---

### **Full Description / How to Use Bot (Under 512 characters for @BotFather -> /setdescription):**
```text
👋 Welcome to Edit Guardian Bot!

🛡️ WHAT I DO:
• Deletes edited messages to maintain transparency.
• Removes 18+ NSFW stickers from unapproved users.
• Auto-deletes media/stickers after set delay.

📖 HOW TO USE:
1. Add me to your group.
2. Make me Admin with 'Delete Messages' permission.
3. Use /auth_edit & /auth_sticker to approve users.

⚙️ COMMANDS:
• /set_delay <min> - Set delete timer
• /get_delay - View settings
• /auth_edit - Authorize user edits
• /auth_sticker - Authorize user media
```

---

## 🚀 Setup & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Edit `.env` and set your Telegram Bot Token from [@BotFather](https://t.me/BotFather):
```env
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE
OWNER_ID=YOUR_TELEGRAM_USER_ID
UPDATE_CHANNEL_URL=https://t.me/your_channel
SUPPORT_CHAT_URL=https://t.me/your_support_group
```

### 3. Run the Bot
On Windows:
Double-click `run_bot.bat` or run:
```bash
python bot.py
```

---

## ⚙️ Group Admin Setup & Permissions

1. Add your bot to your Telegram Group.
2. Grant Administrator rights with **Delete Messages** (`can_delete_messages`) enabled.
3. Use `/get_delay` in the group to verify status.
