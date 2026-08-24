"""
Message parser for the Word Grid Userbot.
Handles detection and extraction from Word Grid Bot + Solver Bot messages.
"""
import re


# ─── CLUE PATTERN ─────────────────────────────────────────────────────────────
# Matches patterns like: "B--- (4)", "S_____ (6)", "F........ (8)"
_CLUE_RE = re.compile(r"[A-Z][-_\.]{1,20}\s*\(\d+\)", re.IGNORECASE)


def has_clue_pattern(text: str) -> bool:
    """Return True if the text contains at least one clue like 'B--- (4)'."""
    return bool(_CLUE_RE.search(text or ""))


# ─── GAME OVER DETECTION ──────────────────────────────────────────────────────
_GAME_OVER_KEYWORDS = [
    "game over",
    "all words found",
    "congratulations",
    "puzzle complete",
    "game ended",
    "game finished",
    "final scores",
    "leaderboard",
]


def is_game_over(text: str) -> bool:
    """Return True if Word Grid Bot announced game over or if all clues are checkmarked."""
    t = (text or "").lower()
    if any(kw in t for kw in _GAME_OVER_KEYWORDS):
        return True

    # If message contains clue list and 0 clues remain unsolved (all checkmarked), game is complete!
    if ("find these words" in t or "hard mode" in t) and ("☑️" in text or "✅" in text):
        unsolved = get_unsolved_clue_numbers(text)
        if len(unsolved) == 0:
            return True

    return False


# ─── NORMAL GAME DETECTION ────────────────────────────────────────────────────
_NORMAL_START_KEYWORDS = ["new game", "game started", "started a game", "game begins"]


def is_normal_game(text: str) -> bool:
    """
    Return True if Word Grid Bot started a NORMAL (non-hard) game.
    We detect 'game started' without the word 'hard'.
    """
    t = (text or "").lower()
    started = any(kw in t for kw in _NORMAL_START_KEYWORDS)
    is_hard = "hard" in t
    return started and not is_hard


# ─── WORD FOUND CONFIRMATION ──────────────────────────────────────────────────
_FOUND_PATTERNS = [
    re.compile(r"\bfound[:\s]+([A-Z]{3,20})\b", re.IGNORECASE),
    re.compile(r"[✅☑️✔]\s*(?:You found\s+)?([A-Z]{3,20})\b", re.IGNORECASE),
    re.compile(r"(?:correct|guessed)[!:\s]+([A-Z]{3,20})\b", re.IGNORECASE),
]


def extract_confirmed_word(text: str) -> str | None:
    """
    Extract the confirmed/found word from a Word Grid Bot message.
    Returns the word in UPPERCASE, or None if not found.
    """
    for pattern in _FOUND_PATTERNS:
        m = pattern.search(text or "")
        if m:
            w = m.group(1).upper()
            if w not in ("YOU", "YOUR", "THE", "BOT", "HAS", "WAS", "FOR"):
                return w
    return None


def extract_all_solved_words(text: str) -> set[str]:
    """
    Extract all words that are already checkmarked (✅ TILL, ☑️ SNOW, etc.) in the clue list.
    """
    solved = set()
    for m in re.finditer(r"[✅☑️✔]\s*([A-Z]{3,20})", text or ""):
        w = m.group(1).upper()
        if w not in _SKIP_WORDS:
            solved.add(w)
    return solved


# ─── MISSING CLUE NUMBERS ─────────────────────────────────────────────────────
_MISSING_KEYWORDS = ["missing", "remaining", "not found", "still need", "unfound", "left"]


def extract_missing_clue_numbers(text: str) -> list[int]:
    """
    Detect which clue numbers are still unanswered after a round.
    Returns a deduplicated list of integers (clue indices).
    """
    # First check explicit keyword lists
    t = (text or "").lower()
    if any(kw in t for kw in _MISSING_KEYWORDS):
        nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", text) if 1 <= int(n) <= 50]
        seen = set()
        result = []
        for n in nums:
            if n not in seen:
                seen.add(n)
                result.append(n)
        if result:
            return result

    # Fallback / Primary: parse clue list lines (unsolved clue lines vs solved checkmark lines)
    return get_unsolved_clue_numbers(text)


def get_unsolved_clue_numbers(text: str) -> list[int]:
    """
    Parse a Word Grid Bot clue list message and return the 1-indexed clue numbers
    of all remaining UNSOLVED clues (lines with hyphens/dots vs solved lines).
    """
    lines = (text or "").splitlines()
    unsolved = []
    clue_index = 0

    for line in lines:
        l = line.strip()
        # Skip header lines like "HARD MODE CHALLENGE", "Find these words:", etc.
        if "HARD" in l.upper() or "CHALLENGE" in l.upper() or "FIND" in l.upper() or "REFRESH" in l.upper():
            continue

        # Check if line looks like a clue line (has letter or checkmark + word)
        has_clue_pattern = bool(re.search(r"^[A-Z][-_\.]{1,20}\s*\(\d+\)", l, re.IGNORECASE))
        has_checkmark = bool(re.search(r"[✅☑️✔]", l)) or "found" in l.lower()
        has_word = bool(re.search(r"[A-Z]{3,20}", l, re.IGNORECASE))

        if has_clue_pattern or has_checkmark or (has_word and not l.startswith("/")):
            clue_index += 1
            # Unsolved clues have 2 or more hyphens, dots, or underscores
            if re.search(r"[-_\.]{2,}", l):
                unsolved.append(clue_index)

    return unsolved


# ─── SOLVER BOT REPLY PARSER ──────────────────────────────────────────────────
# Primary: matches "1. **BEACH**" or "1. BEACH" lines (word-solver-bot format)
_SOLUTION_LINE_RE = re.compile(
    r"^\s*\d+[.)]\s+\*{0,2}([A-Z]{3,20})\*{0,2}",
    re.IGNORECASE | re.MULTILINE,
)

# Fallback: grab any standalone long uppercase word
_BARE_WORD_RE = re.compile(r"\b([A-Z]{4,20})\b")

# Words to skip in fallback mode (common non-game words in bot replies)
_SKIP_WORDS = {
    "HARD", "MODE", "WORD", "FOUND", "SEARCH", "PUZZLE", "SOLVED",
    "GRID", "CLUE", "CLUES", "HINT", "HINTS", "ROUND", "GAME",
    "ROW", "COL", "RIGHT", "LEFT", "DOWN", "FROM", "INTO", "THAT",
    "WITH", "THIS", "HAVE", "MORE", "ALSO", "THEN", "NEXT", "LAST",
    "WRONG", "SWAP", "OPTION", "OPTIONS", "DIRECTION", "START", "END",
}


def parse_solver_words(text: str) -> list[str]:
    """
    Parse the list of solved words from the solver bot's reply.
    Returns a deduplicated list of UPPERCASE words.
    """
    words = []
    seen = set()

    # Primary: "1. **BEACH**" format from word-solver-bot
    for m in _SOLUTION_LINE_RE.finditer(text or ""):
        w = m.group(1).upper()
        if w not in seen:
            seen.add(w)
            words.append(w)

    # Fallback: if structured lines not found, grab long uppercase words
    if not words:
        for m in _BARE_WORD_RE.finditer(text or ""):
            w = m.group(1).upper()
            if w in _SKIP_WORDS or w in seen:
                continue
            seen.add(w)
            words.append(w)

    return words
