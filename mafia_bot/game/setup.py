import random
from typing import List, Dict

def get_balanced_roles(player_count: int) -> List[str]:
    """Generates a balanced role list based on the number of players."""
    if player_count < 4:
        # Minimum setup for testing
        return ["GODFATHER", "DOCTOR", "DETECTIVE", "VILLAGER"][:player_count]

    roles = []

    if player_count in (4, 5):
        # 1 Mafia, 1 Detective, 1 Doctor, Rest Villagers
        roles = ["GODFATHER", "DETECTIVE", "DOCTOR"]
        while len(roles) < player_count:
            roles.append("VILLAGER")

    elif player_count in (6, 7):
        # 2 Mafia, 1 Detective, 1 Doctor, 1 Vigilante, Rest Villagers
        roles = ["GODFATHER", "MAFIA", "DETECTIVE", "DOCTOR", "VIGILANTE"]
        while len(roles) < player_count:
            roles.append("VILLAGER")

    elif player_count in (8, 9):
        # 2 Mafia, 1 Detective, 1 Doctor, 1 Vigilante, 1 Jester, 1 Mayor, Rest Villagers
        roles = ["GODFATHER", "MAFIA", "DETECTIVE", "DOCTOR", "VIGILANTE", "JESTER", "MAYOR"]
        while len(roles) < player_count:
            roles.append("VILLAGER")

    elif player_count in (10, 11, 12):
        # 3 Mafia, 1 Detective, 1 Sergeant, 1 Doctor, 1 Vigilante, 1 Mayor, 1 Jester, Rest Villagers
        roles = ["GODFATHER", "MAFIA", "MAFIA", "DETECTIVE", "SERGEANT", "DOCTOR", "VIGILANTE", "MAYOR", "JESTER"]
        while len(roles) < player_count:
            roles.append("VILLAGER")

    else: # 13+ players
        # 4 Mafia, 1 Serial Killer, 1 Detective, 1 Sergeant, 1 Doctor, 1 Vigilante, 1 Mayor, 1 Jester, Rest Villagers
        roles = ["GODFATHER", "MAFIA", "MAFIA", "MAFIA", "SERIAL_KILLER", "DETECTIVE", "SERGEANT", "DOCTOR", "VIGILANTE", "MAYOR", "JESTER"]
        while len(roles) < player_count:
            roles.append("VILLAGER")

    random.shuffle(roles)
    return roles
