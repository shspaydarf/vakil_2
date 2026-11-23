from legal_bot.brief_writer import render_structured_brief


def test_professional_renderer_uses_document_headings_and_paragraphs():
    draft = {
        'draft_type': 'لایحه دفاعیه',
        'caption': {'court': 'شعبه آزمایشی', 'parties': ['خواهان', 'خوانده'], 'subject': 'مطالبه وجه'},
        'facts': [{'text': 'در تاریخ ثبت‌شده، قرارداد میان طرفین تنظیم شده است.', 'document_name': 'قرارداد', 'page': 2}],
        'issues': [{'label': 'اعتبار قرارداد', 'question': 'آیا قرارداد پیوست برای ادعا کفایت می‌کند؟'}],
        'arguments': [{'heading': 'قرارداد پیوست', 'position': 'بررسی اصالت و مفاد قرارداد', 'reasoning_steps': [{'step': 'strategy_frame', 'text': 'بررسی مفاد قرارداد با ادعای مطرح‌شده'}], 'supporting_evidence': [], 'authority_refs': [], 'missing_support': [{'text': 'اصل قرارداد باید بررسی شود.'}]}],
        'requested_relief': ['رسیدگی به خواسته مطابق محتویات پرونده'],
        'citations': [],
    }
    text = render_structured_brief(draft)
    assert '۱. شرح وقایع و اطلاعات مستند' in text
    assert 'در تاریخ ثبت‌شده، قرارداد میان طرفین تنظیم شده است.' in text
    assert 'مأخذ: قرارداد، صفحه 2' in text
    assert '۳.1. قرارداد پیوست' in text
    assert 'اصل قرارداد باید بررسی شود.' in text
    assert 'رسیدگی به خواسته مطابق محتویات پرونده' in text
    assert 'منبع تأییدشده‌ای برای درج خودکار ثبت نشده است' in text


def test_professional_renderer_does_not_invent_missing_facts_or_relief():
    text = render_structured_brief({'draft_type': 'لایحه دفاعیه', 'facts': [], 'issues': [], 'arguments': [], 'requested_relief': [], 'citations': []})
    assert '[شرح وقایع مستند باید با مراجعه به پرونده تکمیل شود.]' in text
    assert '[خواسته نهایی باید بر اساس پرونده و نظر تنظیم‌کننده تعیین و تأیید شود.]' in text
    assert 'استدلال حدسی' in text
    assert 'با احترام،' in text
