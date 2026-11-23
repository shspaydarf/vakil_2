from unittest.mock import patch

from legal_bot.ingestion.network_diagnostics import diagnose_host


def test_rejects_non_https_and_credentials_without_dns():
    with patch("legal_bot.ingestion.network_diagnostics.socket.getaddrinfo") as dns:
        assert diagnose_host("http://example.org").status == "rejected_url"
        assert diagnose_host("https://user:pass@example.org").status == "rejected_url"
        dns.assert_not_called()


def test_rejects_nonstandard_port():
    with patch("legal_bot.ingestion.network_diagnostics.socket.getaddrinfo") as dns:
        assert diagnose_host("https://example.org:8443").status == "rejected_port"
        dns.assert_not_called()


def test_reports_system_dns_failure_and_does_not_connect():
    import socket
    with patch("legal_bot.ingestion.network_diagnostics.socket.getaddrinfo", side_effect=socket.gaierror(-3, "temporary failure")), \
         patch("legal_bot.ingestion.network_diagnostics.socket.create_connection") as connect:
        result = diagnose_host("https://example.org")
        assert result.status == "dns_failed"
        connect.assert_not_called()


def test_reports_empty_dns_result():
    with patch("legal_bot.ingestion.network_diagnostics.socket.getaddrinfo", return_value=[]):
        assert diagnose_host("https://example.org").status == "dns_empty"


def test_tls_failure_is_separate_from_dns_failure():
    import socket
    with patch("legal_bot.ingestion.network_diagnostics.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]), \
         patch("legal_bot.ingestion.network_diagnostics.socket.create_connection", side_effect=TimeoutError("timeout")):
        assert diagnose_host("https://example.org").status == "tcp_or_tls_failed"
