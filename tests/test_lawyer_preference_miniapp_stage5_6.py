from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_miniapp_has_memory_lifecycle_management_panel():
    app = (ROOT / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    assert 'lawyerMemoryManager' in app
    assert 'lawyerMemoryHistory' in app
    assert 'lawyerMemoryToggle' in app
    assert 'memoryCompareFrom' in app and 'memoryCompareTo' in app
    assert 'lawyerMemoryDelete' in app


def test_miniapp_calls_existing_authenticated_lifecycle_routes():
    app = (ROOT / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    assert "'/api/v1/lawyer-preferences/history?limit=50'" in app
    assert '/api/v1/lawyer-preferences/compare?from_version=' in app
    assert "'/api/v1/lawyer-preferences/restore'" in app
    assert '`/api/v1/lawyer-preferences/${action}`' in app
    assert "'/api/v1/lawyer-preferences/profile'" in app


def test_persistent_actions_use_explicit_confirmation_and_expected_version():
    app = (ROOT / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    assert 'expected_profile_version:lawyerPreferenceVersion,confirm_action:true' in app
    assert 'source_profile_version:sourceVersion,expected_profile_version:lawyerPreferenceVersion,confirm_action:true' in app
    assert "method:'DELETE',body:JSON.stringify({expected_profile_version:lawyerPreferenceVersion,confirm_action:true})" in app
    assert app.count('window.confirm(') >= 4


def test_memory_manager_has_responsive_visual_styles():
    css = (ROOT / 'miniapp' / 'styles.css').read_text(encoding='utf-8')
    assert '.lawyer-memory-manager' in css
    assert '.memory-diff-row.added' in css
    assert '.memory-diff-row.removed' in css
    assert '.memory-diff-row.changed' in css
    assert '@media(max-width:420px)' in css
