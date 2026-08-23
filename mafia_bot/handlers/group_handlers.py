import asyncio
import time
import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_game, create_game, set_game_state, add_player,
    get_players, delete_game, set_player_role, extend_game_timer
)
from config import REGISTRATION_TIME, EXTEND_TIME, NIGHT_TIME, DAY_VOTE_TIME, OWNER_ID
from game.setup import get_balanced_roles
from game.roles import ROLES_INFO
from game.engine import check_win_condition, process_night_actions, process_day_votes

logger = logging.getLogger(__name__)

async def check_and_clean_stale_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """If a lobby timer has expired, auto-trigger start sequence or cleanup."""
    game = await get_game(chat_id)
    if not game:
        return False

    now = int(time.time())
    if game["state"] == "LOBBY" and game["expires_at"] <= now:
        players = await get_players(chat_id)
        if len(players) >= 3:
            await start_game_sequence(context, chat_id)
            return True
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Registration time expired! Need at least 3 players to start (joined: {len(players)}).\nLobby closed. Use `/game` to try again!"
            )
            await delete_game(chat_id)
            return True

    return False

async def cmd_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /game or /game@bot to open a game lobby in group."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("❌ Please use `/game` in a Telegram Group chat to start a Mafia game!")
        return

    stale_handled = await check_and_clean_stale_game(context, chat.id)
    if stale_handled:
        game = None
    else:
        game = await get_game(chat.id)

    if game and game["state"] != "ENDED":
        now = int(time.time())
        rem = max(0, game["expires_at"] - now)
        await update.message.reply_markdown(
            f"⚠️ A game match is already active in this group!\n"
            f"**Phase**: `{game['state']}`\n"
            f"⏱️ **Time Left**: **{rem} seconds**\n"
            f"Use `/status` to check players, `/start` to start now, or `/stop` to cancel."
        )
        return

    await create_game(chat.id, user.id, duration_sec=REGISTRATION_TIME)

    bot_username = context.bot.username
    join_url = f"https://t.me/{bot_username}?start=join_{chat.id}"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Click Here to Join Game", url=join_url)]
    ])

    msg = (
        f"🎭 **MAFIA SYNDICATE LOBBY STARTED!** 🎭\n\n"
        f"👑 **Host**: {user.full_name}\n"
        f"⏱️ **Registration Time**: {REGISTRATION_TIME} seconds\n"
        f"👥 **Min Players**: 3 Players\n\n"
        f"👉 Click the button below to **start DM with bot & join**!\n"
        f"Use `/start` to start immediately, `/extend` to add time, `/time` for countdown, or `/stop` to cancel."
    )
    await update.message.reply_markdown(msg, reply_markup=reply_markup)

    if context.job_queue:
        context.job_queue.run_once(
            callback=auto_start_timer,
            when=REGISTRATION_TIME,
            chat_id=chat.id,
            name=f"registration_{chat.id}"
        )

async def auto_start_timer(context: ContextTypes.DEFAULT_TYPE):
    """Auto-start callback when registration timer expires."""
    chat_id = context.job.chat_id
    await check_and_clean_stale_game(context, chat_id)

