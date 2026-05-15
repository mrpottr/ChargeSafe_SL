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
        CREATE TYPE cyber_risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
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

CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    revoke_reason VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at ON user_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_last_seen_at ON user_sessions(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_revoked_at ON user_sessions(revoked_at);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type VARCHAR(100) NOT NULL,
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    ip_address INET,
    user_agent TEXT,
    result VARCHAR(20) NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_result ON audit_logs(result);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

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
    score_high INT DEFAULT 4,
    UNIQUE (criterion_name)
);
INSERT INTO cyber_criteria (
    criterion_name,
    description,
    iec_reference,
    weight,
    score_low,
    score_medium,
    score_high
)
VALUES
(
    'Secure Remote Access',
    'Remote maintenance and operator access must use secure authenticated channels.',
    'IEC 62443 - Access Control',
    8.00,
    0,
    2,
    4
),
(
    'Role-Based Access Control',
    'Users should only have permissions required for their responsibilities.',
    'IEC 62443 - Use Control',
    7.00,
    0,
    2,
    4
),
(
    'Password Policy Enforcement',
    'Strong password rules and password rotation must be enforced.',
    'IEC 62443 - Identification and Authentication Control',
    6.00,
    0,
    2,
    4
),
(
    'Multi-Factor Authentication',
    'Privileged or remote access should require more than one authentication factor.',
    'IEC 62443 - Identification and Authentication Control',
    8.00,
    0,
    2,
    4
),
(
    'Account Lockout Protection',
    'Repeated failed login attempts must trigger lockout or delay protections.',
    'IEC 62443 - Identification and Authentication Control',
    5.00,
    0,
    2,
    4
),
(
    'Session Timeout Control',
    'Inactive management sessions should automatically expire after a safe period.',
    'IEC 62443 - Session Integrity',
    4.00,
    0,
    2,
    4
),
(
    'Least Privilege Administration',
    'Administrative permissions should be minimized to essential functions only.',
    'IEC 62443 - Restricted Data Flow and Use Control',
    7.00,
    0,
    2,
    4
),
(
    'Device Identity Management',
    'Each charging station should have a unique verifiable device identity.',
    'IEC 62443 - Identification and Authentication Control',
    7.00,
    0,
    2,
    4
),
(
    'Secure Firmware Update Mechanism',
    'Firmware updates must be signed, verified, and protected against tampering.',
    'IEC 62443 - System Integrity / OWASP IoT Top 10 - Insecure Software Update Mechanism',
    10.00,
    0,
    2,
    4
),
(
    'Firmware Version Currency',
    'Station firmware should be current and free from known critical vulnerabilities.',
    'IEC 62443 - Patch and Vulnerability Management',
    8.00,
    0,
    2,
    4
),
(
    'Patch Management Process',
    'Security patches should be tested, approved, and applied within a defined timeline.',
    'IEC 62443 - Security Program / Patch Management',
    8.00,
    0,
    2,
    4
),
(
    'Malware Protection Controls',
    'Systems should include controls to prevent, detect, and respond to malicious code.',
    'IEC 62443 - System Integrity',
    6.00,
    0,
    2,
    4
),
(
    'Log Generation and Retention',
    'Security-relevant events should be logged and retained for investigation.',
    'IEC 62443 - Audit Log / Accountability',
    7.00,
    0,
    2,
    4
),
(
    'Security Monitoring and Alerting',
    'The system should generate alerts for suspicious behavior and security events.',
    'IEC 62443 - Continuous Monitoring',
    8.00,
    0,
    2,
    4
),
(
    'Incident Response Readiness',
    'Defined procedures should exist for containment, investigation, and recovery.',
    'IEC 62443 - Security Program / Incident Response',
    7.00,
    0,
    2,
    4
),
(
    'Network Segmentation',
    'Charging infrastructure should be separated from other business or public networks.',
    'IEC 62443 - Restricted Data Flow',
    9.00,
    0,
    2,
    4
),
(
    'Port and Service Hardening',
    'Unused ports, services, and protocols should be disabled to reduce attack surface.',
    'IEC 62443 - System Hardening / OWASP IoT Top 10 - Insecure Network Services',
    9.00,
    0,
    2,
    4
),
(
    'Secure Communication Encryption',
    'Sensitive station-to-server communication must be protected with strong encryption.',
    'IEC 62443 - Confidentiality / OWASP IoT Top 10 - Lack of Secure Data Transfer and Storage',
    9.00,
    0,
    2,
    4
),
(
    'Certificate and Key Management',
    'Cryptographic keys and certificates must be generated, stored, rotated, and revoked securely.',
    'IEC 62443 - Cryptographic Key Management',
    8.00,
    0,
    2,
    4
),
(
    'Data at Rest Protection',
    'Sensitive stored data should be encrypted or otherwise protected from unauthorized access.',
    'IEC 62443 - Data Confidentiality / OWASP IoT Top 10 - Lack of Secure Data Transfer and Storage',
    7.00,
    0,
    2,
    4
),
(
    'Backup and Recovery Security',
    'Critical configurations and security data should be backed up and recoverable safely.',
    'IEC 62443 - Availability / Recovery Capability',
    6.00,
    0,
    2,
    4
),
(
    'Physical Tamper Protection',
    'The charger should resist, detect, or report unauthorized physical access or tampering.',
    'IEC 62443 - Physical Security',
    8.00,
    0,
    2,
    4
),
(
    'Default Credential Elimination',
    'Factory default or hardcoded credentials must be removed or disabled before deployment.',
    'OWASP IoT Top 10 - Weak, Guessable, or Hardcoded Passwords',
    10.00,
    0,
    2,
    4
),
(
    'Insecure Ecosystem Interface Protection',
    'Mobile apps, APIs, cloud dashboards, and web portals must be secured against misuse.',
    'OWASP IoT Top 10 - Insecure Ecosystem Interfaces',
    8.00,
    0,
    2,
    4
),
(
    'Secure Configuration Management',
    'System settings should use secure defaults and block unnecessary risky configurations.',
    'OWASP IoT Top 10 - Lack of Secure Update Mechanism / Insecure Default Settings',
    7.00,
    0,
    2,
    4
),
(
    'Personal Data Privacy Controls',
    'Personally identifiable information and user charging records must be handled securely.',
    'OWASP IoT Top 10 - Privacy Protection / IEC 62443 - Data Confidentiality',
    7.00,
    0,
    2,
    4
),
(
    'Secure Boot Integrity',
    'The device should verify trusted software during startup to prevent unauthorized code execution.',
    'IEC 62443 - System Integrity',
    8.00,
    0,
    2,
    4
),
(
    'Vulnerability Disclosure Readiness',
    'A process should exist to receive, assess, and remediate reported security vulnerabilities.',
    'IEC 62443 - Security Management',
    5.00,
    0,
    2,
    4
),
(
    'DoS Resilience',
    'The station and backend should tolerate or recover from denial-of-service conditions.',
    'IEC 62443 - Resource Availability',
    7.00,
    0,
    2,
    4
),
(
    'Telemetry and Diagnostic Exposure Control',
    'Diagnostic interfaces and telemetry outputs should not expose excessive internal information.',
    'OWASP IoT Top 10 - Insecure Default Settings / Information Exposure',
    6.00,
    0,
    2,
    4
)
ON CONFLICT (criterion_name) DO NOTHING;
INSERT INTO cyber_criteria (
    criterion_name,
    description,
    iec_reference,
    weight,
    score_low,
    score_medium,
    score_high
)
VALUES
(
    'Weak Default Password Protection',
    'Device must not rely on default or guessable credentials.',
    'OWASP IoT Top 10 - Weak, Guessable, or Hardcoded Passwords',
    9.00,
    0,
    2,
    4
),
(
    'Secure Update Mechanism',
    'Firmware and software updates must be signed and verified before installation.',
    'OWASP IoT Top 10 - Insecure Software Update Mechanism',
    9.00,
    0,
    2,
    4
),
(
    'Data Encryption in Transit',
    'All sensitive communication must be encrypted over the network.',
    'OWASP IoT Top 10 - Lack of Secure Data Transfer and Storage',
    8.00,
    0,
    2,
    4
),
    'Insecure Network Services Protection',
    'Unused or risky network services must be disabled or restricted.',
    'OWASP IoT Top 10 - Insecure Network Services',
    9.00,
    0,
    2,
    4
),
    'Lack of Secure Default Settings Protection',
    'Devices must ship and operate with secure-by-default settings.',
    'OWASP IoT Top 10 - Use of Insecure or Outdated Components / Insecure Default Settings',
    7.00,
    0,
    2,
    4
),
(
    'Outdated Component Management',
    'Third-party libraries, firmware components, and dependencies must be kept up to date.',
    'OWASP IoT Top 10 - Use of Insecure or Outdated Components',
    8.00,
    0,
    2,
    4
),
(
    'Privacy Protection Controls',
    'Personal and operational data must be collected, stored, and shared with proper privacy safeguards.',
    'OWASP IoT Top 10 - Insufficient Privacy Protection',
    7.00,
    0,
    2,
    4
),
(
    'Secure Device Management',
    'Remote administration, provisioning, and support features must be securely controlled.',
    'OWASP IoT Top 10 - Lack of Device Management',
    8.00,
    0,
    2,
    4
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
    action_type VARCHAR(100) NOT NULL,
    ip_address INET,
    user_agent TEXT,
    result VARCHAR(20) NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
ON CONFLICT (criterion_name) DO NOTHING;

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
