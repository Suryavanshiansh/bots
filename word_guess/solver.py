import os
import re
from collections import Counter
from typing import List, Tuple, Dict, Set, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GREEN_SYMBOLS = {'🟩', '🟢', '💚', 'g', 'G', '1'}
YELLOW_SYMBOLS = {'🟨', '🟡', '💛', 'y', 'Y', '2'}
RED_SYMBOLS = {'🟥', '🔴', '❤️', '⬛', '⬜', '🟫', 'r', 'R', 'b', 'B', 'x', 'X', '0'}

class WordleSolver:
    def __init__(self, common_path: Optional[str] = None, full_path: Optional[str] = None):
        if not common_path:
            common_path = os.path.join(BASE_DIR, "common_words.txt")
        elif not os.path.isabs(common_path):
            common_path = os.path.join(BASE_DIR, common_path)

        if not full_path:
            full_path = os.path.join(BASE_DIR, "dictionary.txt")
        elif not os.path.isabs(full_path):
            full_path = os.path.join(BASE_DIR, full_path)

        self.common_words = set(self.load_words(common_path))
        self.full_words = self.load_words(full_path)

    @staticmethod
    def load_words(path: str) -> List[str]:
        words = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if len(w) == 5 and w.isalpha():
                        words.append(w)
        except Exception as e:
            print(f"Error loading words from {path}: {e}")
        return words

    def score_word(self, word: str, candidates: List[str]) -> float:
        freq = Counter()
        for w in candidates:
            freq.update(set(w))
        unique_letters = set(word)
        return sum(freq[c] for c in unique_letters)

    def parse_line(self, line: str) -> Optional[Tuple[List[str], str]]:
        line = line.strip()
        if not line:
            return None

        words_found = re.findall(r'\b[a-zA-Z]{5}\b', line)
        if not words_found:
            return None

        target_word = words_found[0].lower()
        line_without_word = line.replace(words_found[0], '').strip()

        colors = []
        for char in line_without_word:
            if char in GREEN_SYMBOLS:
                colors.append('G')
            elif char in YELLOW_SYMBOLS:
                colors.append('Y')
            elif char in RED_SYMBOLS:
                colors.append('R')

        if len(colors) != 5:
            return None

        return colors, target_word

    def parse_message(self, text: str) -> List[Tuple[List[str], str]]:
        attempts = []
        for line in text.splitlines():
            parsed = self.parse_line(line)
            if parsed:
                attempts.append(parsed)
        return attempts

    def solve(self, attempts: List[Tuple[List[str], str]]) -> Tuple[List[str], List[str]]:
        """
        Returns (common_matches, rare_matches)
        both ordered by letter frequency score.
        """
        if not attempts:
            common_candidates = [w for w in self.full_words if w in self.common_words]
            rare_candidates = [w for w in self.full_words if w not in self.common_words]
            return common_candidates, rare_candidates

        candidates = list(self.full_words)

        for colors, guess in attempts:
            bad_positions: Dict[int, Set[str]] = {i: set() for i in range(5)}
            exact_positions: Dict[int, str] = {}
            gy_counts: Counter = Counter()

            for i, (col, char) in enumerate(zip(colors, guess)):
                if col == 'G':
                    exact_positions[i] = char
                    gy_counts[char] += 1
                elif col == 'Y':
                    bad_positions[i].add(char)
                    gy_counts[char] += 1
                elif col == 'R':
                    bad_positions[i].add(char)

            min_counts: Counter = Counter()
            exact_counts: Dict[str, int] = {}

            for i, (col, char) in enumerate(zip(colors, guess)):
                if col == 'R':
                    if gy_counts[char] > 0:
                        exact_counts[char] = gy_counts[char]
                    else:
                        exact_counts[char] = 0

            for char, count in gy_counts.items():
                if char not in exact_counts:
                    min_counts[char] = max(min_counts[char], count)

            filtered = []
            for word in candidates:
                valid = True

                for pos, char in exact_positions.items():
                    if word[pos] != char:
                        valid = False
                        break
                if not valid:
                    continue

                for pos, chars in bad_positions.items():
                    if word[pos] in chars:
                        valid = False
                        break
                if not valid:
                    continue

                word_counts = Counter(word)
                for char, req_min in min_counts.items():
                    if word_counts[char] < req_min:
                        valid = False
                        break
                if not valid:
                    continue

                for char, max_allowed in exact_counts.items():
                    if word_counts[char] != max_allowed:
                        valid = False
                        break
                if not valid:
                    continue

                filtered.append(word)

            candidates = filtered

        # Separate into common and rare
        common_matches = []
        rare_matches = []

        for word in candidates:
            score = self.score_word(word, candidates)
            if word in self.common_words:
                common_matches.append((score, word))
            else:
                rare_matches.append((score, word))

        common_matches.sort(key=lambda x: x[0], reverse=True)
        rare_matches.sort(key=lambda x: x[0], reverse=True)

        return [w for s, w in common_matches], [w for s, w in rare_matches]