async def cmd_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /extend to add registration time."""
    chat = update.effective_chat
    game = await get_game(chat.id)
    if not game or game["state"] != "LOBBY":
        await update.message.reply_text("⚠️ No active registration lobby to extend!")
        return

    rem_time = await extend_game_timer(chat.id, extra_sec=EXTEND_TIME)

    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(f"registration_{chat.id}")
        for j in current_jobs:
            j.schedule_removal()

        context.job_queue.run_once(
            callback=auto_start_timer,
            when=rem_time,
            chat_id=chat.id,
            name=f"registration_{chat.id}"
        )
    await update.message.reply_text(f"⏱️ Registration time extended! **{rem_time} seconds remaining**.")

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /time to check how much time is left in current phase."""
    chat = update.effective_chat
    await check_and_clean_stale_game(context, chat.id)

    game = await get_game(chat.id)
    if not game or game["state"] == "ENDED":
        await update.message.reply_text("⚠️ No active game in progress.")
        return

    now = int(time.time())
    rem = max(0, game["expires_at"] - now)
    await update.message.reply_markdown(
        f"⏱️ **TIME REMAINING**\n"
        f"**Phase**: `{game['state']}` (Round {game['phase_round']})\n"
        f"⏳ **Time Left**: **{rem} seconds**"
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /start in group (or deep link start in DM)."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        if context.args and context.args[0].startswith("join_"):
            try:
                target_chat_id = int(context.args[0].replace("join_", ""))
                game = await get_game(target_chat_id)
                if not game or game["state"] != "LOBBY":
                    await update.message.reply_text("❌ This game lobby is no longer accepting new players!")
                    return

                players = await get_players(target_chat_id)
                if any(p["user_id"] == user.id for p in players):
                    await update.message.reply_text("✅ You have already joined this game lobby!")
                    return

                await add_player(target_chat_id, user.id, user.username, user.full_name)
                players_now = await get_players(target_chat_id)
                await update.message.reply_text(f"🎉 You successfully joined the Mafia lobby! Total players: {len(players_now)}")

                now = int(time.time())
                rem = max(0, game["expires_at"] - now)
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=f"👤 **{user.full_name}** joined the game! Total registered: **{len(players_now)}** (⏱️ {rem}s left)"
                )
            except Exception:
                await update.message.reply_text("❌ Invalid join request.")
            return
        else:
            from handlers.dm_handlers import cmd_start_dm
            await cmd_start_dm(update, context)
            return

    if chat.type != "private":
        game = await get_game(chat.id)
        if not game or game["state"] != "LOBBY":
            await update.message.reply_text("⚠️ No active lobby to start!")
            return

        players = await get_players(chat.id)
        if len(players) < 3:
            await update.message.reply_text(f"⚠️ Need at least 3 players to start! Current joined: {len(players)}")
            return

        if context.job_queue:
            current_jobs = context.job_queue.get_jobs_by_name(f"registration_{chat.id}")
            for j in current_jobs:
                j.schedule_removal()

        await start_game_sequence(context, chat.id)

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /stop to cancel active game."""
    chat = update.effective_chat
    user = update.effective_user

    game = await get_game(chat.id)
    if not game:
        await update.message.reply_text("⚠️ No active game in this chat.")
        return

    if user.id != game["owner_id"] and user.id != OWNER_ID:
        member = await chat.get_member(user.id)
        if member.status not in ("administrator", "creator"):
            await update.message.reply_text("❌ Only the Game Host, Bot Owner, or Group Admins can stop the game!")
            return

    if context.job_queue:
        for prefix in ["registration", "night", "day_vote"]:
            jobs = context.job_queue.get_jobs_by_name(f"{prefix}_{chat.id}")
            for j in jobs:
                j.schedule_removal()

    await delete_game(chat.id)
    await update.message.reply_text("🛑 **The Mafia game has been canceled.**")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /status to display current game state, alive player list, and role summary."""
    chat = update.effective_chat
    await check_and_clean_stale_game(context, chat.id)

    game = await get_game(chat.id)
    if not game:
        await update.message.reply_text("⚠️ No active game in this chat. Use `/game` to start one!")
        return

    players = await get_players(chat.id)
    alive_players = [p for p in players if p["is_alive"]]

    alive_lines = []
    role_counts = {}
    for idx, p in enumerate(alive_players, start=1):
        alive_lines.append(f"{idx}. {p['full_name']}")
        role_name = ROLES_INFO.get(p["role"], {}).get("name", "Villager")
        role_counts[role_name] = role_counts.get(role_name, 0) + 1

    summary_roles = []
    for r_name, count in role_counts.items():
        summary_roles.append(f"{r_name} - {count}" if count > 1 else f"{r_name}")

    now = int(time.time())
    rem = max(0, game["expires_at"] - now)

    msg = (
        f"📋 **PLAYERS ALIVE** ({len(alive_players)}):\n" +
        ("\n".join(alive_lines) if alive_lines else "None") + "\n\n"
        f"🎭 **Some of them are**:\n" +
        (", ".join(summary_roles) if summary_roles else "Unknown") + "\n"
        f"**Total**: {len(alive_players)} people.\n\n"
        f"⏱️ **Phase**: `{game['state']}` ({rem}s left)"
    )
    await update.message.reply_markdown(msg)

