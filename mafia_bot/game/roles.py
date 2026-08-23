from enum import Enum

class Team(Enum):
    MAFIA = "Mafia 🔴"
    TOWN = "Town 🔵"
    NEUTRAL = "Neutral 🟡"

ROLES_INFO = {
    "GODFATHER": {
        "name": "Mafia Godfather 👑🔴",
        "team": Team.MAFIA,
        "description": "Leader of the Mafia. You vote with the Mafia at night. If the Detective investigates you, you appear as INNOCENT!",
        "has_night_action": True,
        "action_prompt": "Choose a target for the Mafia to eliminate:"
    },
    "MAFIA": {
        "name": "Mafia Goon 🔴",
        "team": Team.MAFIA,
        "description": "Member of the Mafia. Coordinate with your team at night to eliminate Town members.",
        "has_night_action": True,
        "action_prompt": "Choose a target for the Mafia to eliminate:"
    },
    "DETECTIVE": {
        "name": "Detective 🔍🔵",
        "team": Team.TOWN,
        "description": "Investigate one player each night to discover if they are Mafia or Innocent.",
        "has_night_action": True,
        "action_prompt": "Choose a player to investigate tonight:"
    },
    "DOCTOR": {
        "name": "Doctor 💉🔵",
        "team": Team.TOWN,
        "description": "Protect one player each night from night attacks (you can protect yourself).",
        "has_night_action": True,
        "action_prompt": "Choose a player to save tonight:"
    },
    "VIGILANTE": {
        "name": "Vigilante 🔫🔵",
        "team": Team.TOWN,
        "description": "Town gunman. You have limited bullets to eliminate suspects at night.",
        "has_night_action": True,
        "action_prompt": "Choose a target to shoot tonight (or skip):"
    },
    "MAYOR": {
        "name": "Mayor 👑🔵",
        "team": Team.TOWN,
        "description": "Town leader. Your vote during Day Lynching counts as TWO votes!",
        "has_night_action": False,
        "action_prompt": None
    },
    "SERGEANT": {
        "name": "Sergeant 🛡️🔵",
        "team": Team.TOWN,
        "description": "Backup Detective. If the Detective dies, you inherit investigation powers!",
        "has_night_action": False, # Becomes True if Detective dies
        "action_prompt": "Choose a player to investigate tonight:"
    },
    "VILLAGER": {
        "name": "Villager 🏡🔵",
        "team": Team.TOWN,
        "description": "Standard town member. Use deduction, behavioral observation, and day voting to find the Mafia.",
        "has_night_action": False,
        "action_prompt": None
    },
    "JESTER": {
        "name": "Jester (The Fool) 🃏🟡",
        "team": Team.NEUTRAL,
        "description": "Wildcard! Your goal is to get lynched during the Day vote. If lynched, YOU WIN!",
        "has_night_action": False,
        "action_prompt": None
    },
    "SERIAL_KILLER": {
        "name": "Serial Killer 🔪🟡",
        "team": Team.NEUTRAL,
        "description": "Solo murderer. Eliminate one player every night. Win if you are the last survivor!",
        "has_night_action": True,
        "action_prompt": "Choose a player to murder tonight:"
    }
}
