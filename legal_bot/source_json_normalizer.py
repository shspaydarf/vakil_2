"""One-time conservative normalization for bundled Persian legal JSON sources.

Version 53: fix high-confidence لا/ال OCR transpositions and Persian final-ه
suffix attachment (مثل «هزینههای» -> «هزینه‌های») at the source, so generated
summaries, legal-material text, and term lists inherit the corrected form.
Unknown word boundaries are never guessed.
"""
import argparse
import json
from pathlib import Path
from .legal_text_cleanup import cleanup_legal_text
from .ocr_lam_alef import normalize_legal_ocr

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "iran"
FILES = (
    "laws.json",
    "rulings.json",
    "consultations.json",
    "legal_glossary.json",
    "important_terms.json",
)

# Final «ه» followed by common Persian suffixes is normally a missing ZWNJ,
# not a new word. We only repair these explicit suffixes; we do NOT split an
# arbitrary «ه» + Persian text because that could destroy genuine words.
FINAL_HE_SUFFIXES = (
    "هایشان", "هایمان", "هایتان", "هایم", "هایت", "هایش", "های", "هایی",
    "ایمان", "ایتان", "ایشان", "ایم", "اید", "اند", "ای", "ات",
)


def normalize_final_he_suffixes(text: str) -> str:
    if not text:
        return text
    # A word ending in «ه» followed by the plural suffix «ها/هایی» is written
    # with a ZWNJ: «پروندهها» -> «پرونده‌ها», «خانههایی» -> «خانه‌هایی».
    # The two-character suffix is inserted after the base «ه»; we never split
    # an arbitrary unknown word boundary.
    s = text.replace("ههایی", "ه\u200cهایی")
    s = s.replace("ههای", "ه\u200cهای")
    return s


def normalize_source_text(text: str) -> str:
    s = cleanup_legal_text(text)
    s = normalize_legal_ocr(s)
    s = normalize_final_he_suffixes(s)
    # High-confidence OCR forms may also be glued to surrounding Persian text.
    # These are explicit lexical fixes; there is no global لا/ال swap.
    for bad, good in {
        "اعالم": "اعلام", "اصالح": "اصلاح", "اسالمی": "اسلامی",
        "ابالغ": "ابلاغ", "اطالعات": "اطلاعات", "طالق": "طلاق",
        "اجارهنامه": "اجاره‌نامه", "ولیفقیه": "ولی‌فقیه",
        "مشقتبار": "مشقت‌بار", "هزینههای": "هزینه‌های",
    }.items():
        s = s.replace(bad, good)
    # Run the conservative cleanup once more so spacing repairs introduced by
    # the OCR pass are reflected consistently. Do not perform any global لا/ال swap.
    s = cleanup_legal_text(s)
    return s


def _walk(value, path=()):
    changed = 0
    examples = []
    if isinstance(value, str):
        fixed = normalize_source_text(value)
        if fixed != value:
            changed = 1
            if len(examples) < 3:
                examples.append({"path": ".".join(map(str, path)), "before": value[:300], "after": fixed[:300]})
        return fixed, 1, changed, examples
    if isinstance(value, list):
        total_strings = total_changed = 0
        for i, item in enumerate(value):
            new_item, strings, ch, ex = _walk(item, path + (i,))
            value[i] = new_item
            total_strings += strings; total_changed += ch
            examples.extend(ex[: max(0, 3-len(examples))])
        return value, total_strings, total_changed, examples
    if isinstance(value, dict):
        total_strings = total_changed = 0
        for k, item in value.items():
            # Metadata/source identifiers are not legal prose and should not be
            # rewritten. Record content fields are normalized below.
            if path == () and k == "metadata":
                continue
            new_item, strings, ch, ex = _walk(item, path + (k,))
            value[k] = new_item
            total_strings += strings; total_changed += ch
            examples.extend(ex[: max(0, 3-len(examples))])
        return value, total_strings, total_changed, examples
    return value, 0, 0, []


ACTIVE_LEGAL_BANKS = frozenset({"laws.json", "rulings.json", "consultations.json",
                              "samples_and_circulars.json"})


def normalize_file(path: Path, *, apply_non_bank_changes: bool = False):
    """Normalize for preview; never write an active legal bank from this utility."""
    path = Path(path)
    if path.name in ACTIVE_LEGAL_BANKS and apply_non_bank_changes:
        raise PermissionError("active_legal_banks_must_be_updated_through_reviewed_bank_transaction")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = json.dumps(data, ensure_ascii=False, sort_keys=True)
    records_before = _record_count(data)
    data, strings, changed, examples = _walk(data)
    after = json.dumps(data, ensure_ascii=False, sort_keys=True)
    would_change = before != after
    written = False
    if would_change and apply_non_bank_changes:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        written = True
    return {
        "file": path.name,
        "records": records_before,
        "strings_visited": strings,
        "strings_changed": changed,
        "would_change": would_change,
        "written": written,
        "examples": examples,
    }


def _record_count(data):
    if isinstance(data, dict):
        for key in ("rulings", "consultations"):
            if isinstance(data.get(key), list):
                return len(data[key])
        return sum(len(v) for v in data.values() if isinstance(v, list))
    return len(data) if isinstance(data, list) else 1


def normalize_all(*, apply_non_bank_changes: bool = False):
    return [normalize_file(DATA / fn, apply_non_bank_changes=apply_non_bank_changes)
            for fn in FILES]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preview conservative legal JSON text normalization")
    parser.add_argument("--apply-non-bank-files", action="store_true",
                        help="Write only glossary/term files; active legal banks remain transaction-only")
    args = parser.parse_args()
    print(json.dumps(normalize_all(apply_non_bank_changes=args.apply_non_bank_files),
                     ensure_ascii=False, indent=2))
