"""Tests for the three tools: core logic, the MCP layer (in-memory FastMCP client), and the failure cases.

Run:  python -m pytest -v
"""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core      # noqa: E402
import server    # noqa: E402
from fastmcp import Client                 # noqa: E402
from fastmcp.exceptions import ToolError   # noqa: E402


@pytest.fixture(autouse=True)
def temp_bookings(tmp_path, monkeypatch):
    """Write bookings to a temporary file so tests never touch data/bookings.json."""
    monkeypatch.setattr(core, "BOOKINGS_FILE", tmp_path / "bookings.json")
    return tmp_path / "bookings.json"


def call(tool, args):
    async def _run():
        async with Client(server.mcp) as c:
            return await c.call_tool(tool, args)
    return asyncio.run(_run())


# ---------------------------------------------------------------- DATA tool
def test_size_system_family():
    r = core.size_system(["fridge", "lights", "TV", "washing machine"])
    assert r["recommended_package"] == "Family" and r["daily_kwh"] == 3.2


def test_size_system_ac_needs_comfort():
    assert core.size_system(["an AC", "fridge"])["recommended_package"] == "Comfort"


def test_size_system_is_read_only(temp_bookings):
    core.size_system(["fridge"])
    assert not temp_bookings.exists()


def test_size_system_failure_unknown_appliances():
    with pytest.raises(core.ToolInputError, match="None of these appliances are recognised"):
        core.size_system(["spaceship", "time machine"])


def test_size_system_failure_empty():
    with pytest.raises(core.ToolInputError):
        core.size_system([])


# ---------------------------------------------------------------- ACTION tool
def test_book_site_visit_writes_booking(temp_bookings):
    b = core.book_site_visit("Abbas Yassine", "abbasyassine@example.com", "Jounieh", "Comfort")
    saved = json.loads(temp_bookings.read_text())
    assert b["booking_id"].startswith("SV-") and saved[0]["booking_id"] == b["booking_id"]
    assert saved[0]["region"] == "Keserwan"


def test_book_site_visit_failure_unserved_town(temp_bookings):
    with pytest.raises(core.ToolInputError, match="does not serve 'Zahle'"):
        core.book_site_visit("Abbas", "abbasyassine@example.com", "Zahle", "Starter")
    assert not temp_bookings.exists()   # nothing written on failure


def test_book_site_visit_failure_bad_email():
    with pytest.raises(core.ToolInputError, match="not a valid email"):
        core.book_site_visit("Abbas", "not-an-email", "Beirut", "Starter")


# ---------------------------------------------------------------- ORCHESTRATION tool
def test_plan_solar_install_runs_both_steps(temp_bookings):
    r = core.plan_solar_install(["inverter ac", "fridge", "lights"], "Abbas", "abbasyassine@example.com", "Hamra")
    assert r["sizing"]["recommended_package"] == "Comfort"
    assert r["booking"]["package"] == "Comfort"            # booked what sizing recommended
    assert len(json.loads(temp_bookings.read_text())) == 1


def test_plan_solar_install_failure_says_which_step(temp_bookings):
    with pytest.raises(core.ToolInputError, match="Sizing succeeded .* but the booking failed"):
        core.plan_solar_install(["fridge"], "Abbas", "abbasyassine@example.com", "Tripoli")
    assert not temp_bookings.exists()


# ---------------------------------------------------------------- MCP layer (what the agent actually sees)
def test_server_exposes_exactly_three_tools_and_a_resource():
    async def _run():
        async with Client(server.mcp) as c:
            return await c.list_tools(), await c.list_resources()
    tools, resources = asyncio.run(_run())
    assert sorted(t.name for t in tools) == ["book_site_visit", "plan_solar_install", "size_system"]
    assert all(t.description and (getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)) for t in tools)
    assert all(getattr(t, "output_schema", None) or getattr(t, "outputSchema", None) for t in tools)             # typed outputs
    assert [str(r.uri) for r in resources] == ["suncedar://packages"]


def test_mcp_call_returns_structured_output():
    r = call("size_system", {"appliances": ["fridge", "lights", "tv"]})
    assert r.structured_content["recommended_package"] == "Starter"


def test_mcp_failure_is_a_clear_tool_error():
    with pytest.raises(ToolError, match="does not serve"):
        call("book_site_visit", {"name": "Abbas", "email": "abbasyassine@example.com", "town": "Zahle",
                                 "package": "Starter"})


def test_mcp_rejects_invalid_package_value():
    with pytest.raises(ToolError):
        call("book_site_visit", {"name": "Abbas", "email": "abbasyassine@example.com", "town": "Beirut",
                                 "package": "Platinum"})
