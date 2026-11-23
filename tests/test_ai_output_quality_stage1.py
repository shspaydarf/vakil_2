from legal_bot.text_guard import prepare_ai_answer

def plain(text):
    return str(text).replace('\u2066', '').replace('\u2069', '')


def test_ai_answer_removes_known_internal_scaffolding_and_cleans_persian_text():
    answer = 'نتیجه حقوقی  : بررسی شود\nstrategy_frame: internal only\nمنبع  : سند شماره ۱'
    cleaned = plain(prepare_ai_answer(answer))
    assert 'strategy_frame' not in cleaned
    assert 'نتیجه حقوقی: بررسی شود' in cleaned
    assert 'منبع: سند شماره ۱' in cleaned


def test_ai_answer_collapses_only_adjacent_exact_duplicate_lines():
    answer = 'جمع‌بندی\nجمع‌بندی\n\nدلیل اول\nدلیل دوم\nجمع‌بندی'
    cleaned = prepare_ai_answer(answer)
    assert cleaned.splitlines().count('جمع‌بندی') == 2
    assert 'دلیل اول\nدلیل دوم' in cleaned


def test_ai_answer_empty_or_internal_only_result_is_empty():
    assert prepare_ai_answer('   \n  ') == ''
    assert prepare_ai_answer('strategy_frame: internal only') == ''


def test_ai_answer_preserves_numbers_and_legal_content():
    answer = 'طبق ماده ۱۰ قانون مدنی، قرارداد بررسی شود.\nتاریخ: ۱۴۰۵/۰۵/۱۱'
    cleaned = plain(prepare_ai_answer(answer))
    assert 'ماده ۱۰ قانون مدنی' in cleaned
    assert '۱۴۰۵/۰۵/۱۱' in cleaned