async def start_game_sequence(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Only Bot Owner gets role selection choice in DM; all other hosts auto-randomize immediately."""
    game = await get_game(chat_id)
    players = await get_players(chat_id)
    host_id = game["owner_id"]

    if len(players) < 3:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Cannot start game! Minimum 3 players required (currently joined: {len(players)})."
        )
        return

    # Strictly check if host_id is the Bot Owner (OWNER_ID)
    if host_id == OWNER_ID or any(p["user_id"] == OWNER_ID for p in players):
        await set_game_state(chat_id, "ROLE_ASSIGNMENT", duration_sec=60)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Assign Random Roles", callback_data=f"roleopt_rand_{chat_id}")],
            [InlineKeyboardButton("🎭 Custom Assign Roles", callback_data=f"roleopt_cust_{chat_id}")]
        ])
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=(
                    f"👑 **BOT OWNER CONTROL PANEL** (Group: {chat_id})\n"
                    f"Total joined players: **{len(players)}**.\n\n"
                    f"How would you like to assign secret roles for this match?"
                ),
                reply_markup=keyboard
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎭 **Game is starting!** Waiting for Bot Owner to select role assignment in DM..."
            )
            return
        except Exception as e:
            logger.warning(f"Could not DM Owner {OWNER_ID}: {e}")

    # For all normal hosts / non-owners: Auto-assign random roles immediately
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎭 **GAME IS STARTING!** Assigning secret roles to {len(players)} players via DM..."
    )
    await assign_random_roles_and_start(context, chat_id)

async def assign_random_roles_and_start(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Assigns random roles to ALL players and starts Night Phase."""
    players = await get_players(chat_id)
    balanced_roles = get_balanced_roles(len(players))

    for p, role in zip(players, balanced_roles):
        await set_player_role(chat_id, p["user_id"], role)
        role_info = ROLES_INFO.get(role, {})
        role_name = role_info.get("name", role)
        role_team = role_info.get("team", {}).value if hasattr(role_info.get("team"), "value") else "Town"
        role_desc = role_info.get("description", "")

        dm_text = (
            f"🎭 **YOUR SECRET ROLE**: {role_name}\n"
            f"**Team**: {role_team}\n\n"
            f"ℹ️ {role_desc}"
        )
        try:
            await context.bot.send_message(chat_id=p["user_id"], text=dm_text)
        except Exception as e:
            logger.warning(f"Could not send role DM to user {p['user_id']}: {e}")

    await start_night_phase(context, chat_id, round_num=1)

async def start_night_phase(context: ContextTypes.DEFAULT_TYPE, chat_id: int, round_num: int):
    """Transitions game to Night Phase, sends tailored atmospheric night status messages, and DM action panels."""
    await set_game_state(chat_id, "NIGHT", phase_round=round_num, duration_sec=NIGHT_TIME)
    players = await get_players(chat_id, alive_only=True)
    roles_present = set(p["role"] for p in players)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🌙 **NIGHT {round_num} HAS FALLEN...** 🌙\n\n"
            f"The city sleeps as darkness settles over the streets...\n"
            f"⏱️ **Night Duration**: {NIGHT_TIME} seconds"
        )
    )

    if "GODFATHER" in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="🎩 **Don is giving secret orders to the Mafia...**")

    if "MAFIA" in roles_present and "GODFATHER" not in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="🔴 **Mafia is choosing a target...**")

    if "DOCTOR" in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="💉 **Doctor went on night duty...**")

    if "DETECTIVE" in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="🕵️ **Detective is looking for the criminals...**")

    if "VIGILANTE" in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="🔫 **Vigilante is loading their gun in the dark...**")

    if "SERIAL_KILLER" in roles_present:
        await asyncio.sleep(1)
        await context.bot.send_message(chat_id=chat_id, text="🔪 **Serial Killer is lurking in the shadows...**")

    for p in players:
        role = p["role"]
        user_id = p["user_id"]
        role_info = ROLES_INFO.get(role, {})

        if not role_info or not role_info.get("has_night_action"):
            continue

        targets_buttons = []
        for target in players:
            if role in ("GODFATHER", "MAFIA") and target["role"] in ("GODFATHER", "MAFIA"):
                continue
            if role == "DETECTIVE" and target["user_id"] == user_id:
                continue

            btn_text = f"🎯 {target['full_name']}"
            cb_data = f"nact_{chat_id}_{round_num}_{role}_{target['user_id']}"
            targets_buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

        targets_buttons.append([InlineKeyboardButton("⏭️ Skip Action Tonight", callback_data=f"nact_{chat_id}_{round_num}_{role}_0")])

        if targets_buttons:
            keyboard = InlineKeyboardMarkup(targets_buttons)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🌙 **NIGHT {round_num} ACTION**\n{role_info.get('action_prompt', 'Select target:')}",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Could not send action DM to {user_id}: {e}")

    if context.job_queue:
        context.job_queue.run_once(
            callback=end_night_phase_job,
            when=NIGHT_TIME,
            chat_id=chat_id,
            name=f"night_{chat_id}"
        )

