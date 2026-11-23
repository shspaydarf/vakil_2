import tempfile
from pathlib import Path


def _boot(monkeypatch, tmp_path):
    import legal_bot.config as config
    import legal_bot.db as db
    db_path = tmp_path / "product.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    return db


def test_product_workspace_is_single_contract(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 10101
    db.register_user(uid, "hash-product", "0001", full_name="Product")
    cid = db.create_case(uid, "پرونده محصول")
    assert cid
    db.add_case_document(cid, "test.txt", 1, "این متن برای آزمون پرونده است. پرداخت و قرارداد و تعهد در آن آمده است.")

    from legal_bot.core.product import ProductCaseService
    service = ProductCaseService()
    result = service.workspace(uid, cid, include_deep_intelligence=False)

    assert result["contract_version"] == 2
    assert result["case"]["id"] == cid
    assert result["document_count"] == 1
    assert "intelligence" in result
    assert result["ai"]["auto_invoked"] is False
    assert result["drafting"]["human_review_required"] is True
    assert result["capabilities"]["final_legal_approval"] is False


def test_product_workspace_enforces_ownership(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    db.register_user(11111, "hash-owner", "0002", full_name="Owner")
    db.register_user(22222, "hash-other", "0003", full_name="Other")
    cid = db.create_case(11111, "پرونده خصوصی")
    assert cid

    from legal_bot.core.product import ProductCaseError, ProductCaseService
    try:
        ProductCaseService().workspace(22222, cid, include_deep_intelligence=False)
    except ProductCaseError as exc:
        assert "پرونده" in str(exc)
    else:
        raise AssertionError("cross-user case access was not rejected")


def test_product_intelligence_summary_is_actionable(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 30303
    db.register_user(uid, "hash-intel", "0004", full_name="Intel")
    cid = db.create_case(uid, "پرونده هوشمند")
    db.add_case_document(cid, "test.txt", 1, "خوانده مدعی است که پرداخت انجام شده است. تاریخ قرارداد 1402/01/01 است.")
    from legal_bot.core.product import ProductCaseService
    result = ProductCaseService().workspace(uid, cid, include_deep_intelligence=True)
    summary = result["intelligence"]["summary"]
    assert summary["risk_level"] in {"low", "medium", "high"}
    assert "headline" in summary
    assert isinstance(summary["findings"], list)
    assert isinstance(summary["recommended_actions"], list)


def test_intelligence_confidence_does_not_follow_text_sufficiency():
    from legal_bot.core.product import _build_intelligence_summary
    summary = _build_intelligence_summary(
        {"conflicts": []}, {"issues": [{"issue_id": "i1"}]},
        {"claims": [], "matrix": []},
        {"authorities": [{"verification_status": "review_required"}], "counts": {"authority_gaps": 1}},
        {}, {"sufficient": True, "overview": ["تحلیل پایه"], "source_stats": {"x": 1}},
    )
    assert summary["confidence"] == "low"
    assert summary["confidence_basis"] == "rule_based_not_semantically_validated"
    assert summary["unverified_legal_authority_count"] == 1
    assert summary["legal_authority_gaps"] == 1


def test_page_citation_audit_only_checks_page_label_existence():
    from legal_bot.core.product import _audit_answer_page_citations
    result = _audit_answer_page_citations(
        "طبق سند (منبع: [صفحه ۲]) و صفحه 9 هم مهم است.",
        "[صفحه 1]\nمتن اول\n[صفحه 2]\nمتن دوم",
    )
    assert result["status"] == "partially_matched_page_labels"
    assert result["matched_page_labels"] == [2]
    assert result["unmatched_page_labels"] == [9]
    assert result["semantic_support_checked"] is False


def test_page_citation_audit_reports_missing_page_markers():
    from legal_bot.core.product import _audit_answer_page_citations
    result = _audit_answer_page_citations("منبع: صفحه 3", "متن بدون علامت صفحه")
    assert result["status"] == "cannot_validate_page_labels"
    assert result["semantic_support_checked"] is False


def test_dashboard_aggregates_case_scoped_operational_data_without_pii(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 40404
    db.register_user(uid, "hash-dashboard", "0005", full_name="Dashboard")
    cid = db.create_case(uid, "پرونده داشبورد")
    db.add_case_document(cid, "سند اصلی.txt", 1, "متن استخراج‌شده پرونده")
    db.add_case_task(uid, cid, "اقدام عقب‌افتاده", "2020-01-01")
    db.add_case_event(uid, cid, "review", "بازبینی سند", "جزئیات خصوصی نباید در خلاصه باشد")
    db.add_case_important_dates(uid, cid, [{
        "date_jalali": "1405/08/20", "date_gregorian": "2026-11-11",
        "description": "موعد مندرج در سند", "source_page": 2, "source_text": "متن خصوصی منبع",
    }])
    with db.conn() as conn:
        conn.execute("INSERT INTO case_lawyer_notes(case_id,user_id,note_text,updated_at) VALUES(?,?,?,?)",
                     (cid, uid, "یادداشت محرمانه", "2026-10-31T10:00:00"))
        conn.commit()

    from legal_bot.core.product import ProductCaseService
    result = ProductCaseService().workspace(uid, cid, include_deep_intelligence=False)
    dash = result["dashboard"]
    assert dash["dashboard_contract_version"] == 1
    assert dash["overview"]["open_task_count"] == 1
    assert dash["overview"]["overdue_task_count"] == 1
    assert dash["overview"]["important_date_count"] == 1
    assert dash["lawyer_note"]["has_note"] is True
    assert "یادداشت محرمانه" not in str(dash)
    assert "متن خصوصی منبع" not in str(dash)
    assert "جزئیات خصوصی" not in str(dash)
    assert dash["ai"]["auto_invoked"] is False
    assert dash["data_quality"]["coverage"]["deep_intelligence_computed"] is False


def test_lightweight_workspace_does_not_call_deep_engines(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 50505
    db.register_user(uid, "hash-light", "0006", full_name="Light")
    cid = db.create_case(uid, "پرونده سبک")
    import legal_bot.core.product as product
    def forbidden(*args, **kwargs):
        raise AssertionError("deep engine must not run in lightweight mode")
    monkeypatch.setattr(product, "build_case_chronology", forbidden)
    monkeypatch.setattr(product, "build_case_issues", forbidden)
    monkeypatch.setattr(product, "build_evidence_matrix", forbidden)
    monkeypatch.setattr(product, "build_case_authorities", forbidden)
    monkeypatch.setattr(product, "build_case_strategies", forbidden)
    monkeypatch.setattr(product, "build_case_guidance", forbidden)
    result = product.ProductCaseService().workspace(uid, cid, include_deep_intelligence=False)
    assert result["dashboard"]["data_quality"]["coverage"]["deep_intelligence_computed"] is False


def test_dashboard_attention_prioritizes_overdue_and_near_due_actions(monkeypatch, tmp_path):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    db = _boot(monkeypatch, tmp_path)
    uid = 60606
    db.register_user(uid, "hash-priority", "0007", full_name="Priority")
    cid = db.create_case(uid, "پرونده اولویت‌بندی")
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    db.add_case_task(uid, cid, "کار عقب‌افتاده", (today - timedelta(days=2)).isoformat())
    db.add_case_task(uid, cid, "کار فردا", (today + timedelta(days=1)).isoformat())
    db.add_case_task(uid, cid, "کار هفته آینده", (today + timedelta(days=8)).isoformat())

    from legal_bot.core.product import ProductCaseService
    dash = ProductCaseService().workspace(uid, cid, include_deep_intelligence=False)["dashboard"]
    alerts = dash["attention"]["alerts"]
    assert alerts[0]["type"] == "overdue_task"
    assert alerts[0]["priority_band"] == "urgent"
    assert alerts[0]["priority_score"] > alerts[1]["priority_score"]
    assert any(a["type"] == "upcoming_task" and a["priority_band"] == "urgent" for a in alerts)
    assert dash["attention"]["priority_summary"]["top_action"]["id"] == alerts[0]["id"]
    assert dash["attention"]["priority_summary"]["method"] == "deterministic_rules_not_legal_deadline_validation"


def test_dashboard_alerts_are_stably_sorted_and_bounded(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 70707
    db.register_user(uid, "hash-bounded", "0008", full_name="Bounded")
    cid = db.create_case(uid, "پرونده هشدارها")
    for index in range(30):
        db.add_case_task(uid, cid, f"کار عقب‌افتاده {index}", "2020-01-01")
    from legal_bot.core.product import ProductCaseService
    dash = ProductCaseService().workspace(uid, cid, include_deep_intelligence=False)["dashboard"]
    alerts = dash["attention"]["alerts"]
    assert len(alerts) <= 20
    assert alerts == sorted(alerts, key=lambda a: (-a["priority_score"], str(a.get("due_date") or "9999-99-99"), a["id"]))


def test_dashboard_draft_preview_excludes_full_draft_content(monkeypatch, tmp_path):
    db = _boot(monkeypatch, tmp_path)
    uid = 80808
    db.register_user(uid, "hash-draft-dashboard", "0009", full_name="Draft dashboard")
    cid = db.create_case(uid, "پرونده پیش‌نویس")
    from legal_bot.drafting_artifacts import save_draft_artifact
    secret_body = "متن کامل و محرمانه پیش‌نویس که نباید در خلاصه داشبورد باشد"
    save_draft_artifact(uid, cid, status="draft", draft_text=secret_body, brief_type="لایحه دفاعیه")

    from legal_bot.core.product import ProductCaseService
    result = ProductCaseService().workspace(uid, cid, include_deep_intelligence=False)
    dashboard = result["dashboard"]
    assert dashboard["drafting"]["latest"]["brief_type"] == "لایحه دفاعیه"
    assert "draft_text" not in dashboard["drafting"]["latest"]
    assert secret_body not in str(dashboard)


def test_case_instrument_gauge_ticks_follow_upper_semicircle():
    from pathlib import Path
    app_js = Path("miniapp/app.js").read_text(encoding="utf-8")
    # The main dial runs left (0) -> top (50) -> right (100).
    assert "const a=(-180+i*18)*Math.PI/180" in app_js
    assert "aria-label=\"فشار عملیاتی پرونده ${topScore} از ۱۰۰\"" in app_js


def test_case_instrument_controls_have_keyboard_focus_style():
    from pathlib import Path
    css = Path("miniapp/styles.css").read_text(encoding="utf-8")
    assert ".machina-mini-gauge:focus-visible" in css
    assert ".machina-alert-row:focus-visible" in css
