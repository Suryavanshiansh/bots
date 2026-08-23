import asyncio
from typing import Dict, List, Optional
from database import (
    get_game, get_players, set_game_state, set_player_dead,
    get_night_actions, get_day_votes, log_night_action, record_day_vote
)
from game.roles import ROLES_INFO

async def check_win_condition(chat_id: int) -> Optional[Dict]:
    """
    Checks if any team has met win conditions.
    Returns dict with winner info if ended, else None.
    """
    players = await get_players(chat_id, alive_only=True)
    if not players:
        return {"winner": "NOBODY", "text": "Everyone died! It's a draw! 💀"}

    mafia_count = sum(1 for p in players if p["role"] in ("GODFATHER", "MAFIA"))
    sk_count = sum(1 for p in players if p["role"] == "SERIAL_KILLER")
    town_count = sum(1 for p in players if p["role"] not in ("GODFATHER", "MAFIA", "SERIAL_KILLER", "JESTER"))
    jester_count = sum(1 for p in players if p["role"] == "JESTER")
    total_alive = len(players)

    # 1. Serial Killer Win: SK is alive and only 1 or 2 players total remain (and no Mafia)
    if sk_count > 0 and (total_alive <= 2) and mafia_count == 0:
        return {
            "winner": "SERIAL_KILLER",
            "text": "🔪 **SERIAL KILLER WINS!** The lone killer outlasted everyone and purged the city!"
        }

    # 2. Villagers Win: All Mafia & Serial Killer eliminated
    if mafia_count == 0 and sk_count == 0:
        return {
            "winner": "TOWN",
            "text": "🎉 **TOWN WINS!** All evil forces have been eliminated from the city!"
        }

    # 3. Mafia Wins: Mafia count >= Town + Jester count AND no Serial Killer
    if mafia_count >= (town_count + jester_count) and sk_count == 0:
        return {
            "winner": "MAFIA",
            "text": "🔴 **MAFIA WINS!** The Mafia has reached numerical control of the city!"
        }

    return None

async def process_night_actions(chat_id: int, phase_round: int) -> Dict:
    """
    Processes secret night actions (Doctor save, Mafia kill, SK kill, Vigilante shoot, Detective check).
    Returns summary result for group announcement.
    """
    actions = await get_night_actions(chat_id, phase_round)
    players = await get_players(chat_id, alive_only=True)
    player_dict = {p["user_id"]: p for p in players}

    saved_player_ids = set()
    mafia_targets = []
    sk_targets = []
    vig_targets = []
    detective_checks = []

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

    # Determine Mafia consensus target
    mafia_final_target = None
    if mafia_targets:
        # Pick most voted target by Mafia
        mafia_final_target = max(set(mafia_targets), key=mafia_targets.count)

    # Collect all attack targets
    attack_targets = set()
    if mafia_final_target:
        attack_targets.add(mafia_final_target)
    for t in sk_targets:
        attack_targets.add(t)
    for t in vig_targets:
        attack_targets.add(t)

    # Filter out saved targets
    deaths = []
    for target_id in attack_targets:
        if target_id in saved_player_ids:
            continue # Saved by Doctor!
        if target_id in player_dict:
            await set_player_dead(chat_id, target_id)
            deaths.append(player_dict[target_id])

    # Check if original Detective died, promote Sergeant if alive
    alive_detective = any(p["role"] == "DETECTIVE" and p["is_alive"] for p in players if p["user_id"] not in [d["user_id"] for d in deaths])
    if not alive_detective:
        # Promote Sergeant to Detective if Sergeant exists and is alive
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE players SET role = 'DETECTIVE' WHERE chat_id = ? AND role = 'SERGEANT' AND is_alive = 1",
                (chat_id,)
            )
            await db.commit()

    return {
        "deaths": deaths,
        "saved_count": len(saved_player_ids)
    }

async def process_day_votes(chat_id: int, phase_round: int) -> Dict:
    """
    Tallies votes cast via DM inline keyboard during Day phase.
    Returns lynch result dict.
    """
    votes = await get_day_votes(chat_id, phase_round)
    players = await get_players(chat_id, alive_only=True)
    player_map = {p["user_id"]: p for p in players}

    tally: Dict[int, int] = {}
    for v in votes:
        target_id = v["target_id"]
        weight = v["weight"]
        tally[target_id] = tally.get(target_id, 0) + weight

    if not tally:
        return {"lynched": None, "reason": "No votes were cast during the day!"}

    # Find highest votes
    max_votes = max(tally.values())
    top_candidates = [tid for tid, count in tally.items() if count == max_votes]

    if len(top_candidates) > 1:
        return {"lynched": None, "reason": f"It was a tie vote ({max_votes} votes each)! Nobody was lynched today."}

    lynched_id = top_candidates[0]
    lynched_player = player_map.get(lynched_id)

    if lynched_player:
        await set_player_dead(chat_id, lynched_id)
        return {
            "lynched": lynched_player,
            "votes_count": max_votes,
            "is_jester": (lynched_player["role"] == "JESTER")
        }

    return {"lynched": None, "reason": "Target player not found."}
