"""Conservative Persian legal OCR normalization (v54).

Lam-alef policy: only explicit, whitelisted canonical forms are corrected from
OCR variants. There is NO global or bidirectional «ال/لا» swap. Ambiguous words
are preserved. Final user-visible output applies the same whitelist again.
"""
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
LEXICON_PATH = BASE / "ocr_lexicon.json"
CERTAIN_LA_PATH = BASE / "certain_la_words.json"

__CACHE = None
__LA_CACHE = None

def load_ocr_lexicon():
    global __CACHE
    if __CACHE is None:
        try:
            with open(LEXICON_PATH, encoding="utf-8") as f:
                __CACHE = json.load(f)
        except (OSError, ValueError, TypeError):
            __CACHE = {}
    return __CACHE

def load_certain_la_words():
    global __LA_CACHE
    if __LA_CACHE is None:
        try:
            with open(CERTAIN_LA_PATH, encoding="utf-8") as f:
                data = json.load(f)
            __LA_CACHE = data.get("words", {}) if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError):
            __LA_CACHE = {}
    return __LA_CACHE

def normalize_lam_alef_glyphs(text: str) -> str:
    if not text:
        return text
    replacements = {
        "\ufefb":"لا", "\ufefc":"لا", "\ufef9":"لا", "\ufefa":"لا",
        "\ufef7":"لا", "\ufef8":"لا", "\ufef5":"لا", "\ufef6":"لا"
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Only an isolated split lam-alef is safe to join.
    return re.sub(r"(?<!\S)ا[\u200c\u200d ]+ل(?!\S)", "لا", text)

def _token_core(tok):
    m = re.match(r"^([^\w\u0600-\u06ff]*)(.*?)([^\w\u0600-\u06ff]*)$", tok, re.UNICODE)
    return m.groups() if m else ("", tok, "")

def _apply_exact_pairs(text, pairs):
    if not text or not pairs:
        return text
    def repl(m):
        tok=m.group(0); pre,core,post=_token_core(tok)
        return pre + pairs.get(core, core) + post
    return re.sub(r"\S+", repl, text)

def correct_certain_la_words(text: str) -> str:
    """Correct ONLY exact OCR tokens explicitly whitelisted as certain «لا»."""
    return _apply_exact_pairs(text, load_certain_la_words())

CERTAIN_OCR_FIXES = {
    "طالق": "طلاق",
    "اختالف": "اختلاف",
    "اختالفات": "اختلافات",
}

def correct_certain_ocr(text: str) -> str:
    return _apply_exact_pairs(text, CERTAIN_OCR_FIXES)

def correct_legal_ocr_words(text: str, lexicon=None) -> str:
    # v54 deliberately ignores the old derived/directional lam-alef logic.
    # Only explicit certain-la and certain OCR corrections are allowed.
    text = correct_certain_ocr(text)
    return correct_certain_la_words(text)

def normalize_legal_ocr(text: str) -> str:
    return correct_legal_ocr_words(normalize_lam_alef_glyphs(text))
