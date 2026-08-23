from telegram import Update
from telegram.ext import ContextTypes
from database import get_game, get_night_actions, get_players
from config import OWNER_ID

async def cmd_gamelog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /gamelog in DM (Owner Only) to view secret night logs."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type != "private":
        await update.message.reply_text("🔒 `/gamelog` can ONLY be used in DM with the bot to protect game privacy!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/gamelog <GROUP_CHAT_ID>`")
        return

    try:
        group_chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid Group Chat ID format!")
        return

    game = await get_game(group_chat_id)
    if not game:
        await update.message.reply_text("⚠️ No game found for that Group Chat ID.")
        return

    if user.id != OWNER_ID and user.id != game["owner_id"]:
        await update.message.reply_text("⛔ **ACCESS DENIED**: Only the Bot Owner or Game Host can view secret game logs!")
        return

    players = await get_players(group_chat_id)
    player_map = {p["user_id"]: p["full_name"] for p in players}

    actions = await get_night_actions(group_chat_id, game["phase_round"])
    if not actions:
        await update.message.reply_text(f"📜 No secret night actions recorded for Round {game['phase_round']} yet.")
        return

    log_lines = [f"📜 **SECRET GAME LOG** (Group {group_chat_id} - Round {game['phase_round']}):\n"]
    for act in actions:
        actor_name = player_map.get(act["actor_id"], f"User_{act['actor_id']}")
        target_name = player_map.get(act["target_id"], "Nobody") if act["target_id"] else "None"
        log_lines.append(f"• **{actor_name}** ({act['role']}) ➔ {act['action_type']} ➔ **{target_name}**")

    await update.message.reply_markdown("\n".join(log_lines))
