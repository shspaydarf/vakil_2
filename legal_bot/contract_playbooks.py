"""Built-in contract review playbooks for MACHINA's AI workflow.

These are issue-spotting checklists, not legal opinions or statements of law.
They are intentionally static in this stage: no database or user data involved.
"""
from __future__ import annotations

from copy import deepcopy


_PLAYBOOKS = {
    "construction": {
        "id": "construction",
        "title": "قرارداد پیمانکاری",
        "description": "بررسی تعهدات اجرای کار، پرداخت، زمان‌بندی و تحویل.",
        "criteria": (
            ("scope", "موضوع، دامنه و مشخصات فنی کار"),
            ("parties", "مشخصات طرفین، نمایندگان و حدود اختیار امضا"),
            ("schedule", "مدت، نقاط عطف، برنامه زمان‌بندی و تمدید"),
            ("payment", "مبلغ، صورت‌وضعیت، کسورات و زمان پرداخت"),
            ("variation", "دستورکار، تغییر مقادیر و کارهای اضافی"),
            ("delay", "تأخیر، تمدید مدت و وجه التزام"),
            ("quality", "استانداردها، نظارت، آزمون و رفع عیب"),
            ("handover", "تحویل موقت/قطعی و صورت‌جلسه‌ها"),
            ("security", "ضمانت‌نامه‌ها، حسن انجام کار و کسور تضمین"),
            ("termination", "تعلیق، فسخ، خاتمه و تسویه"),
            ("disputes", "حل اختلاف، داوری و مرجع رسیدگی"),
        ),
        "follow_up_questions": (
            "آیا شرایط عمومی یا خصوصی پیمان، نقشه‌ها و مشخصات فنی پیوست قرارداد هستند؟",
            "آیا صورت‌جلسه‌های تحویل کارگاه، دستورکارها و صورت‌وضعیت‌ها در دسترس‌اند؟",
            "آیا تمدید مدت یا ادعای تأخیر از سوی هر یک از طرفین ثبت شده است؟",
        ),
        "risk_focus": ("ابهام دامنه کار", "پرداخت و کسورات", "تأخیر و تمدید", "تحویل و تضمین", "فسخ و تسویه"),
    },
    "lease": {
        "id": "lease",
        "title": "قرارداد اجاره",
        "description": "بررسی رابطه موجر و مستأجر، مدت، اجاره‌بها، تحویل و پایان اجاره.",
        "criteria": (
            ("parties", "مشخصات طرفین، مالک/موجر و اختیار نمایندگی"),
            ("property", "توصیف دقیق مورد اجاره، ملحقات و وضعیت تحویل"),
            ("term", "تاریخ شروع و پایان، تمدید و شرایط ادامه تصرف"),
            ("rent", "اجاره‌بها، ودیعه، سررسید و روش پرداخت"),
            ("use", "نوع استفاده مجاز، محدودیت‌ها و تغییر کاربری"),
            ("maintenance", "تعمیرات، هزینه‌ها و مسئولیت نگهداری"),
            ("utilities", "شارژ، قبوض، مالیات‌ها و هزینه‌های جانبی"),
            ("transfer", "انتقال منافع، واگذاری به غیر و اجاره مجدد"),
            ("default", "عدم پرداخت، تخلف از شروط و مهلت رفع تخلف"),
            ("deposit", "استرداد ودیعه، تضمین‌ها و شرایط کسر مبالغ"),
            ("termination", "انقضا، تمدید، فسخ، تخلیه و تحویل مورد اجاره"),
            ("disputes", "حل اختلاف و مرجع رسیدگی"),
        ),
        "follow_up_questions": (
            "آیا صورت‌جلسه تحویل، فهرست تجهیزات و تصاویر وضعیت ملک وجود دارد؟",
            "پرداخت اجاره‌بها و ودیعه با چه رسیدها یا گردش حسابی قابل اثبات است؟",
            "آیا اخطار، اظهارنامه یا توافقی درباره تمدید یا تخلیه انجام شده است؟",
        ),
        "risk_focus": ("مشخصات و تحویل ملک", "مدت و تمدید", "پرداخت و ودیعه", "تعمیرات و استفاده", "تخلیه و استرداد تضمین"),
    },
    "sale": {
        "id": "sale",
        "title": "قرارداد بیع و فروش",
        "description": "بررسی مورد معامله، اختیار فروشنده، ثمن، پرداخت، تحویل و ادعاهای مربوط به عیب یا عدم انطباق.",
        "criteria": (
            ("parties", "مشخصات طرفین و اختیار قانونی/قراردادی امضا"),
            ("subject", "توصیف، مقدار، اوصاف و قابلیت شناسایی مورد معامله"),
            ("ownership", "مدارک مالکیت یا اختیار انتقال و محدودیت‌های اعلام‌شده"),
            ("price", "ثمن، اجزای قیمت، سررسیدها و شیوه پرداخت"),
            ("payment_proof", "رسیدها، چک‌ها، حواله‌ها و مانده ثمن"),
            ("delivery", "موعد، محل، تشریفات و اسناد تحویل"),
            ("conformity", "تطبیق مورد تحویل با اوصاف و مشخصات توافق‌شده"),
            ("defects", "ادعای عیب، کسری، عدم انطباق و زمان اطلاع"),
            ("documents", "اسناد انتقال، مجوزها، مدارک فنی و پیوست‌ها"),
            ("warranties", "تعهدات تضمینی، مسئولیت‌ها و وجه التزام"),
            ("termination", "شرایط فسخ، انفساخ، استرداد عوضین و تسویه"),
            ("disputes", "حل اختلاف و مرجع رسیدگی"),
        ),
        "follow_up_questions": (
            "آیا مورد معامله و تمام اوصاف مورد توافق در قرارداد و پیوست‌ها دقیقاً مشخص شده‌اند؟",
            "آیا مدارک مالکیت، استعلام‌ها یا مجوزهای لازم ارائه شده‌اند؟",
            "آیا پرداخت ثمن و تحویل مورد معامله با اسناد مستقل قابل تطبیق است؟",
        ),
        "risk_focus": ("هویت و مالکیت مورد معامله", "ابهام اوصاف", "پرداخت ثمن", "تحویل و عدم انطباق", "فسخ و استرداد"),
    },
}


def list_contract_playbooks() -> list[dict]:
    """Return safe display metadata for all built-in playbooks."""
    return [
        {"id": p["id"], "title": p["title"], "description": p["description"]}
        for p in _PLAYBOOKS.values()
    ]


def get_contract_playbook(playbook_id: str) -> dict | None:
    """Return a detached playbook definition, or None for an unknown id."""
    playbook = _PLAYBOOKS.get(str(playbook_id or "").strip())
    return deepcopy(playbook) if playbook else None


def build_playbook_checklist(playbook_id: str) -> dict | None:
    """Build a normalized checklist payload suitable for later AI integration."""
    playbook = get_contract_playbook(playbook_id)
    if playbook is None:
        return None
    return {
        "playbook_id": playbook["id"],
        "title": playbook["title"],
        "criteria": [
            {"id": criterion_id, "label": label, "status": "نیازمند بررسی", "evidence": []}
            for criterion_id, label in playbook["criteria"]
        ],
        "follow_up_questions": list(playbook["follow_up_questions"]),
        "risk_focus": list(playbook["risk_focus"]),
        "notice": "این چک‌لیست صرفاً برای شناسایی موضوعات نیازمند بررسی است؛ نتیجه حقوقی قطعی محسوب نمی‌شود.",
    }
