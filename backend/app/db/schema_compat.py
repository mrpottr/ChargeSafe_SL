import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


SCHEMA_PATCHES = [
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cyber_risk_level') THEN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'cyber_risk_level'::regtype
                  AND enumlabel = 'LOW'
            ) THEN
                ALTER TYPE cyber_risk_level ADD VALUE 'LOW';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'cyber_risk_level'::regtype
                  AND enumlabel = 'MEDIUM'
            ) THEN
                ALTER TYPE cyber_risk_level ADD VALUE 'MEDIUM';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'cyber_risk_level'::regtype
                  AND enumlabel = 'HIGH'
            ) THEN
                ALTER TYPE cyber_risk_level ADD VALUE 'HIGH';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'cyber_risk_level'::regtype
                  AND enumlabel = 'CRITICAL'
            ) THEN
                ALTER TYPE cyber_risk_level ADD VALUE 'CRITICAL';
            END IF;
        END IF;
    END $$;
    """,
    """
    ALTER TABLE charging_stations
        ADD COLUMN IF NOT EXISTS firmware_version VARCHAR(50),
        ADD COLUMN IF NOT EXISTS firmware_age_days INTEGER,
        ADD COLUMN IF NOT EXISTS temperature_celsius DOUBLE PRECISION,
        ADD COLUMN IF NOT EXISTS power_status VARCHAR(50),
        ADD COLUMN IF NOT EXISTS fault_count INTEGER DEFAULT 0;
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
        report_type VARCHAR(50) NOT NULL,
        severity INTEGER,
        description TEXT NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'resolved',
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        message TEXT NOT NULL,
        notification_type VARCHAR(50) NOT NULL,
        icon VARCHAR(10),
        is_read BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role VARCHAR(10) NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        push_notifications_enabled BOOLEAN DEFAULT TRUE,
        alert_threshold INTEGER DEFAULT 70,
        units_system VARCHAR(50) DEFAULT 'Metric (C, km)',
        language VARCHAR(50) DEFAULT 'English',
        map_pin_color_mode VARCHAR(100) DEFAULT 'Risk Score (Green/Amber/Red)',
        safe_threshold INTEGER DEFAULT 30,
        warning_threshold INTEGER DEFAULT 70,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS score_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
        score DOUBLE PRECISION NOT NULL,
        level VARCHAR(20) NOT NULL,
        trigger VARCHAR(50) NOT NULL,
        recorded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS temperature_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
        temperature_celsius DOUBLE PRECISION NOT NULL,
        recorded_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
]


def ensure_schema_compatibility(engine: Engine) -> None:
    """
    Patch older database schemas so the live ORM and API can run without manual migration steps.
    """
    with engine.begin() as connection:
        for statement in SCHEMA_PATCHES:
            connection.execute(text(statement))
    logger.info("Schema compatibility checks completed.")
