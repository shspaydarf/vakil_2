
import tempfile
from pathlib import Path

def _setup(monkeypatch, user_id=991005):
    td=tempfile.TemporaryDirectory()
    db_path=Path(td.name)/"test.sqlite3"
    monkeypatch.setenv("DB_PATH",str(db_path))
    from legal_bot import config, db
    monkeypatch.setattr(config,"DB_PATH",str(db_path))
    monkeypatch.setattr(db,"DB_PATH",db_path)
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(user_id,"hash","5678",full_name="Stage5")
    return td,db

def test_case_ai_reserve_commit_and_history(monkeypatch):
    td,db=_setup(monkeypatch)
    try:
        from legal_bot.core.cases import CaseService
        from legal_bot.core.product import ProductCaseService
        import legal_bot.core.product as product
        cid=CaseService().create(991005,"پرونده AI",stage="research",priority="high")["id"]
        monkeypatch.setattr(product,"ask_ai_question",lambda question,case_summary="",standard_prompt="",preference_uid=None: "پاسخ مبتنی بر پرونده")
        result=ProductCaseService().ask_ai(991005,cid,"نقاط ضعف چیست؟",context_mode="full")
        assert result["answer"]=="پاسخ مبتنی بر پرونده"
        assert result["metered"] is True
        rows=db.get_case_ai_history(991005,cid,5)
        assert len(rows)==1 and rows[0]["question"]=="نقاط ضعف چیست؟"
        status=db.credit_status(991005)
        assert status["remaining"] < status["allowance"]
    finally:
        td.cleanup()

def test_case_ai_failure_refunds(monkeypatch):
    td,db=_setup(monkeypatch,991006)
    try:
        from legal_bot.core.cases import CaseService
        from legal_bot.core.product import ProductCaseService
        import legal_bot.core.product as product
        cid=CaseService().create(991006,"پرونده AI")["id"]
        before=db.credit_status(991006)["remaining"]
        def fail(*a,**k): raise RuntimeError("provider down")
        monkeypatch.setattr(product,"ask_ai_question",fail)
        try: ProductCaseService().ask_ai(991006,cid,"سؤال")
        except RuntimeError: pass
        else: assert False
        assert db.credit_status(991006)["remaining"]==before
        assert db.get_case_ai_history(991006,cid,5)==[]
    finally:
        td.cleanup()

def test_case_ai_rejects_archived(monkeypatch):
    td,db=_setup(monkeypatch,991007)
    try:
        from legal_bot.core.cases import CaseService
        from legal_bot.core.product import ProductCaseService, ProductCaseError
        cid=CaseService().create(991007,"پرونده بایگانی")["id"]
        db.finish_case(cid, "{}")
        assert CaseService().archive(991007,cid)
        try: ProductCaseService().ask_ai(991007,cid,"سؤال")
        except ProductCaseError as exc: assert "بایگانی" in str(exc)
        else: assert False
    finally:
        td.cleanup()


def test_case_summary_samples_beginning_middle_and_end(monkeypatch):
    from legal_bot import ai
    source = ('ابتدای پرونده و مشخصات. ' * 100) + ('بخش میانی درباره تعهدات. ' * 100) + ('انتهای پرونده و نتیجه ابلاغ. ' * 100)
    sampled, truncated = ai._sample_case_text(source, 1200)
    assert truncated is True
    assert len(sampled) <= 1200
    assert 'بخش‌هایی از متن برای کنترل هزینه ارسال نشده‌اند' in sampled
    assert 'گزیده میانی متن اصلی' in sampled
    assert 'گزیده پایانی متن اصلی' in sampled
    assert 'ابتدای پرونده' in sampled
    assert 'انتهای پرونده' in sampled


def test_case_summary_prompt_enforces_evidence_and_uncertainty(monkeypatch):
    from legal_bot import ai
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_TEXT_MAX_CHARS', 5000)
    calls = []
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: calls.append((messages, temperature)) or '📄 خلاصه پرونده')
    result = ai.summarize_case_for_lawyer('[صفحه 1]\nادعای خواهان: مبلغ پرداخت نشده است.', 'خلاصه محلی: ادعای پرداخت بررسی نشده است.')
    assert result.startswith('📄 خلاصه پرونده')
    prompt = calls[0][0][1]['content']
    assert 'هر دو را جداگانه گزارش کن' in prompt
    assert 'نقاط قوت و ضعف مستند' in prompt
    assert 'وجود ندارد' in prompt
    assert calls[0][1] == 0.1


