from legal_bot.brief_writer import review_brief


def test_review_flags_repetition_and_vague_legal_citation_without_rewriting_text():
    text = '''ریاست محترم شعبه دادگاه
موضوع: مطالبه وجه
خواهان بر اساس قرارداد مبلغ مورد مطالبه را پرداخت کرده است. این موضوع طبق قانون قابل پیگیری است.
خواهان بر اساس قرارداد مبلغ مورد مطالبه را پرداخت کرده است.
خواسته: صدور حکم شایسته و الزام خوانده.
پیوست: قرارداد و رسید پرداخت.
تاریخ: ۱۴۰۳/۰۱/۰۱
با احترام.'''
    report = review_brief(text)
    assert 'به قانون/مقررات به‌صورت کلی' in report or 'استناد صریح به ماده/اصل' in report
    assert 'این گزارش ویرایش حقوقی قطعی نیست' in report


def test_review_does_not_call_review_flags_proof_of_falsehood():
    text = '''ریاست محترم دادگاه
موضوع: بررسی اختلاف قراردادی
بر اساس قرارداد، طرفین درباره زمان تحویل توافق کرده‌اند.
این موضوع قطعاً به نفع موکل است.
خواسته: رسیدگی و صدور تصمیم مقتضی.
مستندات: قرارداد، صفحه ۲.
تاریخ: ۱۴۰۴/۰۲/۰۱
با احترام، این متن برای بررسی اولیه ارائه شده است.'''
    report = review_brief(text)
    assert 'عبارت با لحن قطعی' in report
    assert 'این گزارش ویرایش حقوقی قطعی نیست' in report
