from legal_bot.ai_preference_context import build_ai_preference_context


def _prefs():
    return {
        "writing_style": {"tone": "formal", "detail_level": "concise"},
        "legal_analysis": {"analysis_structure": "irac"},
        "citations_and_sources": {"citation_density": "comprehensive", "citation_verification": True},
    }


def test_conflict_policy_defines_safety_and_system_as_top_priority():
    block = build_ai_preference_context(_prefs(), task="legal_drafting")
    assert "دستورهای سامانه/توسعه‌دهنده" in block
    assert "سیاست‌های ایمنی" in block


def test_accuracy_and_source_integrity_precede_preferences():
    block = build_ai_preference_context(_prefs(), task="legal_drafting")
    assert "صحت حقوقی" in block
    assert "منابع واقعاً در دسترس" in block
    assert "هیچ‌گاه قانون، رأی، ماده" in block


def test_current_request_overrides_saved_style_preferences():
    block = build_ai_preference_context(_prefs(), task="legal_drafting")
    assert "درخواست صریح همین نوبت کاربر" in block
    assert "درخواست فعلی با یک ترجیح سبک/قالبی تعارض دارد" in block


def test_saved_preferences_are_defaults_not_absolute_commands():
    block = build_ai_preference_context(_prefs(), task="legal_drafting")
    assert "درخواست فعلی ساکت یا مبهم است" in block
    assert "نه الزام مطلق" in block


def test_conflict_policy_is_not_truncated_at_supported_maximum():
    block = build_ai_preference_context(_prefs(), task="legal_drafting", max_chars=4000)
    assert block.endswith("محرمانگی محسوب نمی‌شوند.")
    assert len(block) <= 4000


def test_tiny_limit_omits_entire_context_instead_of_partial_guard():
    assert build_ai_preference_context(_prefs(), task="legal_drafting", max_chars=100) == ""
