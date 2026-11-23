"""Per-lawyer reusable prompt and drafting-instruction library.

Resources are private to the authenticated lawyer. Built-in starters are static,
non-personalized examples and are never treated as legal authority.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from .db import conn, now_iso

STARTER_RESOURCES: List[Dict[str, str]] = [
    {
        "id": "starter-fact-map", "kind": "prompt", "title": "نقشه وقایع و ادعاها",
        "category": "تحلیل پرونده", "description": "تفکیک ادعا، واقعیت مستند و موضوع نامعلوم",
        "content": "بر اساس اطلاعات و اسناد همین پرونده، یک نقشه منظم تهیه کن. وقایع را به ترتیب زمانی بیاور و برای هر مورد مشخص کن: (۱) متن یا سند پشتیبان و محل آن، (۲) اینکه واقعیت مستند است یا صرفاً ادعا، (۳) تعارض‌ها یا ابهام‌ها، و (۴) اطلاعاتی که هنوز باید از موکل پرسیده شود. هیچ واقعیت، تاریخ، مبلغ یا استنادی را حدس نزن. اگر مدرک کافی نیست صریحاً بنویس «در اسناد موجود یافت نشد»."
    },
    {
        "id": "starter-evidence-gaps", "kind": "prompt", "title": "شناسایی خلأهای اثباتی",
        "category": "ادله و اثبات", "description": "پیوند ادعاها با مدارک و موارد نیازمند پیگیری",
        "content": "ادعاهای اصلی پرونده را جداگانه فهرست کن و برای هر ادعا نشان بده چه مدرکی در پرونده از آن پشتیبانی می‌کند، چه مدرکی با آن تعارض دارد و چه خلأ اثباتی باقی مانده است. شماره سند یا صفحه را فقط وقتی ذکر کن که در متن زمینه موجود باشد. نبودن مدرک در فایل‌های بررسی‌شده را با اثبات نبودن آن در دنیای واقعی یکی ندان. در پایان پرسش‌های تکمیلی برای وکیل تهیه کن."
    },
    {
        "id": "starter-contract-risk", "kind": "prompt", "title": "بازبینی محتاطانه قرارداد",
        "category": "قرارداد", "description": "ریسک‌ها، ابهام‌ها و بندهای نیازمند مذاکره",
        "content": "قرارداد انتخاب‌شده را فقط بر اساس متن موجود بررسی کن. جدول بساز با ستون‌های: موضوع/بند، عبارت یا محل استناد در سند، ابهام یا ریسک احتمالی، اثر عملی محتمل، پرسش لازم از موکل، و پیشنهاد اصلاح برای مذاکره. میان نقص نگارشی، ابهام قراردادی و نتیجه حقوقی قطعی تفاوت بگذار. قانون یا رأی تأییدنشده نساز و موارد نیازمند بررسی منبع رسمی را جدا علامت بزن."
    },
    {
        "id": "starter-chronology", "kind": "prompt", "title": "ساخت خط زمانی پرونده",
        "category": "تحلیل پرونده", "description": "تاریخ‌ها با ذکر منبع و سطح اطمینان",
        "content": "از اسناد و اطلاعات همین پرونده یک خط زمانی بساز. برای هر رویداد تاریخ عیناً درج‌شده، شرح کوتاه، سند/صفحه پشتیبان و ابهام احتمالی را بنویس. تاریخ‌های شمسی و میلادی را بدون اطمینان از تقویم تبدیل نکن. تاریخ استخراج‌شده را مهلت قانونی قطعی تلقی نکن. موارد فاقد تاریخ روشن را در بخشی جداگانه بیاور."
    },
    {
        "id": "starter-client-questions", "kind": "prompt", "title": "پرسش‌نامه تکمیلی موکل",
        "category": "مدیریت پرونده", "description": "سؤالات هدفمند برای تکمیل واقعیت‌ها و مدارک",
        "content": "با توجه به اطلاعات فعلی پرونده، حداکثر 15 سؤال کوتاه و غیرتکراری برای موکل تهیه کن. سؤال‌ها را بر اساس اهمیت دسته‌بندی کن و کنار هر سؤال توضیح بده کدام ابهام یا خلأ اطلاعاتی را برطرف می‌کند. اطلاعاتی را که در اسناد موجود پاسخ روشن دارد دوباره نپرس. از القای پاسخ یا فرض گرفتن صحت ادعاها خودداری کن."
    },
    {
        "id": "starter-draft-outline", "kind": "template", "title": "قالب ساختار پیش‌نویس حقوقی",
        "category": "نگارش", "description": "ساختار قابل تکمیل برای پیش‌نویس؛ نه متن آماده ثبت",
        "content": "یک پیش‌نویس اولیه با ساختار زیر تهیه کن و فقط بخش‌هایی را تکمیل کن که اطلاعات کافی دارند:\n۱) عنوان و مرجع مخاطب (در صورت معلوم بودن)\n۲) مشخصات پرونده و طرفین (فقط از اطلاعات ثبت‌شده)\n۳) خواسته یا موضوع درخواست\n۴) خلاصه منظم وقایع با ارجاع به مدارک موجود\n۵) استدلال‌ها و مستندات قابل راستی‌آزمایی\n۶) پاسخ به ادعاها یا ایرادهای طرف مقابل\n۷) درخواست نهایی\n۸) فهرست پیوست‌ها\nموارد نامعلوم را با [نیازمند تکمیل توسط وکیل] مشخص کن. هیچ ماده قانونی، رأی، تاریخ یا مشخصات ساختگی وارد نکن."
    },
    {
        "id": "starter-document-summary", "kind": "template", "title": "قالب خلاصه مدیریتی سند",
        "category": "اسناد", "description": "خلاصه استاندارد برای مرور سریع سند",
        "content": "سند را در قالب زیر خلاصه کن:\n- نوع و موضوع سند (در صورت قابل تشخیص بودن)\n- اشخاص/طرف‌های نام‌برده در متن\n- تعهدات و حقوق اصلی هر طرف\n- مبالغ و تاریخ‌های عیناً درج‌شده\n- شروط فسخ، ضمانت اجرا و حل اختلاف (اگر وجود دارد)\n- ابهام‌ها، تناقض‌ها و بخش‌های ناخوانا\n- مواردی که برای نتیجه‌گیری به بررسی انسانی یا سند تکمیلی نیاز دارند\nبرای هر داده مهم، عبارت کوتاه یا محل آن در سند را ذکر کن. اگر موردی یافت نشد، صریحاً اعلام کن."
    },
]


def init_lawyer_library() -> None:
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_library_items (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('prompt','template')),
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lawyer_library_user_updated ON lawyer_library_items(user_id, updated_at DESC)")
        c.commit()


def list_lawyer_library(uid: int, *, kind: str = "", query: str = "") -> List[Dict[str, Any]]:
    init_lawyer_library()
    uid = int(uid)
    kind = str(kind or "").strip().lower()
    if kind not in {"", "prompt", "template"}:
        raise ValueError("نوع منبع کتابخانه نامعتبر است.")
    query = str(query or "").strip()[:120]
    like = f"%{query}%"
    with conn() as c:
        rows = c.execute("""SELECT id,kind,title,category,description,content,created_at,updated_at
            FROM lawyer_library_items WHERE user_id=? AND (?='' OR kind=?)
            AND (?='' OR title LIKE ? OR category LIKE ? OR description LIKE ? OR content LIKE ?)
            ORDER BY updated_at DESC LIMIT 100""",
            (uid, kind, kind, query, like, like, like, like)).fetchall()
    own = [dict(row, source="personal") for row in rows]
    starters = []
    for item in STARTER_RESOURCES:
        if kind and item["kind"] != kind:
            continue
        if query and not any(query.casefold() in str(item.get(k, "")).casefold() for k in ("title", "category", "description", "content")):
            continue
        starters.append({**item, "source": "starter", "created_at": "", "updated_at": ""})
    return starters + own


def create_lawyer_library_item(uid: int, data: Dict[str, Any]) -> Dict[str, Any]:
    init_lawyer_library()
    if not isinstance(data, dict):
        raise ValueError("اطلاعات منبع کتابخانه نامعتبر است.")
    kind = str(data.get("kind") or "prompt").strip().lower()
    if kind not in {"prompt", "template"}:
        raise ValueError("نوع منبع باید دستور آماده یا قالب نگارش باشد.")
    title = str(data.get("title") or "").strip()
    category = str(data.get("category") or "عمومی").strip()
    description = str(data.get("description") or "").strip()
    content = str(data.get("content") or "").strip()
    if not title or len(title) > 100:
        raise ValueError("عنوان الزامی است و نباید بیش از ۱۰۰ نویسه باشد.")
    if len(category) > 60 or len(description) > 240:
        raise ValueError("دسته‌بندی یا توضیح بیش از حد طولانی است.")
    if not content or len(content) > 6000:
        raise ValueError("متن منبع الزامی است و حداکثر ۶۰۰۰ نویسه مجاز است.")
    ts = now_iso(); item_id = uuid.uuid4().hex
    with conn() as c:
        count = c.execute("SELECT COUNT(*) AS n FROM lawyer_library_items WHERE user_id=?", (int(uid),)).fetchone()["n"]
        if int(count or 0) >= 100:
            raise ValueError("حداکثر ۱۰۰ منبع شخصی در کتابخانه مجاز است.")
        c.execute("""INSERT INTO lawyer_library_items
            (id,user_id,kind,title,category,description,content,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (item_id, int(uid), kind, title, category, description, content, ts, ts))
        c.commit()
    return {"id": item_id, "kind": kind, "title": title, "category": category,
            "description": description, "content": content, "created_at": ts,
            "updated_at": ts, "source": "personal"}


