import math
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.db.database import get_connection
from app.models.resource import ResourceUpdate

router = APIRouter(tags=["resources"])


@router.get("/resources")
async def get_resources(type: Optional[str] = Query(None)):
    conn = get_connection()
    if type:
        rows = conn.execute(
            "SELECT * FROM resources WHERE type = ? ORDER BY name", (type,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/resources/nearest")
async def get_nearest_resource(
    lat: float = Query(...),
    lng: float = Query(...),
    type: Optional[str] = Query(None),
):
    conn = get_connection()
    if type:
        rows = conn.execute(
            "SELECT * FROM resources WHERE type = ? AND status = 'open'", (type,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM resources WHERE status = 'open'"
        ).fetchall()
    conn.close()

    if not rows:
        return {"resource": None, "distance_miles": None}

    def haversine(lat1, lng1, lat2, lng2):
        R = 3959
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlng / 2) ** 2
        )
        return R * 2 * math.asin(math.sqrt(a))

    nearest = min(rows, key=lambda r: haversine(lat, lng, r["lat"], r["lng"]))
    dist = haversine(lat, lng, nearest["lat"], nearest["lng"])
    return {"resource": dict(nearest), "distance_miles": round(dist, 2)}


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: int, update: ResourceUpdate):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM resources WHERE id = ?", (resource_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Resource not found")

    updates = []
    params = []
    if update.status is not None:
        updates.append("status = ?")
        params.append(update.status)
    if update.current_occupancy is not None:
        updates.append("current_occupancy = ?")
        params.append(update.current_occupancy)
    if update.notes is not None:
        updates.append("notes = ?")
        params.append(update.notes)

    if updates:
        updates.append("last_updated = CURRENT_TIMESTAMP")
        params.append(resource_id)
        conn.execute(
            f"UPDATE resources SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()

    row = conn.execute(
        "SELECT * FROM resources WHERE id = ?", (resource_id,)
    ).fetchone()
    conn.close()
    return dict(row)
