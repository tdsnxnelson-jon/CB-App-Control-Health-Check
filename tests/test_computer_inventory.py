from datetime import date

import pandas as pd

from healthcheck.analysis import AnalysisResult, computer_inventory
from healthcheck.report import pptx_helpers as ph


def _lifecycle_dates():
    windows = {
        (8, 8): (date(2022, 10, 20), date(2024, 4, 20), date(2026, 4, 20)),
        (8, 10): (date(2025, 2, 26), date(2027, 2, 26), None),
        (8, 11): (date(2026, 3, 5), date(2027, 9, 1), None),
    }
    return {
        "windows_desktop": windows,
        "windows_server": windows,
        "linux": {(8, 9): (date(2026, 5, 11), None, None)},
    }


def test_inactive_agents_guidance_precedes_inventory_findings():
    presentation = ph.create_deck()
    result = AnalysisResult(title="Computer Inventory Health")

    computer_inventory.build_slides(presentation, result)

    slides = [
        " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
        for slide in presentation.slides
    ]
    guidance_index = next(i for i, text in enumerate(slides) if "Key Characteristics of Inactive Agents" in text)
    findings_index = next(i for i, text in enumerate(slides) if "Computer Inventory - Findings" in text)
    guidance = slides[guidance_index]

    assert findings_index == guidance_index + 1
    assert "30 days" in guidance
    assert "41002" in guidance
    assert "b9cli --status" in guidance
    assert "Delete the console computer record" in guidance
    assert "Disabled mode is not Inactive" in guidance


def test_agent_version_table_groups_by_os_and_applies_lifecycle_dates():
    inventory = pd.DataFrame({
        "Operating System": ["Windows Server", "Windows 10", "Windows 11", "Linux", None],
        "Agent Version": ["8.10.4.2", "8.8.2.1042", "8.11.0", "8.9.0", "9.1.0"],
    })

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12), _lifecycle_dates())

    assert rows[0] == ["Operating System", "Agent Version", "Lifecycle", "Count", "Percentage"]
    assert [row[2] for row in rows[1:-1]] == ["Unknown", "GA", "GA", "GA", "EOL"]
    assert rows[-1] == ["Grand Total", "", "", 5, "100.0%"]


def test_agent_version_810_reaches_eos_on_february_26_2027():
    lifecycle_dates = _lifecycle_dates()
    assert computer_inventory._agent_lifecycle_status("Windows Server 2022", "8.10.4.2", date(2027, 2, 25), lifecycle_dates) == "GA"
    assert computer_inventory._agent_lifecycle_status("Windows 11", "8.10.0", date(2027, 2, 26), lifecycle_dates) == "EOS"


def test_agent_version_table_keeps_legacy_exports_without_os():
    inventory = pd.DataFrame({"Agent Version": ["8.10.4.2", "8.10.4.2"]})

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12), _lifecycle_dates())

    assert rows[1] == ["Unknown", "8.10.4.2", "Unknown", 2, "100.0%"]


def test_agent_version_table_keeps_windows_desktop_and_server_separate():
    inventory = pd.DataFrame({
        "Operating System": ["Windows 11", "Windows Server 2022"],
        "Agent Version": ["8.11.0", "8.11.0"],
    })

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12), _lifecycle_dates())

    assert computer_inventory._lifecycle_platform("Windows 11") == "windows_desktop"
    assert computer_inventory._lifecycle_platform("Windows Server 2022") == "windows_server"
    assert computer_inventory._lifecycle_platform("Windows") == ""
    assert rows[1:3] == [
        ["Windows 11", "8.11.0", "GA", 1, "50.0%"],
        ["Windows Server 2022", "8.11.0", "GA", 1, "50.0%"],
    ]


def test_agent_version_table_sorts_versions_newest_first_numerically():
    inventory = pd.DataFrame({
        "Operating System": ["Windows 11"] * 5,
        "Agent Version": ["8.9.0", "8.10.4.2", "8.11.0", "8.10.10.0", ""],
    })

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12), _lifecycle_dates())

    assert [row[1] for row in rows[1:-1]] == ["8.11.0", "8.10.10.0", "8.10.4.2", "8.9.0", "(blank)"]


