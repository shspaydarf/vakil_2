import tempfile
from pathlib import Path

from legal_bot import db
from legal_bot.config import CASE_STORAGE_DIR
from legal_bot.core.cases import CaseService
from legal_bot.core.documents import DocumentService, DocumentValidationError


def setup_module(module):
    module._old_db = db.DB_PATH
    module._tmp = tempfile.TemporaryDirectory()
    db.DB_PATH = Path(module._tmp.name) / "test.db"
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(3001, "hash-c", "1111", full_name="C")
    module._old_storage = CASE_STORAGE_DIR
    # Storage path is a config object; use its existing temp-safe location and clean by case id.


def teardown_module(module):
    db.DB_PATH = module._old_db
    module._tmp.cleanup()


def test_ingest_txt_registers_durable_document(tmp_path):
    case = CaseService().create(3001, "سند تست")
    src = tmp_path / "contract.txt"
    src.write_text("این یک متن حقوقی آزمایشی برای ثبت سند است.", encoding="utf-8")

    result = DocumentService().ingest_file(3001, case["id"], src, "contract.txt")
    assert result["document_id"]
    docs = DocumentService().list(3001, case["id"])
    assert len(docs) == 1
    assert docs[0]["file_name"] == "contract.txt"
    assert docs[0]["storage_path"]
    assert docs[0]["sha256"]
    assert Path(CASE_STORAGE_DIR / str(case["id"]) / "documents").exists()


def test_ingest_is_user_scoped(tmp_path):
    case = CaseService().create(3001, "مالکیت")
    src = tmp_path / "note.txt"
    src.write_text("متن کافی برای تست مرز مالکیت پرونده.", encoding="utf-8")
    try:
        DocumentService().ingest_file(9999, case["id"], src, "note.txt")
        assert False, "foreign user must not ingest into the case"
    except DocumentValidationError:
        pass


def test_invalid_content_does_not_create_document(tmp_path):
    case = CaseService().create(3001, "اعتبارسنجی")
    src = tmp_path / "fake.pdf"
    src.write_text("not a real pdf", encoding="utf-8")
    try:
        DocumentService().ingest_file(3001, case["id"], src, "fake.pdf")
        assert False, "invalid PDF must be rejected"
    except DocumentValidationError:
        pass
    assert DocumentService().list(3001, case["id"]) == []


def test_case_intake_workflow_completes_and_refunds_on_failure(tmp_path):
    from legal_bot.core import CaseIntakeService, CaseWorkflowError
    service = CaseIntakeService()
    src = tmp_path / "workflow.txt"
    src.write_text("تاریخ قرارداد 1405/07/01 و مبلغ آزمایشی.", encoding="utf-8")
    before = db.credit_status(3001)
    result = service.ingest_one(3001, "ورک‌فلو", src, "workflow.txt")
    assert result["case"]["status"] == "completed"
    after_success = db.credit_status(3001)
    assert (after_success.get("remaining") if after_success else None) == (before.get("remaining") if before else None) - 10
    with db.conn() as conn:
        reservation = conn.execute(
            "SELECT status FROM entitlement_reservations WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (3001,),
        ).fetchone()
        assert reservation["status"] == "committed"
    assert result["document"]["document_id"]
    assert not src.exists()

    before = db.credit_status(3001)
    bad = tmp_path / "bad.pdf"
    bad.write_text("fake", encoding="utf-8")
    try:
        service.ingest_one(3001, "ورک‌فلو ناموفق", bad, "bad.pdf")
        assert False, "invalid content must fail"
    except CaseWorkflowError:
        pass
    after = db.credit_status(3001)
    # The failed workflow must not consume an additional credit reservation.
    assert (after.get("remaining") if after else None) == (before.get("remaining") if before else None)


def test_miniapp_document_batch_completes_empty_case_and_exposes_safe_metadata(tmp_path):
    case = CaseService().create_empty(3001, "پرونده اسناد")
    one = tmp_path / "one.txt"
    two = tmp_path / "two.txt"
    one.write_text("قرارداد در تاریخ 1405/07/01 منعقد شد.", encoding="utf-8")
    two.write_text("الحاقیه در تاریخ 1405/07/05 امضا شد.", encoding="utf-8")

    result = DocumentService().add_files(3001, case["id"], [
        {"path": one, "name": "one.txt", "suffix": ".txt"},
        {"path": two, "name": "two.txt", "suffix": ".txt"},
    ])
    assert result["document_count"] == 2
    assert result["addition_no"] is None
    final = CaseService().get(3001, case["id"])
    assert final["status"] == "completed"
    docs = DocumentService().public_list(3001, case["id"])
    assert len(docs) == 2
    assert "extracted_text" not in docs[0]
    assert docs[0]["text_chars"] > 0
    assert docs[0]["preview"]


def test_document_delete_removes_registration_and_storage(tmp_path):
    case = CaseService().create_empty(3001, "حذف سند")
    src = tmp_path / "delete-me.txt"
    src.write_text("متن قابل استخراج برای حذف سند.", encoding="utf-8")
    result = DocumentService().add_files(3001, case["id"], [{"path": src, "name": src.name, "suffix": ".txt"}])
    doc_id = result["documents"][0]["document_id"]
    row = DocumentService().list(3001, case["id"])[0]
    stored = row["storage_path"]
    assert DocumentService().delete_registered(3001, case["id"], doc_id)
    assert DocumentService().list(3001, case["id"]) == []
    from legal_bot.config import CASE_STORAGE_DIR
    assert not (CASE_STORAGE_DIR.parent / stored).exists()


