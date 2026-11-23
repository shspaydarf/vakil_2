from legal_bot.lawyer_preferences import get_schema, normalize_preferences, suggest_from_feedback


def test_schema_has_seven_categories_and_no_persistence():
    schema = get_schema()
    assert len(schema["categories"]) == 7
    assert schema["stage"] == "2_of_6"
    assert schema["persistence_enabled"] is False
    assert schema["feedback_signals"]


def test_empty_profile_is_valid_and_unset_is_not_a_preference():
    normalized, count = normalize_preferences({})
    assert normalized == {}
    assert count == 0


def test_valid_profile_values_are_normalized():
    normalized, count = normalize_preferences({
        "writing_style": {"tone": "formal", "detail_level": "detailed"},
        "legal_analysis": {"counterargument_review": "true", "uncertainty_handling": False},
        "professional_context": {"practice_areas": ["property", "contracts", "property"]},
    })
    assert normalized["writing_style"]["tone"] == "formal"
    assert normalized["legal_analysis"]["counterargument_review"] is True
    assert normalized["legal_analysis"]["uncertainty_handling"] is False
    assert normalized["professional_context"]["practice_areas"] == ["property", "contracts"]
    assert count == 5


def test_unknown_category_and_field_are_rejected():
    for payload in ({"case_data": {"client_name": "x"}}, {"writing_style": {"unknown": "x"}}):
        try:
            normalize_preferences(payload)
        except ValueError:
            pass
        else:
            raise AssertionError("unknown profile data was accepted")


def test_invalid_choice_and_overlong_note_are_rejected():
    for payload in (
        {"writing_style": {"tone": "aggressive_unknown"}},
        {"writing_style": {"style_note": "x" * 501}},
        {"professional_context": {"practice_areas": ["property", "invalid"]}},
    ):
        try:
            normalize_preferences(payload)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid preference was accepted")


def test_suggestion_requires_confirmation_and_is_not_persisted():
    suggestion = suggest_from_feedback("too_long")
    assert suggestion["category"] == "writing_style"
    assert suggestion["field"] == "detail_level"
    assert suggestion["value"] == "concise"
    assert suggestion["requires_lawyer_confirmation"] is True
    assert suggestion["persisted"] is False


def test_unknown_feedback_signal_is_rejected():
    try:
        suggest_from_feedback("infer_from_confidential_case")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown feedback signal was accepted")


def test_api_schema_exposes_persistent_profile_and_preview_remains_non_persistent(monkeypatch):
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)

    handler._lawyer_preferences_schema(101)
    assert captured["status"] == 200
    assert captured["payload"]["data"]["persistence_enabled"] is True
    assert captured["payload"]["data"]["stage"] == "3_of_6"
    assert "profile" in captured["payload"]["data"]

    handler._lawyer_preferences_action(101, "preview", {
        "preferences": {"writing_style": {"tone": "formal"}},
        "lawyer_confirmed": True,
    })
    data = captured["payload"]["data"]
    assert data["lawyer_confirmed_for_preview"] is True
    assert data["persisted"] is False
    assert data["selected_count"] == 1


def test_api_suggestion_returns_proposal_only(monkeypatch):
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._lawyer_preferences_action(202, "suggest", {"signal": "too_few_citations"})
    suggestion = captured["payload"]["data"]["suggestion"]
    assert suggestion["requires_lawyer_confirmation"] is True
    assert suggestion["persisted"] is False
    assert suggestion["value"] == "comprehensive"


def test_miniapp_exposes_preferences_form_and_stage_boundaries():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    css = (root / "miniapp" / "styles.css").read_text(encoding="utf-8")
    assert "async function openLawyerPreferences()" in app
    assert "/api/v1/lawyer-preferences/schema" in app
    assert "/api/v1/lawyer-preferences/suggest" in app
    assert "/api/v1/lawyer-preferences/preview" in app
    assert "ذخیره دائمی ترجیحات" in app
    assert "/api/v1/lawyer-preferences/save" in app
    assert ".pref-category" in css


def test_tri_boolean_rejects_numeric_values():
    try:
        normalize_preferences({"legal_analysis": {"counterargument_review": 1}})
    except ValueError:
        pass
    else:
        raise AssertionError("numeric value must not be accepted as a boolean preference")


def test_miniapp_multi_select_uses_touch_friendly_checkbox_controls():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    css = (root / "miniapp" / "styles.css").read_text(encoding="utf-8")
    assert 'pref-multi-options' in app
    assert 'input[type=checkbox]:checked' in app
    assert '.pref-check-option' in css