def test_agent_lifecycle_parser_handles_current_and_legacy_broadcom_tables():
    html = """
    <table>
      <tr><th>Agent Version</th><th>General Availability (GA)</th><th>End of Service (EOS)</th><th>End of Life (EOL)</th></tr>
      <tr><td>8.12.x</td><td>22 June 2026</td><td>Sept 2027</td><td></td></tr>
    </table>
    <table>
      <tr><th>Agent Version</th><th>Enter Standard</th><th>Enter Extended</th><th>Enter End of Support</th></tr>
      <tr><td>8.10.x</td><td>26 February 2025</td><td>26 February 2026</td><td>26 February 2027</td></tr>
    </table>
    """

    assert computer_inventory._parse_agent_lifecycle_dates(html) == {
        (8, 12): (date(2026, 6, 22), date(2027, 9, 1), None),
        (8, 10): (date(2025, 2, 26), date(2026, 2, 26), date(2027, 2, 26)),
    }


def test_agent_lifecycle_refresh_fetches_each_official_page_every_time(monkeypatch):
    html = """
    <table>
      <tr><th>Agent Version</th><th>General Availability (GA)</th><th>End of Service (EOS)</th><th>End of Life (EOL)</th></tr>
      <tr><td>8.12.x</td><td>22 June 2026</td><td></td><td></td></tr>
    </table>
    """
    requested_urls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return html.encode("utf-8")

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        assert timeout == 15
        return Response()

    monkeypatch.setattr(computer_inventory, "urlopen", fake_urlopen)

    computer_inventory._fetch_agent_lifecycle_dates()
    computer_inventory._fetch_agent_lifecycle_dates()

    assert requested_urls == list(computer_inventory._AGENT_OER_URLS.values()) * 2


def test_computer_inventory_analysis_refreshes_lifecycle_each_time(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(True)
        return _lifecycle_dates()

    monkeypatch.setattr(computer_inventory, "_fetch_agent_lifecycle_dates", fake_fetch)
    inventory = pd.DataFrame({
        "Operating System": ["Windows 11"],
        "Agent Version": ["8.11.0"],
    })

    first = computer_inventory.analyze(inventory)
    second = computer_inventory.analyze(inventory)

    assert len(calls) == 2
    assert first.tables["agent_version"][1][2] == "GA"
    assert second.tables["agent_version"][1][2] == "GA"


def test_agent_lifecycle_refresh_warns_and_skips_unavailable_platform(monkeypatch, caplog):
    html = """
    <table>
      <tr><th>Agent Version</th><th>General Availability (GA)</th><th>End of Service (EOS)</th><th>End of Life (EOL)</th></tr>
      <tr><td>8.12.x</td><td>22 June 2026</td><td></td><td></td></tr>
    </table>
    """

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return html.encode("utf-8")

    def fake_urlopen(request, timeout):
        if "macos" in request.full_url:
            raise OSError("offline")
        return Response()

    monkeypatch.setattr(computer_inventory, "urlopen", fake_urlopen)

    lifecycle_dates = computer_inventory._fetch_agent_lifecycle_dates()

    assert "macos" not in lifecycle_dates
    assert "windows_desktop" in lifecycle_dates
    assert "windows_server" in lifecycle_dates
    assert "Could not refresh macos agent lifecycle dates" in caplog.text


def test_all_agent_versions_are_paginated_after_policy_agent_health():
    versions = [f"8.11.{index}.0" for index in range(40)]
    agent_rows = [["Operating System", "Agent Version", "Lifecycle", "Count", "Percentage"]]
    agent_rows.extend([["Windows Server 2022", version, "GA", 1, "2.5%"] for version in versions])
    agent_rows.append(["Grand Total", "", "", 40, "100.0%"])
    result = AnalysisResult(title="Computer Inventory Health", tables={"agent_version": agent_rows})
    presentation = ph.create_deck()

    computer_inventory.build_slides(presentation, result)

    slide_texts = [
        " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
        for slide in presentation.slides
    ]
    policy_index = next(i for i, text in enumerate(slide_texts) if "Policy and Agent Health" in text)
    assert "Agent Version Inventory" in slide_texts[policy_index + 1]

    inventory_slides = []
    for slide in list(presentation.slides)[policy_index + 1:]:
        title = " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
        if "Agent Version Inventory" not in title:
            break
        inventory_slides.append(slide)

    rendered_table_text = " ".join(
        cell.text
        for slide in inventory_slides
        for shape in slide.shapes
        if shape.has_table
        for row in shape.table.rows
        for cell in row.cells
    )
    assert len(inventory_slides) > 1
    assert all(version in rendered_table_text for version in versions)
    assert "more row(s) not shown" not in rendered_table_text