import asyncio
from typing import Dict, List, Optional
from database import (
    get_game, get_players, set_game_state, set_player_dead,
    get_night_actions, get_day_votes, log_night_action, record_day_vote,
    record_win
)
from game.roles import ROLES_INFO

async def check_win_condition(chat_id: int) -> Optional[Dict]:
    """
    Checks if any team has met win conditions and awards win coins (25 coins).
    Returns dict with winner info if ended, else None.
    """
    players = await get_players(chat_id, alive_only=False)
    alive_players = [p for p in players if p["is_alive"]]

    if not alive_players:
        return {"winner": "NOBODY", "text": "Everyone died! It's a draw! 💀"}

    mafia_count = sum(1 for p in alive_players if p["role"] in ("GODFATHER", "MAFIA"))
    sk_count = sum(1 for p in alive_players if p["role"] == "SERIAL_KILLER")
    town_count = sum(1 for p in alive_players if p["role"] not in ("GODFATHER", "MAFIA", "SERIAL_KILLER", "JESTER"))
    jester_count = sum(1 for p in alive_players if p["role"] == "JESTER")
    total_alive = len(alive_players)

    # 1. Serial Killer Win
    if sk_count > 0 and (total_alive <= 2) and mafia_count == 0:
        for p in players:
            if p["role"] == "SERIAL_KILLER":
                await record_win(p["user_id"], "SERIAL_KILLER")
        return {
            "winner": "SERIAL_KILLER",
            "text": "🔪 **SERIAL KILLER WINS!** The lone killer outlasted everyone and purged the city!\n🪙 **+25 Winner Coins Awarded!**"
        }

    # 2. Villagers Win
    if mafia_count == 0 and sk_count == 0:
        for p in players:
            if p["role"] not in ("GODFATHER", "MAFIA", "SERIAL_KILLER", "JESTER"):
                await record_win(p["user_id"], "TOWN")
        return {
            "winner": "TOWN",
            "text": "🎉 **TOWN WINS!** All evil forces have been eliminated from the city!\n🪙 **+25 Winner Coins Awarded to all Town Members!**"
        }

    # 3. Mafia Wins
    if mafia_count >= (town_count + jester_count) and sk_count == 0:
        for p in players:
            if p["role"] in ("GODFATHER", "MAFIA"):
                await record_win(p["user_id"], "MAFIA")
        return {
            "winner": "MAFIA",
            "text": "🔴 **MAFIA WINS!** The Mafia has reached numerical control of the city!\n🪙 **+25 Winner Coins Awarded to all Mafia Members!**"
        }

    return None

async def process_night_actions(chat_id: int, phase_round: int) -> Dict:
    """Processes secret night actions (Doctor save, Vest protection, Mafia kill, SK kill, Vigilante shoot)."""
    actions = await get_night_actions(chat_id, phase_round)
    players = await get_players(chat_id, alive_only=True)
    player_dict = {p["user_id"]: p for p in players}

    saved_player_ids = set()
    mafia_targets = []
    sk_targets = []
    vig_targets = []

    for act in actions:
        actor_id = act["actor_id"]
        role = act["role"]
        target_id = act["target_id"]
        action_type = act["action_type"]

        if action_type == "SAVE":
            saved_player_ids.add(target_id)
        elif action_type == "KILL" and role in ("GODFATHER", "MAFIA"):
            mafia_targets.append(target_id)
        elif action_type == "KILL" and role == "SERIAL_KILLER":
            sk_targets.append(target_id)
        elif action_type == "SHOOT" and role == "VIGILANTE":
            vig_targets.append(target_id)

    mafia_final_target = None
    if mafia_targets:
        mafia_final_target = max(set(mafia_targets), key=mafia_targets.count)

    attack_targets = set()
    if mafia_final_target:
        attack_targets.add(mafia_final_target)
    for t in sk_targets:
        attack_targets.add(t)
    for t in vig_targets:
        attack_targets.add(t)

    deaths = []
    for target_id in attack_targets:
        if target_id in saved_player_ids:
            continue
        if target_id in player_dict:
            target_player = dict(player_dict[target_id]) # Convert sqlite3.Row to dict safely
            if target_player.get("has_vest"):
                continue

            await set_player_dead(chat_id, target_id)
            deaths.append(target_player)

    return {
        "deaths": deaths,
        "saved_count": len(saved_player_ids)
    }

async def process_day_votes(chat_id: int, phase_round: int) -> Dict:
    """Tallies Day votes cast via DM inline keyboard during Day phase."""
    votes = await get_day_votes(chat_id, phase_round)
    players = await get_players(chat_id, alive_only=True)
    player_map = {p["user_id"]: dict(p) for p in players}

    tally: Dict[int, int] = {}
    for v in votes:
        target_id = v["target_id"]
        weight = v["weight"]
        tally[target_id] = tally.get(target_id, 0) + weight

    if not tally:
        return {"lynched": None, "reason": "No votes were cast during the day!"}

    max_votes = max(tally.values())
    top_candidates = [tid for tid, count in tally.items() if count == max_votes]

    if len(top_candidates) > 1:
        return {"lynched": None, "reason": f"It was a tie vote ({max_votes} votes each)! Nobody was lynched today."}

    lynched_id = top_candidates[0]
    lynched_player = player_map.get(lynched_id)

    if lynched_player:
        await set_player_dead(chat_id, lynched_id)
        if lynched_player.get("role") == "JESTER":
            await record_win(lynched_id, "JESTER")

        return {
            "lynched": lynched_player,
            "votes_count": max_votes,
            "is_jester": (lynched_player.get("role") == "JESTER")
        }

    return {"lynched": None, "reason": "Target player not found."}
