"""Text normalization for keyword matching. Plain Python, no Claude.

Used only to MATCH headlines; the original text is always what gets returned and
cited (never change the source text).
"""

# Serbian Cyrillic -> Latin is a fixed 1:1 table (3 letters become two: lj, nj, dž).
CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ђ": "đ", "е": "e", "ж": "ž",
    "з": "z", "и": "i", "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m", "н": "n",
    "њ": "nj", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "ћ": "ć", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
})

# People often type without diacritics ("vukicevic"), so match without them too.
DIACRITICS_TO_ASCII = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj"})


def normalize(text: str) -> str:
    """'Вукићевић' / 'VUKIĆEVIĆ' / 'vukicevic' -> 'vukicevic' (for matching only)."""
    return text.lower().translate(CYRILLIC_TO_LATIN).translate(DIACRITICS_TO_ASCII)
