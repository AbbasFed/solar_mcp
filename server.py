"""SunCedar MCP server (FastMCP): one Data tool, one Action tool, one Orchestration tool.

Run on its own:   python server.py          (stdio transport, which is what the agent uses)
"""
import sys
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

import core

mcp = FastMCP(
    name="suncedar-solar",
    instructions="Tools for SunCedar Energy, a solar installer in Lebanon: size a home system, book a site visit, "
                 "or do both in one step.",
)


def log(msg: str) -> None:
    # stdout is the MCP channel, so server logs go to stderr (visible in the terminal during the demo)
    print(f"[MCP server] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- typed outputs
class Sizing(BaseModel):
    appliances: list[str] = Field(description="Appliances that were recognised")
    unrecognised: list[str] = Field(description="Inputs that were not recognised (ignored)")
    daily_kwh: float = Field(description="Estimated daily energy use in kWh")
    peak_watts: int = Field(description="Sum of appliance peak power in watts")
    recommended_package: Literal["Starter", "Family", "Comfort"]
    price_usd: int = Field(description="Package price from (USD, installed)")


class Booking(BaseModel):
    booking_id: str
    name: str
    email: str
    town: str
    region: str
    package: Literal["Starter", "Family", "Comfort"]
    created_at: str
    status: str


class InstallPlan(BaseModel):
    sizing: Sizing
    booking: Booking
    summary: str


# ---------------------------------------------------------------- resource (pure data lookup)
@mcp.resource("suncedar://packages", name="packages", description="SunCedar home packages and prices.",
              mime_type="application/json")
def packages() -> dict:
    return core.PACKAGES


# ---------------------------------------------------------------- DATA tool
@mcp.tool
def size_system(appliances: list[str]) -> Sizing:
    """DATA tool (read-only). Estimate a home's daily energy use from a list of appliances and recommend
    one SunCedar package (Starter, Family or Comfort). Changes nothing.
    Example input: ["fridge", "lights", "tv", "washing machine"]."""
    log(f"size_system(appliances={appliances})")
    try:
        return Sizing(**core.size_system(appliances))
    except core.ToolInputError as e:
        log(f"  -> error: {e}")
        raise ToolError(str(e)) from e


# ---------------------------------------------------------------- ACTION tool
@mcp.tool
def book_site_visit(name: str, email: str, town: str,
                    package: Literal["Starter", "Family", "Comfort"]) -> Booking:
    """ACTION tool (side effect). Book a free on-site survey for one package. Saves the booking to
    data/bookings.json and returns its booking_id. Fails clearly if the email is invalid or the town is not served.
    Only call this when the customer has given their name, email and town."""
    log(f"book_site_visit(name={name!r}, email={email!r}, town={town!r}, package={package!r})")
    try:
        result = Booking(**core.book_site_visit(name, email, town, package))
        log(f"  -> saved {result.booking_id}")
        return result
    except core.ToolInputError as e:
        log(f"  -> error: {e}")
        raise ToolError(str(e)) from e


# ---------------------------------------------------------------- ORCHESTRATION tool
@mcp.tool
def plan_solar_install(appliances: list[str], name: str, email: str, town: str) -> InstallPlan:
    """ORCHESTRATION tool. For a customer who lists appliances AND wants a visit: runs size_system, then
    book_site_visit with the recommended package, and returns both results with a one-line summary.
    If booking fails after sizing, the error says which step failed."""
    log(f"plan_solar_install(appliances={appliances}, name={name!r}, email={email!r}, town={town!r})")
    try:
        result = InstallPlan(**core.plan_solar_install(appliances, name, email, town))
        log(f"  -> step 1 size_system: {result.sizing.recommended_package}; "
            f"step 2 book_site_visit: {result.booking.booking_id}")
        return result
    except core.ToolInputError as e:
        log(f"  -> error: {e}")
        raise ToolError(str(e)) from e


if __name__ == "__main__":
    mcp.run(show_banner=False)  # stdio
