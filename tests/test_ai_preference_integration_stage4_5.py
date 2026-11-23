"""Stage 4.5 integration regression tests for lawyer preference memory."""
from legal_bot import ai


def _capture_call_feature(monkeypatch, feature, uid=701):
    captured = {}

    def fake_loader(received_uid, *, task="general", **kwargs):
        captured["uid"] = received_uid
        captured["task"] = task
        return f"PREF:{task}" if task != "extraction" else ""

    monkeypatch.setattr("legal_bot.ai_preference_context.load_ai_preference_context", fake_loader)
    monkeypatch.setattr(ai, "_call", lambda messages, temperature=0.05: captured.update(messages=messages) or "ok")
    ai._call_feature(
        [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "REQUEST"}],
        feature=feature,
        preference_uid=uid,
    )
    return captured


def test_all_preference_aware_workflows_map_to_expected_task_profiles(monkeypatch):
    expected = {
        "legal_question": "legal_question",
        "legal_drafting": "legal_drafting",
        "contract_review": "contract_review",
        "case_summary": "case_summary",
        "document_consistency_review": "document_review",
        "verified_summary": "case_summary",
        "text_assist_formal": "legal_drafting",
    }
    for feature, task in expected.items():
        captured = _capture_call_feature(monkeypatch, feature)
        assert captured["uid"] == 701
        assert captured["task"] == task
        assert any(m.get("content") == f"PREF:{task}" for m in captured["messages"])


def test_machine_extraction_workflows_do_not_receive_style_preferences(monkeypatch):
    for feature in ("document_structured_extraction", "scan_vision_transcription"):
        captured = _capture_call_feature(monkeypatch, feature)
        assert captured["uid"] == 701
        assert captured["task"] == "extraction"
        assert captured["messages"] == [
            {"role": "system", "content": "SYSTEM"},
            {"role": "user", "content": "REQUEST"},
        ]


def test_verified_summary_passes_authenticated_uid_to_preference_adapter(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai, "AI_ENABLED", True)
    monkeypatch.setattr(ai, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(ai, "AI_EXTERNAL_DATA_CONSENT", True)
    import sys, types
    fake_analysis = types.ModuleType("legal_bot.analysis")
    fake_analysis._snippets = lambda text, limit: [(1, "متن منبع معتبر")]
    fake_analysis._rank_summary_sentences = lambda text, snippets, limit: [{"text": "متن منبع معتبر", "page": 1}]
    monkeypatch.setitem(sys.modules, "legal_bot.analysis", fake_analysis)

    def fake_call_feature(messages, **kwargs):
        captured.update(kwargs)
        return '{"items":[{"text":"متن منبع معتبر","source_pages":[1]}]}'

    monkeypatch.setattr(ai, "_call_feature", fake_call_feature)
    result = ai.verified_summary("[صفحه 1] متن منبع معتبر", preference_uid=919)
    assert result == [{"text": "متن منبع معتبر", "page": 1, "source_pages": [1]}]
    assert captured["feature"] == "verified_summary"
    assert captured["preference_uid"] == 919


def test_no_uid_keeps_legacy_ai_prompt_without_preference_context(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai, "_call", lambda messages, temperature=0.05: captured.update(messages=messages) or "ok")
    ai._call_feature([{"role": "user", "content": "REQUEST"}], feature="legal_question")
    assert captured["messages"] == [{"role": "user", "content": "REQUEST"}]
