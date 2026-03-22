from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/stations")
def list_stations(db: Session = Depends(get_db)):
    result = db.execute(
        text(
            """
            SELECT id, name, city, status, safety_score, latitude, longitude
            FROM charging_stations
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
    )
    return [dict(row._mapping) for row in result]
