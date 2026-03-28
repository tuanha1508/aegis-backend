from fastapi import APIRouter, HTTPException
from app.db.database import get_connection

router = APIRouter(tags=["recovery"])


@router.get("/recovery/briefs")
async def get_briefs():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM recovery_briefs ORDER BY generated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/recovery/briefs/{neighborhood}")
async def get_brief(neighborhood: str):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM recovery_briefs WHERE neighborhood = %s", (neighborhood,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404, detail="Brief not found for neighborhood"
            )
        return dict(row)
    finally:
        conn.close()
