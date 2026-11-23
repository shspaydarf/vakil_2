import ast
from pathlib import Path

HANDLERS = Path("legal_bot/handlers.py")
MAIN = Path("legal_bot/main.py")


def _function_node(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)


def test_main_menu_has_ai_submenu_entry():
    source = HANDLERS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    menu_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "menu_lawyer")
    menu_source = ast.get_source_segment(source, menu_fn)
    assert "دستیار هوشمند" in menu_source
    assert "callback_data='aimenu'" in menu_source


def test_ai_submenu_callbacks_are_registered():
    source = MAIN.read_text(encoding="utf-8")
    assert "(ai_menu_cb, r'^aimenu$')" in source
    assert "(ai_cases_cb, r'^aicases$')" in source


def test_ocrstatus_does_not_call_unrelated_ai_handler():
    node = _function_node(HANDLERS, "ocrstatus")
    called_names = {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    referenced_names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
    assert "to_thread" in called_names or any(
        isinstance(child, ast.Attribute) and child.attr == "to_thread"
        for child in ast.walk(node)
    )
    assert "ocr_status" in referenced_names
    assert "ai_cb" not in called_names


def test_ai_submenu_contains_current_feature_and_future_placeholders():
    source = HANDLERS.read_text(encoding="utf-8")
    node = _function_node(HANDLERS, "ai_menu_cb")
    menu_source = ast.get_source_segment(source, node)
    assert "callback_data='aifuture:question'" in menu_source
    assert "callback_data='aifuture:legal'" not in menu_source
    assert menu_source.count("InlineKeyboardButton(") == 5  # four tools + home
    assert "callback_data='aifuture:documents'" in menu_source
    assert "callback_data='aifuture:drafting'" in menu_source
    assert "callback_data='aifuture:review'" in menu_source


def test_ai_feature_callback_is_registered_and_public_qna_is_activated():
    main_source = MAIN.read_text(encoding="utf-8")
    handlers_source = HANDLERS.read_text(encoding="utf-8")
    assert "ai_future_placeholder_cb" in main_source
    assert "r'^aifuture:(question|legal|documents|drafting|review)$'" in main_source
    node = _function_node(HANDLERS, "ai_future_placeholder_cb")
    function_source = ast.get_source_segment(handlers_source, node)
    assert "if feature == 'legal'" in function_source
    assert "awaiting_ai_question" in function_source
    assert "فقط متن همین سؤال" in function_source
    assert "if feature == 'question':" in function_source
    assert "callback_data='aicases'" in function_source


def test_case_dependent_ai_tools_open_case_picker_and_keep_selection():
    handlers_source = HANDLERS.read_text(encoding="utf-8")
    main_source = MAIN.read_text(encoding="utf-8")
    placeholder = _function_node(HANDLERS, "ai_future_placeholder_cb")
    placeholder_source = ast.get_source_segment(handlers_source, placeholder)
    selector = _function_node(HANDLERS, "ai_case_feature_select_cb")
    selector_source = ast.get_source_segment(handlers_source, selector)

    assert "feature in {'documents', 'drafting', 'review'}" in placeholder_source
    assert "list_cases(q.from_user.id, 20)" in placeholder_source
    assert "callback_data=f'aicasepick:{feature}:{cid}'" in placeholder_source
    assert "(ai_case_feature_select_cb, r'^aicasepick:(documents|drafting|review):\\d+$')" in main_source
    assert "get_case(q.from_user.id, cid)" in selector_source
    assert "set_active_case(q.from_user.id, cid)" in selector_source
    assert "context.user_data['ai_selected_case_id'] = cid" in selector_source
    assert "context.user_data['ai_selected_feature'] = feature" in selector_source
    assert "تحلیل و خلاصه‌سازی پرونده" in handlers_source


def test_existing_case_ai_flow_records_selected_case_context():
    handlers_source = HANDLERS.read_text(encoding="utf-8")
    node = _function_node(HANDLERS, "case_ai_cb")
    function_source = ast.get_source_segment(handlers_source, node)
    assert "context.user_data['ai_selected_case_id'] = cid" in function_source
    assert "context.user_data['ai_selected_feature'] = 'question'" in function_source


def test_public_qna_dispatches_only_question_without_implicit_case_context():
    source = HANDLERS.read_text(encoding="utf-8")
    node = _function_node(HANDLERS, "handle_text_message") if "handle_text_message" in source else None
    # The canonical text router is embedded in the message handler; assert the
    # awaiting state routes directly to dispatch with no case-context keyboard.
    assert "if context.user_data.get('awaiting_ai_question')" in source
    branch = source.split("if context.user_data.get('awaiting_ai_question'):", 1)[1].split("await context.user_data", 1)[0]
    assert "await dispatch_ai_question(update, context, value)" in branch
    assert "_ai_case_keyboard" not in branch


def test_general_legal_prompt_avoids_fabricated_or_unverified_law(monkeypatch):
    from legal_bot import ai
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: messages[0]['content'])
    result = ai.ask_ai_question('آیا این کار قانونی است؟')
    assert 'کشور یا حوزه قضایی' in result
    assert 'هیچ ماده قانونی' in result
    assert 'منبع به‌روز تأییدشده' in result
