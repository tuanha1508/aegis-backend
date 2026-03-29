"""Load or fetch shelter / supply-point candidates for the Tampa Bay area."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import DEMO_MODE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Tampa Bay metro approximate bounding box (south, west, north, east) for Overpass
TAMPA_BBOX_SOUTH = 27.85
TAMPA_BBOX_WEST = -82.65
TAMPA_BBOX_NORTH = 28.15
TAMPA_BBOX_EAST = -82.25

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_S = 55.0

ALLOWED_RESOURCE_TYPES = frozenset(
    {"shelter", "medical", "supply_point", "charging", "road"}
)


@dataclass
class ResourceCandidate:
    """Pre-upsert discovery row aligned with resources table (minus DB id / last_updated)."""

    type: str
    name: str
    lat: float
    lng: float
    address: str | None = None
    capacity: int | None = None
    amenities: str | None = None
    osm_type: str | None = None  # node | way | relation
    osm_id: int | None = None
    raw_tags: dict[str, str] = field(default_factory=dict)

    def osm_ref_token(self) -> str | None:
        if self.osm_type and self.osm_id is not None:
            return f"| osm:{self.osm_type}/{self.osm_id}"
        return None


def _compose_address(tags: dict[str, str]) -> str | None:
    hn = tags.get("addr:housenumber", "")
    st = tags.get("addr:street", "")
    if hn and st:
        line1 = f"{hn} {st}"
    elif st:
        line1 = st
    elif hn:
        line1 = hn
    else:
        line1 = ""
    city = tags.get("addr:city", "")
    state = tags.get("addr:state", "")
    postal = tags.get("addr:postcode", "")
    tail = ", ".join(p for p in [city, state, postal] if p)
    parts = [line1] if line1 else []
    if tail:
        parts.append(tail)
    return ", ".join(parts) if parts else None


def _tags_to_amenities(tags: dict[str, str]) -> str | None:
    keys = (
        "wheelchair",
        "drinking_water",
        "shower",
        "internet_access",
        "opening_hours",
        "phone",
        "operator",
        "description",
    )
    bits: list[str] = []
    for k in keys:
        if v := tags.get(k):
            bits.append(f"{k.replace(':', '_')}={v}")
    if tags.get("amenity") == "food_bank":
        bits.append("food_bank")
    if tags.get("social_facility"):
        bits.append(f"social_facility={tags['social_facility']}")
    return ",".join(bits) if bits else None


def infer_type_from_tags(tags: dict[str, str]) -> str:
    if tags.get("amenity") == "shelter" or tags.get("social_facility") == "shelter":
        return "shelter"
    if tags.get("amenity") == "food_bank" or tags.get("social_facility") == "food_bank":
        return "supply_point"
    if tags.get("amenity") == "social_facility" and tags.get("social_facility") not in (
        None,
        "",
        "shelter",
    ):
        # Generic social services / outreach — treat as supply / support point
        return "supply_point"
    if tags.get("emergency") == "disaster_response":
        return "supply_point"
    return "supply_point"


def element_to_candidate(el: dict[str, Any]) -> ResourceCandidate | None:
    tags = {k: str(v) for k, v in el.get("tags", {}).items()}
    typ = el.get("type")
    if typ not in ("node", "way", "relation"):
        return None
    lat: float | None
    lng: float | None
    if typ == "node":
        lat = el.get("lat")
        lng = el.get("lon")
    else:
        c = el.get("center") or {}
        lat = c.get("lat")
        lng = c.get("lon")
    if lat is None or lng is None:
        return None
    name = tags.get("name") or tags.get("official_name")
    kind = infer_type_from_tags(tags)
    if not name:
        name = "Unnamed supply point" if kind == "supply_point" else "Unnamed shelter"
    try:
        oid = int(el["id"])
    except (KeyError, TypeError, ValueError):
        return None
    caps: int | None = None
    if beds := tags.get("capacity:beds"):
        try:
            caps = int(re.sub(r"[^\d]", "", beds) or 0) or None
        except ValueError:
            caps = None
    return ResourceCandidate(
        type=kind,
        name=name,
        lat=float(lat),
        lng=float(lng),
        address=_compose_address(tags),
        capacity=caps,
        amenities=_tags_to_amenities(tags),
        osm_type=typ,
        osm_id=oid,
        raw_tags=tags,
    )


def _json_row_to_candidate(row: dict[str, Any]) -> ResourceCandidate:
    return ResourceCandidate(
        type=row["type"],
        name=row["name"],
        lat=float(row["lat"]),
        lng=float(row["lng"]),
        address=row.get("address"),
        capacity=row.get("capacity"),
        amenities=row.get("amenities"),
        osm_type=None,
        osm_id=None,
        raw_tags={},
    )


def load_demo_candidates() -> list[ResourceCandidate]:
    out: list[ResourceCandidate] = []
    for fname in ("tampa_shelters.json", "tampa_supply_points.json"):
        path = DATA_DIR / fname
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for row in data:
            c = _json_row_to_candidate(row)
            if c.type not in ALLOWED_RESOURCE_TYPES:
                continue
            out.append(c)
    return out


def _overpass_query() -> str:
    s, w, n, e = TAMPA_BBOX_SOUTH, TAMPA_BBOX_WEST, TAMPA_BBOX_NORTH, TAMPA_BBOX_EAST
    return f"""
[out:json][timeout:60];
(
  node["amenity"="shelter"]({s},{w},{n},{e});
  way["amenity"="shelter"]({s},{w},{n},{e});
  node["social_facility"="shelter"]({s},{w},{n},{e});
  way["social_facility"="shelter"]({s},{w},{n},{e});
  node["amenity"="food_bank"]({s},{w},{n},{e});
  way["amenity"="food_bank"]({s},{w},{n},{e});
  node["social_facility"="food_bank"]({s},{w},{n},{e});
  way["social_facility"="food_bank"]({s},{w},{n},{e});
  node["emergency"="disaster_response"]({s},{w},{n},{e});
  way["emergency"="disaster_response"]({s},{w},{n},{e});
);
out center;
""".strip()


def fetch_overpass_candidates() -> list[ResourceCandidate]:
    body = {"data": _overpass_query()}
    with httpx.Client(timeout=OVERPASS_TIMEOUT_S) as client:
        r = client.post(OVERPASS_URL, data=body)
        r.raise_for_status()
        payload = r.json()
    elements = payload.get("elements") or []
    seen: set[tuple[str, int]] = set()
    out: list[ResourceCandidate] = []
    for el in elements:
        c = element_to_candidate(el)
        if not c or c.osm_type is None or c.osm_id is None:
            continue
        key = (c.osm_type, c.osm_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def discover_candidates() -> tuple[list[ResourceCandidate], str]:
    """Returns (candidates, source_label)."""
    if DEMO_MODE:
        return load_demo_candidates(), "demo_json"
    return fetch_overpass_candidates(), "overpass"
