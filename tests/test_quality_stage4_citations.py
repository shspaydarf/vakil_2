from legal_bot.citation_verifier import audit_citations, render_citation_audit
from legal_bot.brief_writer import review_brief


def test_citation_audit_marks_registry_status_without_claiming_legal_validity():
    result = audit_citations('به موجب ماده ۱۰ قانون مدنی، موضوع باید بررسی شود.')
    assert result['count'] == 1
    assert result['mentions'][0]['law_title'] == 'قانون مدنی'
    assert result['mentions'][0]['verification_level'] in {
        'registry_verified_text_status', 'user_document_not_independently_verified',
        'manual_verification_required', 'historical_text_warning', 'source_known_text_pending'
    }
    assert result['legal_validity_certified'] is False
    assert result['api_used'] is False


def test_unknown_law_citation_is_not_silently_accepted():
    result = audit_citations('مطابق ماده ۹۹۹ قانون فرضی، اقدام انجام شد.')
    assert result['count'] == 1
    assert result['mentions'][0]['verification_level'] == 'manual_verification_required'
    assert 'منبع رسمی' in render_citation_audit('مطابق ماده ۹۹۹ قانون فرضی، اقدام انجام شد.')


def test_brief_review_includes_citation_traceability_section():
    text = '''ریاست محترم شعبه دادگاه
موضوع: مطالبه وجه
خواهان بر اساس قرارداد و رسید، وجه را پرداخت کرده است. به موجب ماده ۱۰ قانون مدنی، قرارداد باید بررسی شود.
خواسته: رسیدگی و صدور حکم مقتضی.
پیوست: قرارداد و رسید پرداخت.
تاریخ: ۱۴۰۳/۰۱/۰۱
با احترام. متن برای بررسی اولیه ارائه شده است.'''
    report = review_brief(text)
    assert 'گزارش راستی‌آزمایی مقدماتی استنادها' in report
    assert 'صحت شماره ماده' in report or 'تطبیق' in report
