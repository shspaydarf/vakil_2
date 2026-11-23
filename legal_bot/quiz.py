# -*- coding: utf-8 -*-
"""Student practice exams: level (year) -> course -> 10+ questions."""
import json
import random
from pathlib import Path
from .config import DATA_DIR

_QUIZ_FILE = Path(DATA_DIR) / "iran" / "student_quiz.json"
_ESSAY_FILE = Path(DATA_DIR) / "iran" / "student_essay.json"
_CACHE = None
_ESSAY_CACHE = None


def _load():
    global _CACHE
    if _CACHE is None:
        with open(_QUIZ_FILE, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def _load_essay():
    global _ESSAY_CACHE
    if _ESSAY_CACHE is None:
        p = Path(DATA_DIR) / "iran" / "student_essay.json"
        if p.exists():
            with open(p, encoding="utf-8") as f:
                _ESSAY_CACHE = json.load(f)
        else:
            _ESSAY_CACHE = {"categories": [], "disclaimer": ""}
    return _ESSAY_CACHE


def disclaimer():
    return _load().get("disclaimer") or "نمونه آموزشی است."


def list_levels():
    return list(_load().get("levels") or [])


def list_courses(level_id):
    out = []
    for c in _load().get("courses") or []:
        if c.get("level") == level_id:
            out.append({
                "id": c["id"],
                "title": c["title"],
                "count": len(c.get("questions") or []),
            })
    return out


def get_course_questions(course_id, limit=12, shuffle=True):
    for c in _load().get("courses") or []:
        if c.get("id") == course_id:
            qs = list(c.get("questions") or [])
            if shuffle:
                random.shuffle(qs)
            return qs[:limit], c.get("title") or course_id
    return [], course_id


def list_categories():
    out = []
    for c in _load().get("courses") or []:
        out.append({
            "id": c["id"],
            "title": f"{c.get('level_title','')}: {c.get('title','')}"[:60],
            "count": len(c.get("questions") or []),
        })
    return out


def get_questions(category_id, limit=12, shuffle=True):
    qs, _ = get_course_questions(category_id, limit=limit, shuffle=shuffle)
    return qs


# legacy aliases
def list_terms():
    return [{"id": x["id"], "title": x["title"]} for x in list_levels()]


def list_essay_categories():
    data = _load_essay()
    return [
        {"id": c["id"], "title": c["title"], "count": len(c.get("items") or [])}
        for c in data.get("categories") or []
    ]


def essay_disclaimer():
    return _load_essay().get("disclaimer") or "پاسخ نمونه راهنمای مطالعه است."


def get_essay_items(category_id, limit=5, shuffle=True):
    data = _load_essay()
    for c in data.get("categories") or []:
        if c.get("id") == category_id:
            items = list(c.get("items") or [])
            if shuffle:
                random.shuffle(items)
            return items[:limit]
    return []


def format_question(q, index, total):
    opts = q.get("options") or []
    letters = ["۱", "۲", "۳", "۴"]
    lines = [f"❓ سوال {index} از {total}", "", q.get("q", ""), ""]
    for i, o in enumerate(opts[:4]):
        lines.append(f"{letters[i]}) {o}")
    return "\n".join(lines)


def format_essay(item, index, total):
    return (
        f"✍️ سوال تشریحی {index} از {total}\n\n"
        f"{item.get('q','')}\n\n"
        "پس از فکر کردن، «نمایش پاسخ نمونه» را بزنید."
    )


def check_answer(q, choice_index):
    correct = int(q.get("answer", 0))
    ok = int(choice_index) == correct
    explain = q.get("explain") or ""
    opts = q.get("options") or []
    right_text = opts[correct] if correct < len(opts) else ""
    if ok:
        return True, f"✅ درست\n\n{explain}".strip()
    return False, f"❌ نادرست\nپاسخ صحیح: {right_text}\n\n{explain}".strip()
