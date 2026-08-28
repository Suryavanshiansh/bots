"""
Game state tracker for the Word Grid Userbot.
"""


class GameState:
    def __init__(self):
        self.reset()

    def reset(self):
        # Is a game currently active?
        self.active: bool = False
        # The Telethon message object that has the grid photo
        self.grid_message = None
        # Original full clue text from the game-start message
        self.clue_text: str = ""
        # Words returned by the solver bot
        self.words_to_guess: list = []
        # All words that have been guessed (by us OR other players)
        self.guessed_words: set = set()
