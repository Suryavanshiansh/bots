import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_game, get_players, set_player_role, log_night_action,
    record_day_vote, disable_last_word, get_user_profile,
    buy_shop_item, consume_inventory_item
)
from game.roles import ROLES_INFO
from game.shop import SHOP_ITEMS

async def cmd_start_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start in DM with interactive main menu."""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type != "private":
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 How to Play", callback_data="menu_rules"), InlineKeyboardButton("🎭 Roles & Powers", callback_data="menu_roles")],
        [InlineKeyboardButton("👤 My Profile", callback_data="menu_profile"), InlineKeyboardButton("🛒 Power-Up Shop", callback_data="menu_shop")],
        [InlineKeyboardButton("💼 My Inventory", callback_data="menu_inventory")],
        [InlineKeyboardButton("➕ Add Bot to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ])

    welcome_text = (
        f"🎩 **WELCOME TO MAFIA SYNDICATE!** 🎩\n\n"
        f"Hello **{user.full_name}**!\n"
        f"I am your official Telegram social deduction game host.\n\n"
        f"💰 **Rewards**: Earn 🪙 **10 coins** per game played and 🪙 **25 coins** per victory!\n"
        f"🛒 Use your coins in the **Shop** to buy single-use Power-Ups (Bulletproof Vest, Megaphone, etc.).\n\n"
        f"👇 Select an option from the menu below!"
    )
    await update.message.reply_markdown(welcome_text, reply_markup=keyboard)

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /profile to view user stats and wallet balance."""
    user = update.effective_user
    profile = await get_user_profile(user.id)

    if not profile:
        games_played = 0
        games_won = 0
        mafia_wins = 0
        town_wins = 0
        neutral_wins = 0
        coins = 50
    else:
        games_played = profile["games_played"]
        games_won = profile["games_won"]
        mafia_wins = profile["mafia_wins"]
        town_wins = profile["town_wins"]
        neutral_wins = profile["neutral_wins"]
        coins = profile["coins"]

    win_rate = round((games_won / games_played * 100), 1) if games_played > 0 else 0.0

    profile_text = (
        f"👤 **PLAYER PROFILE: {user.full_name}**\n"
        f"🏷️ **Username**: @{user.username if user.username else 'N/A'}\n"
        f"🆔 **ID**: `{user.id}`\n\n"
        f"🪙 **WALLET BALANCE**: **{coins} Coins**\n\n"
        f"📊 **GAME STATISTICS**:\n"
        f"• **Games Played**: {games_played}\n"
        f"• **Games Won**: {games_won} ({win_rate}% Win Rate)\n\n"
        f"🏆 **WIN BREAKDOWN**:\n"
        f"🔴 **Mafia Wins**: {mafia_wins}\n"
        f"🔵 **Town Wins**: {town_wins}\n"
        f"🟡 **Neutral Wins**: {neutral_wins}"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(profile_text, parse_mode="Markdown")
    else:
        await update.message.reply_markdown(profile_text)

async def cmd_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /shop to browse and purchase power-ups."""
    user = update.effective_user
    profile = await get_user_profile(user.id)
    coins = profile["coins"] if profile else 50

    buttons = []
    text_lines = [f"🛒 **MAFIA SYNDICATE POWER-UP SHOP**\nYour Balance: 🪙 **{coins} Coins**\n"]

    for key, item in SHOP_ITEMS.items():
        text_lines.append(f"• **{item['name']}** — 🪙 **{item['price']} Coins**")
        text_lines.append(f"  _{item['description']}_\n")
        buttons.append([InlineKeyboardButton(f"Buy {item['name']} (🪙 {item['price']})", callback_data=f"buypup_{key}")])

    full_text = "\n".join(text_lines)
    keyboard = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.edit_message_text(full_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_markdown(full_text, reply_markup=keyboard)

async def callback_buy_powerup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles buying power-up callbacks."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    item_key = query.data.replace("buypup_", "")

    if item_key not in SHOP_ITEMS:
        await query.edit_message_text("❌ Unknown item.")
        return

    item = SHOP_ITEMS[item_key]
    success, msg = await buy_shop_item(user.id, item["name"], item["price"])
    await query.edit_message_text(msg, parse_mode="Markdown")

async def cmd_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /inventory to view owned power-ups."""
    user = update.effective_user
    profile = await get_user_profile(user.id)

    if not profile or not profile["inventory"]:
        inv_dict = {}
    else:
        inv_dict = json.loads(profile["inventory"] or "{}")

    if not inv_dict:
        text = "💼 **YOUR INVENTORY IS EMPTY!**\nUse `/shop` to buy power-ups using your earned coins!"
    else:
        lines = ["💼 **YOUR OWNED POWER-UPS**:\n"]
        for key, count in inv_dict.items():
            lines.append(f"• **{key}**: x{count}")
        lines.append("\nℹ️ _Power-ups are automatically equipped during active games!_")
        text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_markdown(text)

async def cmd_roles_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /roles to view details of all roles."""
    text_lines = ["🎭 **MAFIA SYNDICATE ROLES & POWERS** 🎭\n"]
    for key, info in ROLES_INFO.items():
        text_lines.append(f"• **{info['name']}** ({info['team'].value})")
        text_lines.append(f"  _{info['description']}_\n")

    full_text = "\n".join(text_lines)
    if update.callback_query:
        await update.callback_query.edit_message_text(full_text, parse_mode="Markdown")
    else:
        await update.message.reply_markdown(full_text)

async def callback_menu_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Renders How to Play guide via menu button."""
    query = update.callback_query
    await query.answer()

    rules_text = (
        f"📖 **HOW TO PLAY MAFIA SYNDICATE** 📖\n\n"
        f"1️⃣ **Start a Lobby**: Use `/game` in any Telegram Group chat.\n"
        f"2️⃣ **Join the Game**: Click the Join button to start a DM with the bot.\n"
        f"3️⃣ **Secret Roles**: The bot DMs each player their secret role.\n"
        f"4️⃣ **Night Phase**: Special roles receive secret DM buttons for night actions.\n"
        f"5️⃣ **Day Phase & Discussion**: Morning casualties announced in group chat.\n"
        f"6️⃣ **Secret DM Day Voting**: Players vote in DM via inline keyboard.\n"
        f"7️⃣ **Dead Player Last Words**: Eliminated players get 1 DM chance to send a final message.\n"
        f"8️⃣ **Earn Coins & Power-Ups**: Earn 🪙 10 coins per game + 🪙 25 per win to buy Shop items!\n\n"
        f"🏆 **Win Conditions**:\n"
        f"• **Town Wins**: All Mafia & Evil forces eliminated.\n"
        f"• **Mafia Wins**: Mafia reaches numerical parity with Town.\n"
        f"• **Jester Wins**: Gets lynched by the group during Day vote."
    )
    await query.edit_message_text(rules_text, parse_mode="Markdown")

async def callback_owner_role_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    parts = data.split("_")
    opt = parts[1]
    chat_id = int(parts[2])

    from handlers.group_handlers import assign_random_roles_and_start

    if opt == "rand":
        await query.edit_message_text("🎲 Random roles will be assigned to all players!")
        await assign_random_roles_and_start(context, chat_id)
    else:
        players = await get_players(chat_id)
        context.user_data[f"custom_assign_{chat_id}"] = {
            "unassigned_players": [p["user_id"] for p in players],
            "assignments": {}
        }
        await show_custom_role_picker(query, context, chat_id)

async def show_custom_role_picker(query, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    players = await get_players(chat_id)
    player_map = {p["user_id"]: p for p in players}

    session = context.user_data.get(f"custom_assign_{chat_id}")
    if not session or not session["unassigned_players"]:
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
    query = update.callback_query
    await query.answer()
    data = query.data

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
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

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

    await log_night_action(chat_id, round_num, user.id, role, target_id, action_type)

    if role == "DETECTIVE":
        if target_id in player_map:
            target_player = player_map[target_id]
            target_role = target_player["role"]
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
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

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

    vote_weight = 2 if voter_p["role"] == "MAYOR" else 1
    await record_day_vote(chat_id, round_num, user.id, target_id, weight=vote_weight)

    player_map = {p["user_id"]: p for p in voter_players}
    target_name = player_map[target_id]["full_name"] if target_id in player_map else "Abstain"

    mayor_note = " (Mayor x2 Weight Applied)" if vote_weight == 2 else ""
    await query.edit_message_text(f"✅ Your secret vote for **{target_name}** has been recorded!{mayor_note}")

async def handle_dm_last_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if not text or text.startswith("/"):
        return

    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM players WHERE user_id = ? AND can_last_word = 1", (user.id,)
        ) as cursor:
            dead_records = await cursor.fetchall()

    if not dead_records:
        return

    for rec in dead_records:
        chat_id = rec["chat_id"]
        msg_text = f"☠️ **LAST WORDS FROM THE GRAVE** ({rec['full_name']}):\n💬 _\"{text}\"_"
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg_text)
            await disable_last_word(chat_id, user.id)
            await update.message.reply_text("🕊️ Your last words have been delivered to the group!")
        except Exception:
            pass
