from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")


def test_miniapp_loads_telegram_webapp_sdk_before_app():
    sdk = '<script src="https://telegram.org/js/telegram-web-app.js"></script>'
    assert sdk in INDEX
    assert INDEX.index(sdk) < INDEX.index('<script src="app.js"></script>')
    assert "script-src 'self' https://telegram.org" in INDEX


def test_miniapp_has_single_case_and_timeline_status_formatters():
    assert APP.count("function caseStatusLabel(") == 1
    assert APP.count("function timelineStatusLabel(") == 1
    assert "function statusLabel(" not in APP


def test_miniapp_account_uses_authenticated_account_endpoint():
    assert "async function openAccount()" in APP
    assert "api('/api/v1/account')" in APP
    assert "credits" in APP
    assert "subscription" in APP


def test_miniapp_exposes_case_tasks_and_lawyer_note():
    assert "/api/v1/cases/${currentCaseId}/tasks" in APP
    assert "/api/v1/cases/${currentCaseId}/note" in APP
    assert "function openTasks()" in APP
    assert "function openCaseNote()" in APP


def test_miniapp_shows_page_citation_audit_and_legal_source_warning():
    assert "citation_audit" in APP
    assert "صفحه‌های تطبیق‌یافته" in APP
    assert "استنادهای قانونی این پاسخ" in APP
    assert ".citation-audit" in (ROOT / "miniapp" / "styles.css").read_text(encoding="utf-8")
    assert "confidence_note" in APP
    assert "legal_authority_warning" in APP


def test_miniapp_api_helper_preserves_multipart_content_type_for_formdata_uploads():
    # Fetch must generate the multipart boundary itself; forcing application/json
    # makes the server reject every real Mini App file upload.
    assert 'const isFormData=typeof FormData!=="undefined"&&options.body instanceof FormData' in APP
    assert 'if(options.body&&!isFormData&&!headers["Content-Type"])headers["Content-Type"]="application/json"' in APP
    assert 'const selected=[...$("docPicker").files];$("docPicker").value="";uploadDocuments(selected);' in APP


def test_student_practice_is_separate_from_ai_and_has_essay_and_mcq_flows():
    assert "function openStudentPractice()" in APP
    assert "student-practice/essay-sample" in APP
    assert "student-practice/essay-next" in APP
    assert "student-practice/answer" in APP
    assert "AI" not in APP[APP.find('function openStudentPractice()'):APP.find('function openClassicSearch()')]
