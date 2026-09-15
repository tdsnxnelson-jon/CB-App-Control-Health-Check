import os

from healthcheck.analysis import block_analysis
from healthcheck.report import pptx_helpers as ph
import main


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


def test_pie_chart_uses_bar_when_tiny_slice_would_render_invisibly():
    assert ph._should_use_pie_chart(["A", "B", "C"], [90, 9, 0.1]) is False
    assert ph._should_use_pie_chart(["A", "B", "C"], [50, 30, 20]) is True
    assert ph._should_use_pie_chart(["A", "B", "C"], [49, 49, 2]) is True


def test_resolve_output_path_for_directory_target():
    directory = os.path.join("C:\\", "tmp", "reports") + os.sep
    path = main._resolve_output_path(directory, "Epic Hosting", "carbonblack11.ss.us.epichosted.com")

    expected = os.path.join(os.path.normpath(directory), "Epic Hosting_carbonblack11.ss.us.epichosted.com_AppControl_HealthCheck.pptx")
    assert path == expected
