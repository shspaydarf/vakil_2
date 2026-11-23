from pathlib import Path
import ast

HANDLERS = Path('legal_bot/handlers.py')
MAIN = Path('legal_bot/main.py')


def _fn(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def test_contract_review_handoff_is_only_offered_after_case_issue_review():
    source = HANDLERS.read_text(encoding='utf-8')
    node = _fn(HANDLERS, 'ai_case_feature_select_cb')
    body = ast.get_source_segment(source, node)
    assert "callback_data=f'aicontract:{cid}'" in body
    assert body.index("if feature == 'review':") < body.index("callback_data=f'aicontract:{cid}'")


def test_contract_review_callback_checks_ownership_and_consent_before_external_call():
    source = HANDLERS.read_text(encoding='utf-8')
    node = _fn(HANDLERS, 'ai_contract_review_cb')
    body = ast.get_source_segment(source, node)
    assert body.index('get_case(q.from_user.id, cid)') < body.index('review_contract_risks')
    assert body.index('AI_EXTERNAL_DATA_CONSENT') < body.index('review_contract_risks')
    assert 'get_case_text(q.from_user.id, cid)' in body
    assert 'entitlement.refund' in body
    assert 'entitlement.commit' in body


def test_contract_review_callback_is_registered():
    source = MAIN.read_text(encoding='utf-8')
    assert "(ai_contract_review_cb, r'^aicontract:\\d+(?::[a-z_]+)?$')" in source