async def end_night_phase_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue wrapper for ending night phase when timer expires."""
    chat_id = context.job.chat_id
    await trigger_end_night_phase(context, chat_id)

async def trigger_end_night_phase(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Processes night actions, announces casualties with role summary, and moves to Day Voting."""
    try:
        game = await get_game(chat_id)
        if not game or game["state"] != "NIGHT":
            return

        round_num = game["phase_round"]
        result = await process_night_actions(chat_id, round_num)

        deaths = result["deaths"]
        death_text = ""
        if deaths:
            names = []
            for d in deaths:
                r_info = ROLES_INFO.get(d["role"], {})
                r_title = r_info.get("name", d["role"])
                names.append(f"💀 **{d['full_name']}** ({r_title})")
            death_text = "The morning comes with terrible news... The following were eliminated during the night:\n" + "\n".join(names)
            for d in deaths:
                try:
                    await context.bot.send_message(
                        chat_id=d["user_id"],
                        text="☠️ **YOU WERE KILLED!** Send your last message in this DM to broadcast it to the group."
                    )
                except Exception:
                    pass
        else:
            death_text = "☀️ Morning breaks! Miraculously, nobody died during the night!"

        players = await get_players(chat_id, alive_only=True)
        alive_lines = [f"{idx}. {p['full_name']}" for idx, p in enumerate(players, start=1)]

        role_counts = {}
        for p in players:
            r_name = ROLES_INFO.get(p["role"], {}).get("name", "Villager")
            role_counts[r_name] = role_counts.get(r_name, 0) + 1

        summary_roles = [f"{r_name} - {count}" if count > 1 else f"{r_name}" for r_name, count in role_counts.items()]

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"☀️ **DAY {round_num} BREAKS** ☀️\n\n"
                f"{death_text}\n\n"
                f"📋 **Players alive** ({len(players)}):\n" +
                ("\n".join(alive_lines) if alive_lines else "None") + "\n\n"
                f"🎭 **Some of them are**:\n" +
                (", ".join(summary_roles) if summary_roles else "Unknown") + "\n"
                f"**Total**: {len(players)} people.\n\n"
                f"Now it's time to discuss tonight's events to figure out who the Mafia is!"
            )
        )

        win_res = await check_win_condition(chat_id)
        if win_res:
            await context.bot.send_message(chat_id=chat_id, text=win_res["text"])
            await set_game_state(chat_id, "ENDED")
            return

        await start_day_voting_phase(context, chat_id, round_num)
    except Exception as e:
        logger.error(f"Error in trigger_end_night_phase: {e}\n{traceback.format_exc()}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Game Engine Error: {e}. Moving to Day voting...")
        await start_day_voting_phase(context, chat_id, round_num if 'round_num' in locals() else 1)

