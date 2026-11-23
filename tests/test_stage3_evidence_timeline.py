from urllib.parse import urlencode


def _boot(monkeypatch, tmp_path):
    import legal_bot.config as config
    import legal_bot.db as db
    db_path = tmp_path / "stage3.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table(); db.init_drafting_workflow_tables()
    return db


def test_timeline_extracts_source_linked_events_and_conflict(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31001
    db.register_user(uid, "h", "031", full_name="Timeline")
    cid = db.create_case(uid, "Timeline case")
    text = (
        "[صفحه 1]\n"
        "در تاریخ 1402/02/10 قرارداد منعقد شد.\n"
        "در تاریخ 1402/03/15 مبلغ قرارداد پرداخت شد.\n"
        "در تاریخ 1402/04/20 اظهارنامه ارسال شد.\n"
        "[صفحه 2]\n"
        "در تاریخ 1402/05/01 قرارداد منعقد شد.\n"
    )
    db.add_case_document(cid, "contract.txt", 2, text)

    from legal_bot.timeline_engine import build_case_chronology
    result = build_case_chronology(uid, cid)
    assert result["events"]
    assert all(e["sources"][0]["document_id"] for e in result["events"])
    assert any((e.get("date") or {}).get("jalali_date") == "1402/02/10" for e in result["events"])
    assert result["counts"]["events"] == len(result["events"])


def test_evidence_matrix_never_treats_origin_as_independent_support(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31002
    db.register_user(uid, "h2", "032", full_name="Evidence")
    cid = db.create_case(uid, "Evidence case")
    origin = "خواهان ادعا می‌کند مبلغ قرارداد را در تاریخ 1402/02/10 پرداخت کرده است."
    independent = "رسید بانکی نشان می‌دهد مبلغ قرارداد در تاریخ 1402/02/10 به حساب طرف مقابل واریز شده است."
    db.add_case_document(cid, "claim.txt", 1, origin)
    db.add_case_document(cid, "receipt.txt", 1, independent)

    from legal_bot.evidence_engine import build_evidence_matrix
    result = build_evidence_matrix(uid, cid)
    assert result["claims"]
    claim = result["claims"][0]
    matrix = next(m for m in result["matrix"] if m["claim_id"] == claim["claim_id"])
    assert all(x.get("origin") is False for x in matrix["evidence"] if x.get("document_id") == db.get_case_documents(uid, cid)[1]["id"])
    assert matrix["independent_evidence_count"] >= 1
    assert claim["claim_status"] == "supported"


def test_stage3_api_filters_and_rejects_invalid_evidence_status(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31003
    db.register_user(uid, "h3", "033", full_name="API")
    cid = db.create_case(uid, "API case")
    db.add_case_document(cid, "a.txt", 1, "در تاریخ 1402/01/01 قرارداد منعقد شد. پرداخت انجام شد.")

    from legal_bot import api
    class Handler:
        pass
    h = Handler()
    h.path = f"/api/v1/cases/{cid}/timeline?undated=0"
    h._send = lambda status, payload: (status, payload)
    # Bind the actual handler method to keep the HTTP contract close to production.
    import types
    timeline = types.MethodType(api.APIHandler._timeline, h)
    status, payload = timeline(uid, cid)
    assert status == 200
    assert payload["ok"] is True
    assert payload["data"]["counts"]["undated"] == 0

    h.path = f"/api/v1/cases/{cid}/evidence?status=not-a-status"
    evidence = types.MethodType(api.APIHandler._evidence, h)
    try:
        evidence(uid, cid)
    except ValueError as exc:
        assert "وضعیت" in str(exc)
    else:
        raise AssertionError("invalid evidence status was accepted")


def test_timeline_api_filters_status_and_event_type(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31004
    db.register_user(uid, "h4", "034", full_name="Filters")
    cid = db.create_case(uid, "Filtered timeline")
    db.add_case_document(cid, "events.txt", 1,
        "در تاریخ 1402/02/10 قرارداد منعقد شد.\n"
        "در تاریخ 1402/03/15 مبلغ قرارداد پرداخت شد.\n")

    from legal_bot import api
    import types
    h = type("Handler", (), {})()
    h._send = lambda status, payload: (status, payload)
    h.path = f"/api/v1/cases/{cid}/timeline?type=payment"
    status, payload = types.MethodType(api.APIHandler._timeline, h)(uid, cid)
    assert status == 200
    events = payload["data"]["events"]
    assert events and all(e["event_type"] == "payment" for e in events)
    assert payload["data"]["filtered_counts"]["events"] == len(events)

    h.path = f"/api/v1/cases/{cid}/timeline?status=not-a-status"
    try:
        types.MethodType(api.APIHandler._timeline, h)(uid, cid)
    except ValueError as exc:
        assert "وضعیت" in str(exc)
    else:
        raise AssertionError("invalid timeline status was accepted")


def test_evidence_origin_is_explicit_and_same_document_page_is_not_independent(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31005
    db.register_user(uid, "h5", "035", full_name="Provenance")
    cid = db.create_case(uid, "Provenance case")
    text = (
        "[صفحه 1]\n"
        "خواهان ادعا می‌کند مبلغ قرارداد را در تاریخ 1402/02/10 پرداخت کرده است.\n"
        "[صفحه 2]\n"
        "خواهان ادعا می‌کند مبلغ قرارداد را در تاریخ 1402/02/10 پرداخت کرده است.\n"
    )
    db.add_case_document(cid, "single-source.txt", 2, text)
    from legal_bot.evidence_engine import build_evidence_matrix
    result = build_evidence_matrix(uid, cid)
    assert result["claims"]
    claim = result["claims"][0]
    assert claim["origin_source"]["document_name"] == "single-source.txt"
    matrix = next(m for m in result["matrix"] if m["claim_id"] == claim["claim_id"])
    assert matrix["independent_evidence_count"] == 0
    assert claim["claim_status"] != "supported"


def test_timeline_date_conflict_includes_both_source_spans(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 31006
    db.register_user(uid, "h6", "036", full_name="Conflict sources")
    cid = db.create_case(uid, "Conflict source case")
    db.add_case_document(cid, "contract-a.txt", 1,
        "[صفحه 1]\nدر تاریخ 1402/02/10 قرارداد منعقد شد و طرفین تعهدات را پذیرفتند.")
    db.add_case_document(cid, "contract-b.txt", 1,
        "[صفحه 1]\nدر تاریخ 1402/02/15 قرارداد منعقد شد و طرفین تعهدات را پذیرفتند.")

    from legal_bot.timeline_engine import build_case_chronology
    result = build_case_chronology(uid, cid)
    assert result["conflicts"], "expected possible date conflict to be detected"
    conflict = result["conflicts"][0]
    assert conflict["review_required"] is True
    assert conflict["interpretation"] == "possible_date_conflict"
    assert len(conflict["sources"]) >= 2
    assert {s["document_name"] for s in conflict["sources"]} >= {"contract-a.txt", "contract-b.txt"}
    assert all(s["page"] == 1 for s in conflict["sources"])
    assert all(s["snippet"] for s in conflict["sources"])
