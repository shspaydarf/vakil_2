from legal_bot.analysis import search_case_documents, format_case_search_results


def test_search_across_documents_preserves_document_provenance():
    docs = [
        {"id": 11, "file_name": "قرارداد.pdf", "page_count": 2,
         "extracted_text": "[صفحه 1]\nمبلغ قرارداد یک میلیارد ریال است.\n[صفحه 2]\nامضای طرفین"},
        {"id": 12, "file_name": "الحاقیه.pdf", "page_count": 1,
         "extracted_text": "[صفحه 1]\nمبلغ قرارداد دو میلیارد ریال تعیین شد."},
    ]
    hits = search_case_documents(docs, "مبلغ قرارداد")
    assert len(hits) == 2
    assert {(h["document_id"], h["file_name"], h["page"]) for h in hits} == {
        (11, "قرارداد.pdf", 1), (12, "الحاقیه.pdf", 1)
    }


def test_search_skips_documents_without_extracted_text():
    docs = [
        {"id": 1, "file_name": "اسکن.pdf", "extracted_text": ""},
        {"id": 2, "file_name": "متن.txt", "extracted_text": "[صفحه 3]\nخواسته دعوا مطالبه وجه است."},
    ]
    hits = search_case_documents(docs, "مطالبه وجه")
    assert len(hits) == 1
    assert hits[0]["document_id"] == 2
    assert hits[0]["page"] == 3


def test_search_is_bounded_and_empty_query_returns_no_results():
    docs = [{"id": 1, "file_name": "سند", "extracted_text": "\n".join(["موضوع قرارداد"] * 20)}]
    assert search_case_documents(docs, "   ") == []
    assert len(search_case_documents(docs, "موضوع", max_results=3)) == 3


def test_formatter_displays_source_document_and_page():
    rendered = format_case_search_results([
        {"file_name": "دادخواست.pdf", "document_id": 7, "page": 4,
         "snippet": "خواهان تقاضای مطالبه وجه دارد."}
    ], "مطالبه وجه")
    assert "دادخواست.pdf" in rendered
    assert "صفحه 4" in rendered
    assert "شناسه سند: 7" in rendered


def test_formatter_groups_results_by_source_document_and_counts_hits():
    rendered = format_case_search_results([
        {"file_name": "قرارداد.pdf", "document_id": 4, "page": 2,
         "line": 3, "snippet": "مبلغ قرارداد یک میلیارد ریال است."},
        {"file_name": "قرارداد.pdf", "document_id": 4, "page": 5,
         "line": 1, "snippet": "پرداخت مبلغ قرارداد انجام شد."},
        {"file_name": "الحاقیه.pdf", "document_id": 9, "page": None,
         "snippet": "مبلغ جدید توافق شد."},
    ], "مبلغ قرارداد")
    assert "3 مورد در 2 سند" in rendered
    assert rendered.count("📄 قرارداد.pdf") == 1
    assert "شناسه سند: 4 | تعداد تطبیق: 2" in rendered
    assert "📄 الحاقیه.pdf" in rendered
    assert "شماره صفحه در دسترس نیست" in rendered
    assert "متن سند اصلی را بررسی کنید" in rendered


def test_formatter_explains_search_coverage_when_no_results():
    rendered = format_case_search_results([], "عبارت ناموجود")
    assert "نتیجه‌ای" in rendered
    assert "اسناد اسکن‌شده" in rendered


def test_api_case_document_search_is_scoped_and_returns_provenance(monkeypatch):
    from legal_bot import api

    class FakeCaseService:
        def get(self, uid, cid):
            assert (uid, cid) == (77, 9)
            return {"id": cid}

    class FakeDocumentService:
        def list(self, uid, cid):
            assert (uid, cid) == (77, 9)
            return [{"id": 31, "file_name": "قرارداد.pdf", "page_count": 1,
                     "extracted_text": "[صفحه 1]\nمبلغ قرارداد ده میلیون ریال است."}]

    monkeypatch.setattr(api, "CaseService", FakeCaseService)
    monkeypatch.setattr(api, "DocumentService", FakeDocumentService)

    class FakeHandler:
        path = "/api/v1/cases/9/search?q=%D9%85%D8%A8%D9%84%D8%BA"
        def _send(self, status, payload):
            self.status, self.payload = status, payload
            return payload

    handler = FakeHandler()
    handler._search_case_documents = api.APIHandler._search_case_documents.__get__(handler, FakeHandler)
    handler._search_case_documents(77, 9)
    data = handler.payload["data"]
    assert handler.status == 200
    assert data["count"] == 1
    assert data["items"][0]["document_id"] == 31
    assert data["items"][0]["file_name"] == "قرارداد.pdf"
    assert data["items"][0]["page"] == 1
    assert "اصل سند" in data["verification_note"]


def test_api_case_document_search_rejects_missing_case(monkeypatch):
    from legal_bot import api

    class FakeCaseService:
        def get(self, uid, cid):
            return None

    monkeypatch.setattr(api, "CaseService", FakeCaseService)

    class FakeHandler:
        path = "/api/v1/cases/999/search?q=test"
        def _send(self, status, payload):
            return status, payload

    handler = FakeHandler()
    handler._search_case_documents = api.APIHandler._search_case_documents.__get__(handler, FakeHandler)
    try:
        handler._search_case_documents(77, 999)
    except api.DocumentValidationError:
        pass
    else:
        raise AssertionError("search must reject a case not owned by the caller")


def test_api_case_document_search_rejects_empty_or_oversized_query(monkeypatch):
    from legal_bot import api

    class FakeCaseService:
        def get(self, uid, cid):
            return {"id": cid}

    monkeypatch.setattr(api, "CaseService", FakeCaseService)

    class FakeHandler:
        def __init__(self, query):
            from urllib.parse import quote
            self.path = f"/api/v1/cases/9/search?q={quote(query)}"
        def _send(self, status, payload):
            return status, payload

    for query in ("   ", "x" * 201):
        handler = FakeHandler(query)
        handler._search_case_documents = api.APIHandler._search_case_documents.__get__(handler, FakeHandler)
        try:
            handler._search_case_documents(77, 9)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid search query was accepted")


def test_miniapp_contains_case_document_search_controls_and_api_call():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    css = (root / "miniapp" / "styles.css").read_text(encoding="utf-8")
    assert 'id="caseDocSearchForm"' in app
    assert "runCaseDocumentSearch" in app
    assert "/api/v1/cases/${encodeURIComponent(currentCaseId)}/search?q=" in app
    assert ".case-search-group" in css
