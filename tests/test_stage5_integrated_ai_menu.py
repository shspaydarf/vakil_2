from pathlib import Path
import ast

HANDLERS = Path('legal_bot/handlers.py')
MAIN = Path('legal_bot/main.py')


def _fn(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def test_ai_menu_has_four_tools_and_no_duplicate_question_buttons():
    source = HANDLERS.read_text(encoding='utf-8')
    node = _fn(HANDLERS, 'ai_menu_cb')
    body = ast.get_source_segment(source, node)
    assert body.count('InlineKeyboardButton(') == 5  # four capabilities + home
    assert "callback_data='aifuture:question'" in body
    assert "callback_data='aifuture:documents'" in body
    assert "callback_data='aifuture:review'" in body
    assert "callback_data='aifuture:drafting'" in body
    assert "callback_data='aicases'" not in body
    assert "callback_data='aifuture:legal'" not in body


def test_question_menu_keeps_public_and_case_context_paths_explicit():
    source = HANDLERS.read_text(encoding='utf-8')
    node = _fn(HANDLERS, 'ai_future_placeholder_cb')
    body = ast.get_source_segment(source, node)
    question = body.split("if feature == 'question':", 1)[1].split("if feature == 'legal':", 1)[0]
    assert "callback_data='aifuture:legal'" in question
    assert "callback_data='aicases'" in question


def test_all_ai_feature_callbacks_are_registered():
    source = MAIN.read_text(encoding='utf-8')
    assert "r'^aifuture:(question|legal|documents|drafting|review)$'" in source
    assert "r'^aicasepick:(documents|drafting|review):\\d+$'" in source
