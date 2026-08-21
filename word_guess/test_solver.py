import sys
import os

# Ensure the folder containing this file is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from solver import WordleSolver
except ImportError:
    from word_guess.solver import WordleSolver

test_message = """
Crocodile Game EN 🐊 🇮🇳
Johnny Joestar
mario
🟩🟩🟥🟥🟥 MANGO
🟥🟥🟥🟥🟥 SOULS
🟩🟩🟥🟥🟥 MAPLE
🟩🟩🟥🟥🟥 MARRY
🟨🟥🟨🟥🟥 ADIEU
🟩🟩🟨🟥🟥 MAIZE
🟩🟩🟥🟩🟥 MAVIN
🟩🟩🟥🟩🟥 MARIO
"""

def test():
    solver = WordleSolver()
    attempts = solver.parse_message(test_message)
    print(f"Parsed {len(attempts)} attempts:")
    for cols, word in attempts:
        print(f"  {''.join(cols)} {word.upper()}")

    common, rare = solver.solve(attempts)
    print(f"\nFound {len(common)} Valid Common Words: {', '.join([w.upper() for w in common])}")
    print(f"Found {len(rare)} Rare/Uncommon Words: {', '.join([w.upper() for w in rare])}")

if __name__ == "__main__":
    test()
