import time


def test_case_context_cache_hits_and_returns_defensive_copy():
    from legal_bot.core.case_context_cache import clear_cache, get_or_build, cache_stats
    clear_cache()
    calls = []
    def build():
        calls.append(1)
        return {"issues": [{"label": "payment"}]}
    first, hit1 = get_or_build(10, 20, "fingerprint-a", build)
    first["issues"][0]["label"] = "mutated"
    second, hit2 = get_or_build(10, 20, "fingerprint-a", build)
    assert hit1 is False and hit2 is True
    assert second["issues"][0]["label"] == "payment"
    assert len(calls) == 1
    assert cache_stats()["hits"] == 1


def test_case_context_cache_isolated_by_user_and_case():
    from legal_bot.core.case_context_cache import clear_cache, get_or_build
    clear_cache()
    calls = []
    build = lambda: calls.append(1) or {"owner": len(calls)}
    get_or_build(10, 20, "same", build)
    get_or_build(11, 20, "same", build)
    get_or_build(10, 21, "same", build)
    assert len(calls) == 3


def test_case_context_cache_invalidates_on_fingerprint_change():
    from legal_bot.core.case_context_cache import clear_cache, get_or_build, cache_stats
    clear_cache()
    calls = []
    build = lambda: calls.append(1) or {"version": len(calls)}
    first, _ = get_or_build(10, 20, "document-hash-1", build)
    second, hit = get_or_build(10, 20, "document-hash-2", build)
    assert first["version"] == 1
    assert second["version"] == 2 and hit is False
    assert cache_stats()["invalidations"] == 1


def test_case_fingerprint_changes_when_document_text_or_case_event_changes():
    from legal_bot.core.case_context_cache import case_fingerprint
    case = {"updated_at": "2026-10-31T10:00:00", "file_name": "case"}
    docs = [{"id": 1, "created_at": "x", "page_count": 1, "extracted_text": "متن الف"}]
    events = [{"id": 1, "created_at": "x", "event_type": "note", "title": "الف", "details": ""}]
    original = case_fingerprint(case=case, documents=docs, events=events)
    changed_doc = case_fingerprint(case=case, documents=[{**docs[0], "extracted_text": "متن ب"}], events=events)
    changed_event = case_fingerprint(case=case, documents=docs, events=[{**events[0], "details": "تغییر"}])
    assert original != changed_doc
    assert original != changed_event
