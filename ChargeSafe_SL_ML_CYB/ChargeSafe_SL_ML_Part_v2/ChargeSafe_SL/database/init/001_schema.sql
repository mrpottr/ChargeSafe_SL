CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "cube";
CREATE EXTENSION IF NOT EXISTS "earthdistance";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'standard_user');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'station_status') THEN
        CREATE TYPE station_status AS ENUM (
            'operational',
            'faulty',
            'offline',
            'unknown',
            'maintenance'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'station_source') THEN
        CREATE TYPE station_source AS ENUM ('opencharge_map', 'synthetic', 'community');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cyber_risk_level') THEN
        CREATE TYPE cyber_risk_level AS ENUM ('Low', 'Medium', 'High');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'incident_type') THEN
        CREATE TYPE incident_type AS ENUM (
            'thermal_fault',
            'voltage_irregularity',
            'connector_damage',
            'firmware_issue',
            'network_breach',
            'physical_damage',
            'authentication_failure',
            'other'
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'incident_status') THEN
        CREATE TYPE incident_status AS ENUM ('pending', 'verified', 'rejected', 'resolved');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'damage_label') THEN
        CREATE TYPE damage_label AS ENUM ('none', 'minor', 'moderate', 'severe');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'standard_user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS charging_stations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    address TEXT,
    city VARCHAR(100),
    operator VARCHAR(255),
    connector_types VARCHAR(255),
    charging_power_kw NUMERIC(6, 2),
    charging_level VARCHAR(50),
    status station_status NOT NULL DEFAULT 'unknown',
    source station_source NOT NULL DEFAULT 'opencharge_map',
    is_public BOOLEAN DEFAULT TRUE,
    date_installed DATE,
    safety_score NUMERIC(5, 2) CHECK (safety_score BETWEEN 0 AND 100),
    cyber_risk_level cyber_risk_level,
    last_scored_at TIMESTAMPTZ,
    ocm_id VARCHAR(50) UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stations_location
    ON charging_stations USING GIST (ll_to_earth(latitude, longitude));
CREATE INDEX IF NOT EXISTS idx_stations_status ON charging_stations(status);

CREATE TABLE IF NOT EXISTS training_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id VARCHAR(50) DEFAULT 'v1.0',
    charger_power_kw INT,
    avg_temperature_c NUMERIC(5, 2),
    charging_duration_min INT,
    reported_faults_count INT,
    voltage_stability_score INT,
    charger_age_years NUMERIC(4, 2),
    connector_compat_score INT,
    firmware_age_years NUMERIC(4, 2),
    network_security_score INT,
    risk_level cyber_risk_level,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cyber_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    criterion_name TEXT NOT NULL,
    description TEXT,
    iec_reference TEXT,
    weight NUMERIC(5, 2) NOT NULL,
    score_low INT DEFAULT 0,
    score_medium INT DEFAULT 2,
    score_high INT DEFAULT 4
);

CREATE TABLE IF NOT EXISTS cyber_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
    criterion_id UUID NOT NULL REFERENCES cyber_criteria(id) ON DELETE RESTRICT,
    score_value INT NOT NULL,
    risk_rating cyber_risk_level,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_cyber_scores_station ON cyber_scores(station_id);

CREATE TABLE IF NOT EXISTS ml_risk_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
    safety_score NUMERIC(5, 2) NOT NULL CHECK (safety_score BETWEEN 0 AND 100),
    model_confidence NUMERIC(5, 4) CHECK (model_confidence BETWEEN 0 AND 1),
    model_version VARCHAR(50) NOT NULL,
    trigger_source VARCHAR(50),
    feature_vector JSONB,
    score_breakdown JSONB,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_scores_station
    ON ml_risk_scores(station_id, scored_at DESC);

CREATE TABLE IF NOT EXISTS incident_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    station_id UUID NOT NULL REFERENCES charging_stations(id) ON DELETE CASCADE,
    reported_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    incident_type incident_type NOT NULL,
    severity cyber_risk_level NOT NULL,
    description TEXT,
    status incident_status NOT NULL DEFAULT 'pending',
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by UUID REFERENCES users(id),
    verified_at TIMESTAMPTZ,
    occurred_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_station
    ON incident_reports(station_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ev_vehicle_reference (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    make VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    year_range VARCHAR(50),
    connector_type VARCHAR(100),
    battery_capacity_kwh NUMERIC(6, 2),
    max_ac_charge_kw NUMERIC(6, 2),
    max_dc_charge_kw NUMERIC(6, 2),
    chemistry VARCHAR(50),
    country_of_origin VARCHAR(100),
    recommended_max_temp_c INT,
    common_in_sri_lanka BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chatbot_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    station_id UUID REFERENCES charging_stations(id) ON DELETE SET NULL,
    conversation_history JSONB NOT NULL DEFAULT '[]',
    offline_mode BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    metadata JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_stations_updated_at ON charging_stations;
CREATE TRIGGER trg_stations_updated_at
    BEFORE UPDATE ON charging_stations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_incidents_updated_at ON incident_reports;
CREATE TRIGGER trg_incidents_updated_at
    BEFORE UPDATE ON incident_reports
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS trg_chat_updated_at ON chatbot_sessions;
CREATE TRIGGER trg_chat_updated_at
    BEFORE UPDATE ON chatbot_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE FUNCTION flag_station_for_rescoring() RETURNS TRIGGER AS $$
BEGIN
    UPDATE charging_stations
    SET last_scored_at = NULL
    WHERE id = NEW.station_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_rescore_on_incident ON incident_reports;
CREATE TRIGGER trg_rescore_on_incident
    AFTER INSERT ON incident_reports
    FOR EACH ROW
    EXECUTE FUNCTION flag_station_for_rescoring();
