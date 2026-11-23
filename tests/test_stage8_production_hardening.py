
import os
import importlib


def test_production_startup_rejects_wildcard_origin(monkeypatch):
    monkeypatch.setenv("API_ENV", "production")
    monkeypatch.setenv("BOT_TOKEN", "123:token")
    monkeypatch.setenv("MINIAPP_URL", "https://mini.example")
    monkeypatch.setenv("API_ALLOWED_ORIGIN", "*")
    monkeypatch.setenv("API_DEV_MODE", "0")
    import legal_bot.api as api
    api.API_ENV = "production"
    api.BOT_TOKEN = "123:token"
    api.MINIAPP_URL = "https://mini.example"
    api.API_ALLOWED_ORIGIN = "*"
    api.API_DEV_MODE = False
    try:
        api.create_server("127.0.0.1", 0)
    except RuntimeError as exc:
        assert "API_ALLOWED_ORIGIN" in str(exc)
    else:
        raise AssertionError("production wildcard origin was accepted")


def test_production_startup_rejects_dev_mode(monkeypatch):
    monkeypatch.setenv("API_ENV", "production")
    monkeypatch.setenv("BOT_TOKEN", "123:token")
    monkeypatch.setenv("MINIAPP_URL", "https://mini.example")
    monkeypatch.setenv("API_ALLOWED_ORIGIN", "https://mini.example")
    monkeypatch.setenv("API_DEV_MODE", "1")
    import legal_bot.api as api
    api.API_ENV = "production"
    api.BOT_TOKEN = "123:token"
    api.MINIAPP_URL = "https://mini.example"
    api.API_ALLOWED_ORIGIN = "https://mini.example"
    api.API_DEV_MODE = True
    try:
        api.create_server("127.0.0.1", 0)
    except RuntimeError as exc:
        assert "API_DEV_MODE" in str(exc)
    else:
        raise AssertionError("API_DEV_MODE was accepted in production")


def test_rate_limiter_enforces_window(monkeypatch):
    monkeypatch.setenv("API_RATE_LIMIT_REQUESTS", "2")
    import legal_bot.api as api
    api.API_RATE_LIMIT_REQUESTS = 2
    api._RATE_LIMIT_BUCKETS.clear()

    class Addr:
        client_address = ("127.0.0.1", 1234)
        class H:
            def get(self, key, default=""):
                return ""
        headers = H()

    h = Addr()
    api._check_rate_limit(h)
    api._check_rate_limit(h)
    try:
        api._check_rate_limit(h)
    except RuntimeError as exc:
        assert str(exc).startswith("RATE_LIMIT:")
    else:
        raise AssertionError("rate limit did not trigger")


def test_miniapp_preserves_case_management_and_ai_contract():
    from pathlib import Path
    js = Path('miniapp/app.js').read_text(encoding='utf-8')
    assert 'openEditModal' in js
    assert 'changeCaseState' in js
    assert 'deleteCase' in js
    assert 'caseSearch' in js
    assert "api(`/api/v1/cases/${currentCaseId}/ai" in js
    assert '.data};$' not in js


def test_production_compose_serves_miniapp():
    from pathlib import Path
    compose = Path('docker-compose.production.yml').read_text(encoding='utf-8')
    nginx = Path('nginx.conf').read_text(encoding='utf-8')
    assert 'image: nginx:1.27-alpine' in compose
    assert './miniapp:/usr/share/nginx/html:ro' in compose
    assert 'proxy_pass http://api:8080;' in nginx


def test_upload_aggregate_limit_is_bounded_and_matches_proxy_headroom():
    from legal_bot.config import MAX_UPLOAD_REQUEST_MB
    from pathlib import Path

    nginx = Path("nginx.conf").read_text(encoding="utf-8")
    assert 1 <= MAX_UPLOAD_REQUEST_MB <= 64
    assert f"client_max_body_size {MAX_UPLOAD_REQUEST_MB + 1}m;" in nginx
