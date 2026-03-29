"""Shared geo + name matching helpers for resources and intel."""

from __future__ import annotations

import math
import re


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def normalize_name(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def names_match(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if len(na) < 2 or len(nb) < 2:
        return False
    if na in nb or nb in na:
        return True
    wa, wb = set(na.split()), set(nb.split())
    if not wa or not wb:
        return False
    inter = len(wa & wb)
    return inter >= min(2, min(len(wa), len(wb)))
