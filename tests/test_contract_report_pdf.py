from io import BytesIO

import pytest

from legal_bot.contract_report_pdf import build_contract_report_pdf


def test_build_pdf_returns_valid_pdf_bytes():
    result = build_contract_report_pdf("خلاصه مدیریتی\nمعیار دارای یافته: پرداخت", "قرارداد اجاره")
    assert isinstance(result, BytesIO)
    assert result.read(8).startswith(b"%PDF-")


def test_empty_report_is_rejected():
    with pytest.raises(ValueError):
        build_contract_report_pdf("   ")


def test_pdf_has_document_metadata_and_page_chrome():
    result = build_contract_report_pdf("خلاصه مدیریتی\nمعیارهای بررسی\nپرداخت و تحویل", "قرارداد پیمانکاری")
    data = result.getvalue()
    assert data.startswith(b"%PDF-")
    assert b"MACHINA" in data


def test_long_report_builds_multipage_pdf():
    report = "\n".join(f"معیار شماره {i}: توضیحات و شواهد بررسی قرارداد" for i in range(240))
    result = build_contract_report_pdf(report, "قرارداد اجاره")
    assert result.getvalue().startswith(b"%PDF-")
    assert result.getvalue().count(b"/Type /Page") >= 2