def test_later_upload_is_tracked_as_one_addition_session(tmp_path):
    case = CaseService().create_empty(3001, "افزودن بعدی")
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("متن سند اصلی پرونده.", encoding="utf-8")
    second.write_text("متن سند تکمیلی پرونده.", encoding="utf-8")
    DocumentService().add_files(3001, case["id"], [{"path": first, "name": first.name, "suffix": ".txt"}])
    result = DocumentService().add_files(3001, case["id"], [{"path": second, "name": second.name, "suffix": ".txt"}])
    assert result["addition_no"] == 1
    assert db.get_case_documents(3001, case["id"])
    assert db.get_case_addition_file_count(3001, case["id"], 1) == 1


def test_miniapp_document_batch_is_atomic_on_late_failure(tmp_path):
    case = CaseService().create_empty(3001, "آپلود اتمیک")
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.pdf"
    good.write_text("متن سند معتبر برای آزمون اتمیک بودن آپلود.", encoding="utf-8")
    bad.write_text("not a real pdf", encoding="utf-8")

    try:
        DocumentService().add_files(3001, case["id"], [
            {"path": good, "name": good.name, "suffix": ".txt"},
            {"path": bad, "name": bad.name, "suffix": ".pdf"},
        ])
        assert False, "mixed batch must fail"
    except DocumentValidationError:
        pass

    assert DocumentService().list(3001, case["id"]) == []
    assert db.count_case_additions(3001, case["id"]) == 0
    assert CaseService().get(3001, case["id"])['status'] == 'completed'


def test_webp_signature_is_supported_and_spoofed_webp_is_rejected(tmp_path):
    from legal_bot.storage import validate_supported_file

    valid = tmp_path / "image.webp"
    valid.write_bytes(b"RIFF" + (4).to_bytes(4, "little") + b"WEBP")
    invalid = tmp_path / "spoof.webp"
    invalid.write_bytes(b"not a webp file")

    assert validate_supported_file(valid, ".webp") is True
    assert validate_supported_file(invalid, ".webp") is False


def test_archived_case_lawyer_note_cannot_be_cleared(tmp_path):
    case = CaseService().create_empty(3001, "یادداشت محرمانه")
    assert db.save_case_lawyer_note(3001, case["id"], "یادداشت نمونه") is True
    assert CaseService().archive(3001, case["id"]) is True

    assert db.clear_case_lawyer_note(3001, case["id"]) is False
    note = db.get_case_lawyer_note(3001, case["id"])
    assert note and note["note_text"] == "یادداشت نمونه"


def test_task_mutations_require_matching_case_id():
    first = CaseService().create_empty(3001, "پرونده اول برای وظیفه")
    second = CaseService().create_empty(3001, "پرونده دوم برای وظیفه")
    task_id = db.add_case_task(3001, first["id"], "کار پرونده اول")
    assert task_id

    assert db.set_case_task_done(3001, task_id, True, case_id=second["id"]) is False
    assert db.delete_case_task(3001, task_id, case_id=second["id"]) is False
    assert db.list_case_tasks(3001, first["id"], include_done=True)[0]["done"] == 0
    assert db.list_case_tasks(3001, first["id"], include_done=True)[0]["id"] == task_id


def test_document_public_metadata_includes_reviewable_source_linked_fact_candidates(tmp_path):
    case = CaseService().create_empty(3001, "استخراج با منشأ")
    src = tmp_path / "facts.txt"
    src.write_text(
        "[صفحه 1]\nقرارداد مورخ ۱۴۰۵/۰۷/۰۱ منعقد شد. مبلغ قرارداد ۲۵۰,۰۰۰,۰۰۰ تومان است.\n"
        "[صفحه 2]\nخواهان: علی رضایی\nکد ملی: ۱۲۳۴۵۶۷۸۹۰",
        encoding="utf-8",
    )
    DocumentService().add_files(3001, case["id"], [{"path": src, "name": src.name, "suffix": ".txt"}])
    doc = DocumentService().public_list(3001, case["id"])[0]
    facts = doc["extracted_facts"]
    assert any(f["type"] == "date" and f["page"] == 1 and f["review_required"] for f in facts)
    assert any(f["type"] == "amount" and f["page"] == 1 for f in facts)
    assert any(f["type"] == "person_or_party" and f["page"] == 2 for f in facts)
    assert any(f["type"] == "national_id" and f["page"] == 2 for f in facts)
    assert doc["facts_need_review"] is True
    assert "extracted_text" not in doc


def test_document_fact_extraction_keeps_ambiguous_values_unverified():
    from legal_bot.document_facts import extract_document_facts
    facts = extract_document_facts("[صفحه 3]\nتاریخ: 01/02/03 و مبلغ 12,000 ریال")
    assert facts
    assert all(f["status"] == "needs_review" and f["review_required"] for f in facts)
    ambiguous = next(f for f in facts if f["type"] == "date")
    assert ambiguous["normalized_value"] is None
    assert ambiguous["page"] == 3


def test_pdf_page_limit_is_checked_before_extraction(tmp_path, monkeypatch):
    import fitz
    import legal_bot.files as file_module
    pdf_path = tmp_path / "too-many-pages.pdf"
    pdf = fitz.open()
    pdf.new_page(); pdf.new_page()
    pdf.save(pdf_path)
    pdf.close()
    monkeypatch.setattr(file_module, "MAX_DOCUMENT_PAGES", 1)
    try:
        file_module.extract_with_diagnostics(pdf_path)
        assert False, "PDF exceeding page limit must be rejected"
    except ValueError as exc:
        assert "تعداد صفحات" in str(exc)
