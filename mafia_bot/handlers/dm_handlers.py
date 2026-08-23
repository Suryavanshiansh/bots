from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_game, get_players, set_player_role, log_night_action,
    record_day_vote, disable_last_word
)
from game.roles import ROLES_INFO
from game.engine import process_night_actions
from game.setup import get_balanced_roles

async def callback_owner_role_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles owner choice: Random Roles vs Custom Roles."""
    query = update.callback_query
    await query.answer()
    data = query.data # roleopt_rand_CHATID or roleopt_cust_CHATID

    parts = data.split("_")
    opt = parts[1]
    chat_id = int(parts[2])

    from handlers.group_handlers import assign_random_roles_and_start

    if opt == "rand":
        await query.edit_message_text("🎲 Random roles will be assigned to all players!")
        await assign_random_roles_and_start(context, chat_id)
    else:
        # Custom role assignment panel
        players = await get_players(chat_id)
        context.user_data[f"custom_assign_{chat_id}"] = {
            "unassigned_players": [p["user_id"] for p in players],
            "assignments": {}
        }
        await show_custom_role_picker(query, context, chat_id)

async def show_custom_role_picker(query, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Renders custom role assignment buttons for owner."""
    players = await get_players(chat_id)
    player_map = {p["user_id"]: p for p in players}

    session = context.user_data.get(f"custom_assign_{chat_id}")
    if not session or not session["unassigned_players"]:
        # Done assigning! Apply custom roles & start night
        assignments = session["assignments"]
        for uid, role in assignments.items():
            await set_player_role(chat_id, uid, role)
            try:
                role_info = ROLES_INFO[role]
                dm_text = (
                    f"🎭 **YOUR SECRET ROLE**: {role_info['name']}\n"
                    f"**Team**: {role_info['team'].value}\n\n"
                    f"ℹ️ {role_info['description']}"
                )
                await context.bot.send_message(chat_id=uid, text=dm_text)
            except Exception:
                pass

        await query.edit_message_text("✅ All custom roles assigned! Starting game...")
        from handlers.group_handlers import start_night_phase
        await start_night_phase(context, chat_id, round_num=1)
        return

    target_uid = session["unassigned_players"][0]
    target_player = player_map[target_uid]

    roles_list = list(ROLES_INFO.keys())
    buttons = []
    for r_key in roles_list:
        r_name = ROLES_INFO[r_key]["name"]
        cb_data = f"customset_{chat_id}_{target_uid}_{r_key}"
        buttons.append([InlineKeyboardButton(r_name, callback_data=cb_data)])

    keyboard = InlineKeyboardMarkup(buttons)
    text = f"🎭 **CUSTOM ROLE ASSIGNMENT**\nSelect role for **{target_player['full_name']}** ({len(session['assignments']) + 1}/{len(players)}):"

    if hasattr(query, "edit_message_text"):
        await query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        await query.message.reply_text(text=text, reply_markup=keyboard)

async def callback_custom_role_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles owner selection of a role for a specific player."""
    query = update.callback_query
    await query.answer()
    data = query.data # customset_CHATID_USERID_ROLE

    parts = data.split("_")
    chat_id = int(parts[1])
    target_uid = int(parts[2])
    role_key = parts[3]

    session = context.user_data.get(f"custom_assign_{chat_id}")
    if session:
        session["assignments"][target_uid] = role_key
        if target_uid in session["unassigned_players"]:
            session["unassigned_players"].remove(target_uid)

    await show_custom_role_picker(query, context, chat_id)

async def callback_night_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles secret night actions (Doctor, Mafia, Detective, Vigilante, SK)."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data # nact_CHATID_ROUND_ROLE_TARGETID

    parts = data.split("_")
    chat_id = int(parts[1])
    round_num = int(parts[2])
    role = parts[3]
    target_id = int(parts[4])

    game = await get_game(chat_id)
    if not game or game["state"] != "NIGHT" or game["phase_round"] != round_num:
        await query.edit_message_text("⚠️ This night phase has ended!")
        return

    players = await get_players(chat_id, alive_only=True)
    player_map = {p["user_id"]: p for p in players}

    action_type = "UNKNOWN"
    if role in ("GODFATHER", "MAFIA", "SERIAL_KILLER"):
        action_type = "KILL"
    elif role == "DOCTOR":
        action_type = "SAVE"
    elif role == "VIGILANTE":
        action_type = "SHOOT"
    elif role == "DETECTIVE":
        action_type = "INVESTIGATE"

    # Save to Database
    await log_night_action(chat_id, round_num, user.id, role, target_id, action_type)

    # Special logic for Detective instant DM feedback
    if role == "DETECTIVE":
        if target_id in player_map:
            target_player = player_map[target_id]
            target_role = target_player["role"]
            # Godfather appears Innocent!
            if target_role == "GODFATHER":
                alignment = "INNOCENT 🔵"
            elif target_role in ("MAFIA", "SERIAL_KILLER"):
                alignment = "MAFIA / EVIL 🔴"
            else:
                alignment = "INNOCENT 🔵"

            await query.edit_message_text(
                f"🔍 **INVESTIGATION RESULT**\n"
                f"Player: **{target_player['full_name']}**\n"
                f"Result: **{alignment}**"
            )
            return

    target_name = player_map[target_id]["full_name"] if target_id in player_map else "Nobody (Skipped)"
    await query.edit_message_text(f"✅ Your night choice (**{target_name}**) has been recorded secretly.")

async def callback_day_vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles secret Day votes cast via DM."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data # dvote_CHATID_ROUND_TARGETID

    parts = data.split("_")
    chat_id = int(parts[1])
    round_num = int(parts[2])
    target_id = int(parts[3])

    game = await get_game(chat_id)
    if not game or game["state"] != "DAY_VOTE" or game["phase_round"] != round_num:
        await query.edit_message_text("⚠️ This voting phase has ended!")
        return

    voter_players = await get_players(chat_id, alive_only=True)
    voter_p = next((p for p in voter_players if p["user_id"] == user.id), None)
    if not voter_p:
        await query.edit_message_text("❌ Only alive players can vote!")
        return

    # Check Mayor vote weight multiplier (2x)
    vote_weight = 2 if voter_p["role"] == "MAYOR" else 1

    await record_day_vote(chat_id, round_num, user.id, target_id, weight=vote_weight)

    player_map = {p["user_id"]: p for p in voter_players}
    target_name = player_map[target_id]["full_name"] if target_id in player_map else "Abstain"

    mayor_note = " (Mayor x2 Weight Applied)" if vote_weight == 2 else ""
    await query.edit_message_text(f"✅ Your secret vote for **{target_name}** has been recorded!{mayor_note}")

async def handle_dm_last_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text messages in DM from dead players to broadcast as Last Words."""
    user = update.effective_user
    text = update.message.text

    if not text or text.startswith("/"):
        return

    # Search across active games for dead player with last word rights
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE user_id = ? AND can_last_word = 1", (user.id,)
        ) as cursor:
            dead_records = await cursor.fetchall()

    if not dead_records:
        return # User is not dead or already sent last word

    for rec in dead_records:
        chat_id = rec["chat_id"]
        # Broadcast to Group
        msg_text = f"☠️ **LAST WORDS FROM THE GRAVE** ({rec['full_name']}):\n💬 _\"{text}\"_"
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg_text)
            await disable_last_word(chat_id, user.id)
            await update.message.reply_text("🕊️ Your last words have been delivered to the group!")
        except Exception:
            pass
