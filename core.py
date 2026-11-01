"""Business logic for the SunCedar MCP toolkit.

Plain Python functions with no MCP code, so they can be unit-tested directly.
server.py wraps them as MCP tools.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

BOOKINGS_FILE = Path(__file__).resolve().parent / "data" / "bookings.json"

PACKAGES = {
    "Starter": {"price_usd": 2900, "panels_kw": 3, "battery_kwh": 5,
                "covers": "lights, fridge, router, TV"},
    "Family": {"price_usd": 4800, "panels_kw": 5, "battery_kwh": 10,
               "covers": "Starter loads plus a washing machine and a water pump"},
    "Comfort": {"price_usd": 7400, "panels_kw": 8, "battery_kwh": 15,
                "covers": "Family loads plus one inverter AC and an electric water heater"},
}

# appliance -> (peak watts, kWh per day): typical Lebanese home usage, planning estimates
APPLIANCES = {
    "lights": (120, 0.72), "fridge": (150, 1.50), "tv": (100, 0.50), "router": (15, 0.36),
    "laptop": (60, 0.36), "fan": (60, 0.48), "washing machine": (500, 0.50), "water pump": (750, 0.38),
    "microwave": (1000, 0.30), "inverter ac": (1000, 6.00), "electric water heater": (1500, 3.00),
}
ALIASES = {
    "light": "lights", "lamps": "lights", "refrigerator": "fridge", "television": "tv", "wifi": "router",
    "computer": "laptop", "washer": "washing machine", "pump": "water pump", "ac": "inverter ac",
    "air conditioner": "inverter ac", "aircon": "inverter ac", "water heater": "electric water heater",
    "heater": "electric water heater", "boiler": "electric water heater",
}
SERVED_TOWNS = {
    "beirut": "Greater Beirut", "hamra": "Greater Beirut", "achrafieh": "Greater Beirut",
    "jounieh": "Keserwan", "kaslik": "Keserwan", "baabda": "Baabda", "hazmieh": "Baabda",
    "broummana": "Metn", "antelias": "Metn", "aley": "Aley", "chouf": "Chouf",
    "jbeil": "Jbeil/Byblos", "byblos": "Jbeil/Byblos", "batroun": "Batroun",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class ToolInputError(ValueError):
    """A predictable, user-fixable problem with the tool input."""


def _normalise(name: str) -> str | None:
    n = re.sub(r"^(a|an|the|my|\d+)\s+", "", name.strip().lower())
    if n in APPLIANCES:
        return n
    if n in ALIASES:
        return ALIASES[n]
    if n.endswith("s") and n[:-1] in ALIASES:
        return ALIASES[n[:-1]]
    return next((k for k in APPLIANCES if k in n), None)


# ---------------------------------------------------------------- DATA
def size_system(appliances: list[str]) -> dict:
    """Read-only: estimate daily energy use and recommend a home package."""
    if not appliances:
        raise ToolInputError("No appliances given. Example: ['fridge', 'lights', 'tv'].")
    known, unknown = {}, []
    for a in appliances:
        key = _normalise(a)
        (known.__setitem__(key, APPLIANCES[key]) if key else unknown.append(a))
    if not known:
        raise ToolInputError(f"None of these appliances are recognised: {unknown}. "
                             f"Known appliances: {sorted(APPLIANCES)}.")
    kwh = round(sum(v[1] for v in known.values()), 1)
    if "inverter ac" in known or "electric water heater" in known or kwh > 10:
        package = "Comfort"
    elif "washing machine" in known or "water pump" in known or kwh > 5:
        package = "Family"
    else:
        package = "Starter"
    if kwh > 15:
        raise ToolInputError(f"Estimated {kwh} kWh/day is above the largest home package (15 kWh battery). "
                             "This needs a Business Solar site survey.")
    return {"appliances": sorted(known), "unrecognised": unknown, "daily_kwh": kwh,
            "peak_watts": sum(v[0] for v in known.values()), "recommended_package": package,
            "price_usd": PACKAGES[package]["price_usd"]}


# ---------------------------------------------------------------- ACTION
def book_site_visit(name: str, email: str, town: str, package: str) -> dict:
    """Side effect: append a site-visit booking to data/bookings.json."""
    name, email, town = (name or "").strip(), (email or "").strip(), (town or "").strip()
    if not name:
        raise ToolInputError("Name is required.")
    if not EMAIL_RE.match(email):
        raise ToolInputError(f"'{email}' is not a valid email address.")
    if package not in PACKAGES:
        raise ToolInputError(f"Unknown package '{package}'. Choose one of {list(PACKAGES)}.")
    region = SERVED_TOWNS.get(town.lower())
    if region is None:
        raise ToolInputError(f"SunCedar does not serve '{town}' yet. Served areas: Greater Beirut, Metn, "
                             "Keserwan, Baabda, Aley, Chouf, Jbeil/Byblos and Batroun.")
    booking = {"booking_id": f"SV-{uuid.uuid4().hex[:6].upper()}", "name": name, "email": email,
               "town": town.title(), "region": region, "package": package,
               "created_at": datetime.now().isoformat(timespec="seconds"), "status": "pending_confirmation"}
    BOOKINGS_FILE.parent.mkdir(exist_ok=True)
    bookings = json.loads(BOOKINGS_FILE.read_text()) if BOOKINGS_FILE.exists() else []
    bookings.append(booking)
    BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))
    return booking


# ---------------------------------------------------------------- ORCHESTRATION
def plan_solar_install(appliances: list[str], name: str, email: str, town: str) -> dict:
    """Size the system, then book a site visit for the recommended package."""
    sizing = size_system(appliances)                      # step 1: data
    try:
        booking = book_site_visit(name, email, town, sizing["recommended_package"])   # step 2: action
    except ToolInputError as e:
        raise ToolInputError(f"Sizing succeeded ({sizing['recommended_package']}, {sizing['daily_kwh']} kWh/day) "
                             f"but the booking failed: {e}") from e
    return {"sizing": sizing, "booking": booking,
            "summary": f"{sizing['recommended_package']} package (from ${sizing['price_usd']:,}) for "
                       f"~{sizing['daily_kwh']} kWh/day; site visit {booking['booking_id']} requested in "
                       f"{booking['town']}."}
