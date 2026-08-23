# 🎭 Telegram Mafia Game Bot

A feature-packed, multi-role Telegram Mafia party game bot with custom owner role selection, secret DM inline-keyboard day voting, dead-player DM last words forwarding, admin log privacy, and 10 dynamic roles.

---

## 🌟 Key Features

- **TrueMafiaBot Style Commands**: Compatible with `/game`, `/extend`, `/start`, `/stop`, `/status`, `/gamelog`.
- **Owner Role Assignment**:
  - **Random Roles**: One-click auto-balanced role generation.
  - **Custom Assign**: Owner manually picks who gets which role via interactive DM panel.
- **Secret DM Day Voting**: Day voting takes place inside each player's DM using inline buttons to prevent bandwagoning.
- **Mayor Voting Weight**: The Mayor's DM vote automatically counts as 2 votes in the tally.
- **Dead Player Last Words**: Eliminated players get 1 opportunity via DM to send a final message broadcast to the group (`☠️ Last Words from the Grave: "..."`).
- **Admin Log Privacy**: Secret night actions and player roles are restricted from group admins during gameplay to prevent cheating. Only the Host/Owner can inspect logs in DM.
- **10 Dynamic Roles**:
  - 🔴 **Mafia Team**: Mafia Godfather/Don (Innocent on check), Mafia Goon
  - 🔵 **Town Team**: Detective, Doctor, Vigilante (2 shots), Mayor (2x vote), Sergeant (Backup Detective), Villager
  - 🟡 **Neutral Team**: Jester (Wins if lynched), Serial Killer (Solo murderer)

---

## 🛠️ Installation & Setup

1. **Clone or Navigate to Directory**:
   ```bash
   cd f:\bots\mafia_bot
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file from `.env.example`:
   ```ini
   BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyZ
   OWNER_ID=123456789
   REGISTRATION_TIME=60
   EXTEND_TIME=60
   NIGHT_TIME=60
   DAY_VOTE_TIME=90
   ```

4. **Run the Bot**:
   ```bash
   python main.py
   ```

---

## 📜 Group & DM Commands

| Command | Location | Description |
|---------|----------|-------------|
| `/game` | Group | Open a new game lobby for registration |
| `/extend` | Group | Extend registration time (+60s) |
| `/start` | Group | Finish registration and begin the game |
| `/stop` | Group | Cancel registration or stop active game |
| `/status` | Group/DM | View list of alive and dead players |
| `/gamelog <CHAT_ID>` | DM (Owner Only) | Inspect secret night action logs |