def delete_lawyer_library_item(uid: int, item_id: str) -> bool:
    init_lawyer_library()
    with conn() as c:
        cur = c.execute("DELETE FROM lawyer_library_items WHERE id=? AND user_id=?", (str(item_id)[:80], int(uid)))
        c.commit()
        return cur.rowcount == 1


def update_lawyer_library_item(uid: int, item_id: str, data: Dict[str, Any]) -> Dict[str, Any] | None:
    init_lawyer_library()
    if not isinstance(data, dict):
        raise ValueError("اطلاعات منبع کتابخانه نامعتبر است.")
    kind = str(data.get("kind") or "prompt").strip().lower()
    title = str(data.get("title") or "").strip()
    category = str(data.get("category") or "عمومی").strip()
    description = str(data.get("description") or "").strip()
    content = str(data.get("content") or "").strip()
    if kind not in {"prompt", "template"}:
        raise ValueError("نوع منبع باید دستور آماده یا قالب نگارش باشد.")
    if not title or len(title) > 100:
        raise ValueError("عنوان الزامی است و نباید بیش از ۱۰۰ نویسه باشد.")
    if len(category) > 60 or len(description) > 240:
        raise ValueError("دسته‌بندی یا توضیح بیش از حد طولانی است.")
    if not content or len(content) > 6000:
        raise ValueError("متن منبع الزامی است و حداکثر ۶۰۰۰ نویسه مجاز است.")
    ts = now_iso()
    with conn() as c:
        cur = c.execute("""UPDATE lawyer_library_items SET kind=?,title=?,category=?,description=?,content=?,updated_at=?
            WHERE id=? AND user_id=?""",
            (kind, title, category, description, content, ts, str(item_id)[:80], int(uid)))
        if cur.rowcount != 1:
            return None
        c.commit()
        row = c.execute("""SELECT id,kind,title,category,description,content,created_at,updated_at
            FROM lawyer_library_items WHERE id=? AND user_id=?""", (str(item_id)[:80], int(uid))).fetchone()
    return dict(row, source="personal") if row else None