def test_case_ai_full_context_keeps_document_excerpts_within_budget(monkeypatch):
    td, db = _setup(monkeypatch, 991008)
    try:
        from legal_bot.core.cases import CaseService
        from legal_bot.core.product import ProductCaseService
        import legal_bot.core.product as product

        cid = CaseService().create(991008, "پرونده context کامل")['id']
        source = (
            "DOCUMENT_BEGIN_TOKEN\n" + ("ابتدای سند. " * 1800) +
            "DOCUMENT_MIDDLE_TOKEN\n" + ("میانه سند. " * 1800) +
            "DOCUMENT_END_TOKEN\n"
        )
        monkeypatch.setattr(product, 'get_case_text', lambda uid, case_id: source)
        monkeypatch.setattr(product, 'build_case_chronology', lambda *a, **k: {'events': [], 'conflicts': []})
        monkeypatch.setattr(product, 'build_case_issues', lambda *a, **k: {'issues': []})
        monkeypatch.setattr(product, 'build_evidence_matrix', lambda *a, **k: {'claims': [], 'matrix': []})
        monkeypatch.setattr(product, 'build_case_guidance', lambda text: {'overview': ['راهنمایی'], 'source_stats': {}})
        monkeypatch.setattr(product, 'build_case_authorities', lambda *a, **k: {'authorities': [], 'warnings': [], 'counts': {}})
        captured = {}
        monkeypatch.setattr(product, 'ask_ai_question', lambda question, case_summary='', standard_prompt='', preference_uid=None: captured.update(context=case_summary) or 'پاسخ')

        result = ProductCaseService().ask_ai(991008, cid, 'سؤال درباره پرونده', context_mode='full')
        assert result['answer'] == 'پاسخ'
        assert result['context_coverage']['document_text_sampled'] is True
        context = captured['context']
        assert len(context) <= 11000
        assert 'خلاصه هوشمندی پرونده' in context
        assert 'متن اسناد پرونده' in context
        assert 'DOCUMENT_BEGIN_TOKEN' in context
        assert '[گزیده میانی متن اصلی]' in context
        assert 'میانه سند.' in context
        assert 'DOCUMENT_END_TOKEN' in context
        assert 'فقط گزیده‌ای' in context
    finally:
        td.cleanup()


def test_case_ai_documents_mode_skips_legal_intelligence_engines(monkeypatch):
    td, db = _setup(monkeypatch, 991009)
    try:
        from legal_bot.core.cases import CaseService
        from legal_bot.core.product import ProductCaseService
        import legal_bot.core.product as product

        cid = CaseService().create(991009, "پرونده اسناد")['id']
        monkeypatch.setattr(product, 'get_case_text', lambda uid, case_id: '[صفحه ۱]\nمتن سند انتخابی')
        def forbidden(*args, **kwargs):
            raise AssertionError('documents mode must not run intelligence engines')
        monkeypatch.setattr(product, 'build_case_chronology', forbidden)
        monkeypatch.setattr(product, 'build_case_issues', forbidden)
        monkeypatch.setattr(product, 'build_evidence_matrix', forbidden)
        monkeypatch.setattr(product, 'build_case_guidance', forbidden)
        monkeypatch.setattr(product, 'build_case_authorities', forbidden)
        captured = {}
        monkeypatch.setattr(product, 'ask_ai_question', lambda question, case_summary='', standard_prompt='', preference_uid=None: captured.update(context=case_summary) or 'پاسخ')

        result = ProductCaseService().ask_ai(991009, cid, 'خلاصه سند چیست؟', context_mode='documents')
        assert result['context_coverage']['document_text_included'] is True
        assert 'متن اسناد پرونده' in captured['context']
        assert 'متن سند انتخابی' in captured['context']
        assert 'Timeline' not in captured['context']
        assert 'Evidence:' not in captured['context']
    finally:
        td.cleanup()
