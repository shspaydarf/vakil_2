from pathlib import Path
import ast


def test_ai_drafting_feature_reuses_existing_case_workflow_without_api_call():
    source = Path('legal_bot/handlers.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'ai_case_feature_select_cb')
    body = ast.get_source_segment(source, node)
    assert "if feature == 'drafting'" in body
    assert "load_workflow_state(q.from_user.id, cid)" in body
    assert "callback_data=f'cstart161:{cid}'" in body
    assert "callback_data=f'coutput160:{cid}'" in body
    drafting = body.split("if feature == 'drafting':", 1)[1].split("if feature == 'review':", 1)[0]
    assert 'هیچ درخواست خارجی' in drafting
    assert 'review_case_contradictions' not in drafting
    assert 'summarize_case_for_lawyer' not in drafting


def test_ai_drafting_feature_checks_case_and_archived_status_before_workflow():
    source = Path('legal_bot/handlers.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'ai_case_feature_select_cb')
    body = ast.get_source_segment(source, node)
    assert body.index('case = get_case(q.from_user.id, cid)') < body.index("if feature == 'drafting':")
    assert body.index("if not case or case.get('status') == 'archived':") < body.index("if feature == 'drafting':")
