from healthcheck.analysis import block_analysis
from healthcheck.report import pptx_helpers as ph


def test_sanitize_chart_values_replaces_non_finite():
    values = [1.0, float("nan"), float("inf"), None, 3.0]

    assert ph._sanitize_chart_values(values) == [1.0, 0.0, 0.0, 0.0, 3.0]


def test_sanitize_chart_categories_replaces_non_finite():
    categories = ["2024-01-01", float("nan"), None, "2024-01-03"]

    assert ph._sanitize_chart_categories(categories) == ["2024-01-01", "", "", "2024-01-03"]


def test_categorize_keeps_logon_script_variants():
    assert block_analysis._categorize("Logon Script") == "Logon Script"
    assert block_analysis._categorize(" logon script ") == "Logon Script"
    assert block_analysis._categorize("Logon Script Data") == "Logon Script"
