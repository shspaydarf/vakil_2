import sqlite3
import pytest

from legal_bot import config
from legal_bot import lawyer_preference_store as store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-security-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO users(user_id) VALUES(?)", [(101,), (202,)])
    store.init_lawyer_preference_tables()
    return db_path


def test_common_identifiers_in_free_text_are_rejected(isolated_db):
    bad_values = [
        "شماره تماس 09123456789",
        "کد ملی ۱۲۳۴۵۶۷۸۹۰",
        "برای تماس lawyer@example.com",
        "شماره پرونده: 12345678",
    ]
    for value in bad_values:
        with pytest.raises(store.PreferencePrivacyError):
            store.save_profile(101, {"professional_context": {"practice_context_note": value}},
                               expected_profile_version=0, confirm_save=True)
    assert store.get_profile(101) is None


def test_preference_text_without_identifiers_is_allowed(isolated_db):
    saved = store.save_profile(101, {"professional_context": {"practice_context_note": "تمرکز بر دعاوی قراردادی و حقوق تجارت"}},
                               expected_profile_version=0, confirm_save=True)
    assert saved["profile_version"] == 1


def test_history_snapshots_cannot_be_updated_directly(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    with sqlite3.connect(isolated_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE lawyer_preference_versions SET change_type='restored' WHERE user_id=101")


def test_profile_owner_cannot_be_reassigned(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    with sqlite3.connect(isolated_db) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE lawyer_preference_profiles SET user_id=202 WHERE user_id=101")
    assert store.get_profile(101) is not None
    assert store.get_profile(202) is None


def test_corrupt_or_missing_history_blocks_overwrite(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("DELETE FROM lawyer_preference_versions WHERE user_id=101")
    with pytest.raises(store.ProfileIntegrityError):
        store.save_profile(101, {"writing_style": {"tone": "neutral"}}, expected_profile_version=1, confirm_save=True)
    assert store.get_profile(101)["preferences"]["writing_style"]["tone"] == "formal"


def test_owner_reads_are_isolated_for_profile_and_history(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    store.save_profile(202, {"writing_style": {"tone": "plain_language"}}, expected_profile_version=0, confirm_save=True)
    assert store.get_profile(101)["preferences"]["writing_style"]["tone"] == "formal"
    assert store.get_profile(202)["preferences"]["writing_style"]["tone"] == "plain_language"
    assert [x["preferences"]["writing_style"]["tone"] for x in store.list_profile_versions(101)] == ["formal"]
    assert [x["preferences"]["writing_style"]["tone"] for x in store.list_profile_versions(202)] == ["plain_language"]


def test_user_delete_cascades_profile_and_history(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("DELETE FROM users WHERE user_id=101")
    assert store.get_profile(101) is None
    assert store.list_profile_versions(101) == []


def test_telegram_auth_helper_rejects_tampered_identity(monkeypatch):
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode
    from legal_bot import api

    token = "test-bot-token"
    monkeypatch.setattr(api, "BOT_TOKEN", token)
    pairs = {
        "auth_date": str(int(time.time())),
        "query_id": "AA-test-query",
        "user": json.dumps({"id": 101, "first_name": "Test"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    init_data = urlencode(pairs)
    assert api.telegram_user_id_from_init_data(init_data, token) == 101

    tampered = init_data.replace('%3A101', '%3A202')
    with pytest.raises(ValueError):
        api.telegram_user_id_from_init_data(tampered, token)
