import math
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from psycopg import sql

from app.db.database import get_connection
from app.models.resource import ResourceUpdate

router = APIRouter(tags=["resources"])


@router.get("/resources")
async def get_resources(type: Optional[str] = Query(None)):
    conn = get_connection()
    try:
        if type:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = %s ORDER BY name", (type,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM resources ORDER BY name").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/resources/nearest")
async def get_nearest_resource(
    lat: float = Query(...),
    lng: float = Query(...),
    type: Optional[str] = Query(None),
):
    conn = get_connection()
    try:
        if type:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = %s AND status = 'open'",
                (type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resources WHERE status = 'open'"
            ).fetchall()

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
    finally:
        conn.close()


@router.put("/resources/{resource_id}")
async def update_resource(resource_id: int, update: ResourceUpdate):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM resources WHERE id = %s", (resource_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Resource not found")

        set_parts: list = []
        params: list = []
        if update.status is not None:
            set_parts.append(sql.SQL("status = {}").format(sql.Placeholder()))
            params.append(update.status)
        if update.current_occupancy is not None:
            set_parts.append(
                sql.SQL("current_occupancy = {}").format(sql.Placeholder())
            )
            params.append(update.current_occupancy)
        if update.notes is not None:
            set_parts.append(sql.SQL("notes = {}").format(sql.Placeholder()))
            params.append(update.notes)

        if set_parts:
            set_parts.append(sql.SQL("last_updated = NOW()"))
            query = sql.SQL("UPDATE resources SET {} WHERE id = {}").format(
                sql.SQL(", ").join(set_parts),
                sql.Placeholder(),
            )
            params.append(resource_id)
            conn.execute(query, params)
            conn.commit()

        row = conn.execute(
            "SELECT * FROM resources WHERE id = %s", (resource_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()
