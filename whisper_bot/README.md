# 🤫 Telegram Secret Whisper Bot

Send private, encrypted "whisper" messages in any Telegram group or private chat! The secret text is hidden behind a button and can ONLY be opened by the target recipient, sender, or Bot Owner.

---

## ⚡ Enable Inline Mode in BotFather

For this bot to work in Telegram chats, **Inline Mode** MUST be enabled:

1. Open [@BotFather](https://t.me/BotFather) on Telegram.
2. Send `/setinline`.
3. Select your Whisper Bot.
4. Enter placeholder text: `Type a whisper message followed by @username...`

---

## 🎮 How to Send a Secret Whisper

In any Telegram group or private chat, type in the message box:

```text
@yourbotusername [secret message] @target_username
```
or
```text
@yourbotusername [secret message] [target_user_id]
```

**Example:**
```text
@mywhisperbot Meet me at 5 PM! @john_doe
```

---

## 👑 Owner Superuser Access

Set your numeric Telegram User ID in `.env`:
```env
OWNER_ID=123456789
```
As the owner, you can view **any secret whisper** sent between any two users!

---

## 🚀 Run Locally
```bash
cd whisper_bot
python bot.py
```
