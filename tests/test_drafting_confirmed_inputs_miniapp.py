import tempfile
from pathlib import Path


def _setup(monkeypatch, uid=995101):
    td = tempfile.TemporaryDirectory()
    db_path = str(Path(td.name) / 'test.sqlite3')
    monkeypatch.setenv('DB_PATH', db_path)
    from legal_bot import db
    db.DB_PATH = db_path
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table(); db.init_drafting_workflow_tables()
    db.register_user(uid, 'hash-intake', '9999', full_name='Intake User')
    with db.conn() as c:
        cur = c.execute("INSERT INTO cases(user_id,file_name,status,result,created_at) VALUES(?,?,?,?,?)", (uid, 'intake.pdf', 'ready', '', db.now_iso()))
        c.commit()
        cid = cur.lastrowid
    return td, db, cid


def test_confirmed_lawyer_inputs_are_rendered_with_separate_provenance(monkeypatch):
    td, db, cid = _setup(monkeypatch)
    try:
        from legal_bot.draft_engine import build_case_draft
        context = {
            'case': db.get_case(995101, cid), 'case_text': '',
            'chronology': {}, 'issues': {}, 'evidence': {}, 'authorities': {}, 'strategies': {},
            'plan': {'parties': [], 'purpose': 'دفاع', 'missing': []},
        }
        result = build_case_draft(
            995101, cid, analysis_context=context,
            confirmed_answers={'subject': 'مطالبه وجه بابت قرارداد'},
            confirmed_answer_labels={'subject': 'موضوع/خواسته'},
        )
        draft = result['draft']
        assert draft['lawyer_confirmed_inputs'][0]['source'] == 'lawyer_confirmed_input'
        assert draft['lawyer_confirmed_inputs'][0]['confirmed_by_lawyer'] is True
        assert 'موضوع/خواسته: مطالبه وجه بابت قرارداد' in draft['rendered_text']
        assert 'مستقلاً با اسناد پرونده راستی‌آزمایی نشده' in draft['rendered_text']
    finally:
        td.cleanup()


def test_drafting_workflow_persists_intake_and_passes_answers_into_draft(monkeypatch):
    td, db, cid = _setup(monkeypatch, 995102)
    try:
        import legal_bot.drafting_workflow as wf
        captured = {}
        original_gate = wf.build_case_consistency_gate
        monkeypatch.setattr(wf, 'build_case_consistency_gate', lambda uid, cid, **kw: captured.update(kw) or {'status': 'PASS', 'updated_draft': {'rendered_text': 'ok'}, 'draft': {'rendered_text': 'ok'}})
        monkeypatch.setattr(wf, 'build_case_output', lambda gate: {'draft_text': 'پیش‌نویس با ورودی وکیل'})
        monkeypatch.setattr(wf, 'save_draft_artifact', lambda *a, **kw: {'id': 'artifact-test', 'version_no': 1})

        first = wf.run_drafting_workflow(995102, cid)
        assert first['status'] == 'NEEDS_INFORMATION'
        state = wf.load_workflow_state(995102, cid)
        assert state['status'] == 'WAITING_FOR_INPUT'

        answers = {
            'parties': 'خواهان: الف؛ خوانده: ب',
            'subject': 'مطالبه وجه بابت قرارداد',
            'main_evidence': 'قرارداد امضاشده مورخ ۱۴۰۲/۰۱/۰۱',
        }
        second = wf.run_drafting_workflow(995102, cid, answers=answers)
        assert second['artifact']['id'] == 'artifact-test'
        assert captured['confirmed_answers'] == answers
        assert captured['confirmed_answer_labels']['subject'] == 'موضوع/خواسته'
        saved = wf.load_workflow_state(995102, cid)
        assert saved['answers'] == answers
    finally:
        td.cleanup()


def test_miniapp_has_draft_intake_form_and_resume_route():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    api = (root / 'legal_bot' / 'api.py').read_text(encoding='utf-8')
    css = (root / 'miniapp' / 'styles.css').read_text(encoding='utf-8')
    assert 'renderDraftIntakeForm' in app
    assert 'ثبت پاسخ‌ها و ادامه لایحه‌نویسی' in app
    assert '/draft-intake' in app and '/draft-intake' in api
    assert 'draft-intake-form' in css
    assert 'در این نسخه، فرم تکمیل این پرسش‌ها داخل Mini App هنوز پیاده‌سازی نشده' not in app
