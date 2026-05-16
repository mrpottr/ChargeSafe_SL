from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# This function creates and manages an independent database session for each incoming request. 
# It is built using a Python generator to provide the active session to the application, 
# and guarantees the database connection is safely closed in the finally block after use.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