async def start_day_voting_phase(context: ContextTypes.DEFAULT_TYPE, chat_id: int, round_num: int):
    """Starts Day voting phase by sending DM inline keyboards to alive players."""
    try:
        await set_game_state(chat_id, "DAY_VOTE", phase_round=round_num, duration_sec=DAY_VOTE_TIME)
        players = await get_players(chat_id, alive_only=True)

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🗳️ **DAY {round_num} LYNCH VOTING IS NOW OPEN!** 🗳️\n\n"
                f"All alive players: Check your DMs from the bot to cast your secret vote!\n"
                f"⏱️ **Voting Time**: {DAY_VOTE_TIME} seconds"
            )
        )

        for p in players:
            voter_id = p["user_id"]
            vote_buttons = []
            for candidate in players:
                if candidate["user_id"] == voter_id:
                    continue
                btn_text = f"⚖️ Vote to lynch {candidate['full_name']}"
                cb_data = f"dvote_{chat_id}_{round_num}_{candidate['user_id']}"
                vote_buttons.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

            vote_buttons.append([InlineKeyboardButton("🚫 Abstain / Skip Vote", callback_data=f"dvote_{chat_id}_{round_num}_0")])
            keyboard = InlineKeyboardMarkup(vote_buttons)

            try:
                await context.bot.send_message(
                    chat_id=voter_id,
                    text=f"🗳️ **DAY {round_num} SECRET LYNCH VOTE**\nSelect who you want to lynch:",
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.warning(f"Could not send vote DM to {voter_id}: {e}")

        if context.job_queue:
            context.job_queue.run_once(
                callback=end_day_voting_phase_job,
                when=DAY_VOTE_TIME,
                chat_id=chat_id,
                name=f"day_vote_{chat_id}"
            )
    except Exception as e:
        logger.error(f"Error in start_day_voting_phase: {e}\n{traceback.format_exc()}")

async def end_day_voting_phase_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue wrapper for ending day vote phase when timer expires."""
    chat_id = context.job.chat_id
    await trigger_end_day_voting_phase(context, chat_id)

async def trigger_end_day_voting_phase(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Tallies Day votes and handles lynching."""
    try:
        game = await get_game(chat_id)
        if not game or game["state"] != "DAY_VOTE":
            return

        round_num = game["phase_round"]
        lynch_res = await process_day_votes(chat_id, round_num)

        lynched = lynch_res["lynched"]
        if lynched:
            role_name = ROLES_INFO.get(lynched["role"], {}).get("name", lynched["role"])
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⚖️ **DAY {round_num} LYNCHING RESULTS** ⚖️\n\n"
                    f"The town has voted! 💀 **{lynched['full_name']}** was lynched!\n"
                    f"Their true role was: **{role_name}**"
                )
            )

            try:
                await context.bot.send_message(
                    chat_id=lynched["user_id"],
                    text="☠️ **YOU WERE LYNCHED!** Send your last words here in DM to broadcast them to the group."
                )
            except Exception:
                pass

            if lynch_res.get("is_jester"):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="🃏 **JESTER WINS!** The Jester tricked the town into lynching them!"
                )
                await set_game_state(chat_id, "ENDED")
                return

        else:
            reason = lynch_res["reason"]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚖️ **DAY {round_num} LYNCHING RESULTS** ⚖️\n\n{reason}"
            )

        win_res = await check_win_condition(chat_id)
        if win_res:
            await context.bot.send_message(chat_id=chat_id, text=win_res["text"])
            await set_game_state(chat_id, "ENDED")
            return

        await start_night_phase(context, chat_id, round_num + 1)
    except Exception as e:
        logger.error(f"Error in trigger_end_day_voting_phase: {e}\n{traceback.format_exc()}")
