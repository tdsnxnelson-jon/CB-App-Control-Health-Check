from datetime import date

import pandas as pd

from healthcheck.analysis import AnalysisResult, computer_inventory
from healthcheck.report import pptx_helpers as ph


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

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12))

    assert rows[0] == ["Operating System", "Agent Version", "Lifecycle", "Count", "Percentage"]
    assert [row[2] for row in rows[1:-1]] == ["Unknown", "GA", "GA", "GA", "EOL"]
    assert rows[-1] == ["Grand Total", "", "", 5, "100.0%"]


def test_agent_version_810_reaches_eos_on_february_26_2027():
    assert computer_inventory._agent_lifecycle_status("Windows Server 2022", "8.10.4.2", date(2027, 2, 25)) == "GA"
    assert computer_inventory._agent_lifecycle_status("Windows 11", "8.10.0", date(2027, 2, 26)) == "EOS"


def test_agent_version_table_keeps_legacy_exports_without_os():
    inventory = pd.DataFrame({"Agent Version": ["8.10.4.2", "8.10.4.2"]})

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12))

    assert rows[1] == ["Unknown", "8.10.4.2", "Unknown", 2, "100.0%"]


def test_agent_version_table_keeps_windows_desktop_and_server_separate():
    inventory = pd.DataFrame({
        "Operating System": ["Windows 11", "Windows Server 2022"],
        "Agent Version": ["8.11.0", "8.11.0"],
    })

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12))

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

    rows = computer_inventory._agent_version_table(inventory, date(2026, 10, 12))

    assert [row[1] for row in rows[1:-1]] == ["8.11.0", "8.10.10.0", "8.10.4.2", "8.9.0", "(blank)"]


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