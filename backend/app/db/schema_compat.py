import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# These SQL patches let the current ORM tolerate older project databases by
# filling in missing tables, columns, enum values, and indexes on startup.
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
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'incidenttype') THEN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'incidenttype'::regtype
                  AND enumlabel = 'positive'
            ) THEN
                ALTER TYPE incidenttype ADD VALUE 'positive';
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
    """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS mfa_secret TEXT,
        ADD COLUMN IF NOT EXISTS mfa_pending_secret TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
        expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        last_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        revoked_at TIMESTAMP WITHOUT TIME ZONE,
        revoke_reason VARCHAR(100),
        ip_address INET,
        user_agent TEXT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);""",
    """CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);""",
    """CREATE INDEX IF NOT EXISTS idx_user_sessions_last_seen_at ON user_sessions(last_seen_at);""",
    """CREATE INDEX IF NOT EXISTS idx_user_sessions_revoked_at ON user_sessions(revoked_at);""",
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        action_type VARCHAR(100) NOT NULL,
        user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
        ip_address INET,
        user_agent TEXT,
        result VARCHAR(20) NOT NULL,
        details TEXT,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    );
    """,
    """
    ALTER TABLE audit_logs
        ADD COLUMN IF NOT EXISTS action_type VARCHAR(100),
        ADD COLUMN IF NOT EXISTS user_agent TEXT,
        ADD COLUMN IF NOT EXISTS result VARCHAR(20),
        ADD COLUMN IF NOT EXISTS details TEXT;
    """,
    """
    ALTER TABLE audit_logs
        ALTER COLUMN action_type SET DEFAULT 'unknown',
        ALTER COLUMN result SET DEFAULT 'success';
    """,
    """
    DO $$
    DECLARE
        has_action BOOLEAN;
        has_metadata BOOLEAN;
    BEGIN
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'action'
        ) INTO has_action;

        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'metadata'
        ) INTO has_metadata;

        IF has_action AND has_metadata THEN
            EXECUTE $sql$
                UPDATE audit_logs
                SET action_type = COALESCE(action_type, action, 'unknown'),
                    result = COALESCE(result, 'success'),
                    details = COALESCE(details, CAST(metadata AS TEXT))
                WHERE action_type IS NULL
                   OR result IS NULL
                   OR details IS NULL
            $sql$;
        ELSIF has_action THEN
            EXECUTE $sql$
                UPDATE audit_logs
                SET action_type = COALESCE(action_type, action, 'unknown'),
                    result = COALESCE(result, 'success')
                WHERE action_type IS NULL
                   OR result IS NULL
            $sql$;
        ELSIF has_metadata THEN
            EXECUTE $sql$
                UPDATE audit_logs
                SET action_type = COALESCE(action_type, 'unknown'),
                    result = COALESCE(result, 'success'),
                    details = COALESCE(details, CAST(metadata AS TEXT))
                WHERE action_type IS NULL
                   OR result IS NULL
                   OR details IS NULL
            $sql$;
        ELSE
            UPDATE audit_logs
            SET action_type = COALESCE(action_type, 'unknown'),
                result = COALESCE(result, 'success')
            WHERE action_type IS NULL
               OR result IS NULL;
        END IF;
    END $$;
    """,
    """
    ALTER TABLE audit_logs
        ALTER COLUMN action_type SET NOT NULL,
        ALTER COLUMN result SET NOT NULL;
    """,
    """
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'ip_address'
              AND data_type <> 'inet'
        ) THEN
            ALTER TABLE audit_logs
                ALTER COLUMN ip_address TYPE INET
                USING NULLIF(BTRIM(ip_address::text), '')::INET;
        END IF;
    END $$;
    """,
    """
    DO $$
    DECLARE
        legacy_column RECORD;
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'action'
        ) THEN
            UPDATE audit_logs
            SET action = COALESCE(action, action_type, 'unknown')
            WHERE action IS NULL;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'status'
        ) THEN
            UPDATE audit_logs
            SET status = COALESCE(status, result, 'success')
            WHERE status IS NULL;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND column_name = 'metadata'
        ) THEN
            UPDATE audit_logs
            SET metadata = COALESCE(metadata, to_jsonb(details::text))
            WHERE metadata IS NULL
              AND details IS NOT NULL;
        END IF;

        FOR legacy_column IN
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'audit_logs'
              AND is_nullable = 'NO'
              AND column_name NOT IN ('id', 'action_type', 'result', 'created_at')
        LOOP
            EXECUTE format(
                'ALTER TABLE audit_logs ALTER COLUMN %I DROP NOT NULL',
                legacy_column.column_name
            );
        END LOOP;
    END $$;
    """,
]


def ensure_schema_compatibility(engine: Engine) -> None:
    # Applying compatibility patches during startup keeps the app resilient on
    # team machines where the schema may lag behind the latest code changes.
    """
    Patch older database schemas so the live ORM and API can run without manual migration steps.
    """
    with engine.begin() as connection:
        for statement in SCHEMA_PATCHES:
            connection.execute(text(statement))
    logger.info("Schema compatibility checks completed.")
