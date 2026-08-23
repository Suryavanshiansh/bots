import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Game Timers (seconds)
REGISTRATION_TIME = int(os.getenv("REGISTRATION_TIME", "60"))
EXTEND_TIME = int(os.getenv("EXTEND_TIME", "60"))
NIGHT_TIME = int(os.getenv("NIGHT_TIME", "60"))
DAY_VOTE_TIME = int(os.getenv("DAY_VOTE_TIME", "90"))
LAST_WORDS_TIME = int(os.getenv("LAST_WORDS_TIME", "60"))

DB_PATH = "mafia_bot.db"
