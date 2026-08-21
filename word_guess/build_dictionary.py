import urllib.request
import os

def build_dictionaries():
    print("Building dictionaries...")

    # 1. Fetch official common target words
    url_targets = "https://raw.githubusercontent.com/3b1b/videos/master/_2022/wordle/data/possible_words.txt"
    common_words = set()
    
    try:
        req = urllib.request.urlopen(url_targets)
        content = req.read().decode("utf-8")
        for line in content.splitlines():
            w = line.strip().lower()
            if len(w) == 5 and w.isalpha():
                common_words.add(w)
    except Exception as e:
        print(f"Error fetching common words: {e}")

    # Add extra well-known 5-letter proper names / common words
    extra_common = {"mario", "zelda", "sonic", "japan", "india", "china", "paris", "tokyo", "romeo", "julie"}
    common_words.update(extra_common)

    # 2. Fetch full allowed words dictionary
    url_allowed = "https://raw.githubusercontent.com/3b1b/videos/master/_2022/wordle/data/allowed_words.txt"
    full_words = set(common_words)
    
    try:
        req = urllib.request.urlopen(url_allowed)
        content = req.read().decode("utf-8")
        for line in content.splitlines():
            w = line.strip().lower()
            if len(w) == 5 and w.isalpha():
                full_words.add(w)
    except Exception as e:
        print(f"Error fetching full allowed words: {e}")

    # Save common_words.txt
    sorted_common = sorted(list(common_words))
    with open("common_words.txt", "w", encoding="utf-8") as f:
        for word in sorted_common:
            f.write(word + "\n")
    print(f"Saved {len(sorted_common)} common 5-letter target words to common_words.txt")

    # Save dictionary.txt
    sorted_full = sorted(list(full_words))
    with open("dictionary.txt", "w", encoding="utf-8") as f:
        for word in sorted_full:
            f.write(word + "\n")
    print(f"Saved {len(sorted_full)} total 5-letter words to dictionary.txt")

if __name__ == "__main__":
    build_dictionaries()
