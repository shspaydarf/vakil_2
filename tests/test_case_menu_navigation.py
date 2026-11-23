from pathlib import Path


SOURCE = (Path(__file__).parents[1] / 'legal_bot' / 'handlers.py').read_text(encoding='utf-8')
START = SOURCE.index('def case_menu(cid):')
END = SOURCE.index('\n\ndef _hash_phone', START)
MENU_SOURCE = SOURCE[START:END]


def test_case_menu_keeps_existing_callback_contracts_and_groups_workflow():
    expected = [
        "cworkspace:{cid}", "ctimeline:{cid}", "cfile:add:{cid}",
        "cfile:version:{cid}", "canalysis:{cid}", "csummary:{cid}",
        "cdrafting:{cid}", "cai:{cid}", "casetext:{cid}", "caseq:{cid}",
        "ctasks:{cid}", "cstatus:{cid}", "cnext:{cid}", "claws:{cid}",
        "cnote:{cid}", "carchive:{cid}", "casedelete:{cid}",
    ]
    for callback in expected:
        assert callback in MENU_SOURCE
    assert "callback_data='cases'" in MENU_SOURCE
    assert "callback_data='home'" in MENU_SOURCE
    assert MENU_SOURCE.count('InlineKeyboardButton(') == 19
    assert "'✍️ نگارش لایحه'" in MENU_SOURCE
    assert "'📎 افزودن سند / متن'" in MENU_SOURCE


def test_case_menu_keeps_delete_isolated_and_near_bottom():
    delete_position = MENU_SOURCE.index("callback_data=f'casedelete:{cid}'")
    archive_position = MENU_SOURCE.index("callback_data=f'carchive:{cid}'")
    navigation_position = MENU_SOURCE.index("callback_data='cases'")
    assert archive_position < delete_position < navigation_position
    assert "Destructive" in MENU_SOURCE
