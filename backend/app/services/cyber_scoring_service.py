from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ChargingStation, CyberCriterion, CyberRiskLevel, CyberScore, StationStatus


class CyberScoringService:
    @staticmethod
    def _score_to_risk_level(score_value: int, criterion: CyberCriterion) -> CyberRiskLevel:
        if score_value >= criterion.score_high:
            return CyberRiskLevel.high
        if score_value >= criterion.score_medium:
            return CyberRiskLevel.medium
        return CyberRiskLevel.low

    @staticmethod
    def _base_score(station: ChargingStation) -> int:
        score = 0

        safety_score = float(station.safety_score or 0)
        firmware_age_days = int(station.firmware_age_days or 0)
        fault_count = int(station.fault_count or 0)
        temperature = float(station.temperature_celsius or 0)
        power_status = (station.power_status or "").lower()
        status = station.status

        if safety_score >= 80:
            score += 2
        elif safety_score >= 45:
            score += 1

        if firmware_age_days >= 300:
            score += 2
        elif firmware_age_days >= 120:
            score += 1

        if fault_count >= 4:
            score += 2
        elif fault_count >= 2:
            score += 1

        if temperature >= 45:
            score += 2
        elif temperature >= 35:
            score += 1

        if status in {StationStatus.faulty, StationStatus.offline}:
            score += 2
        elif status == StationStatus.maintenance:
            score += 1

        if power_status == "unstable":
            score += 2
        elif power_status == "fluctuation":
            score += 1

        return min(score, 4)

    @staticmethod
    def _criterion_score(station: ChargingStation, criterion: CyberCriterion) -> tuple[int, str]:
        # Normalise to lowercase+stripped so DB name casing never causes a silent miss
        name = (criterion.criterion_name or "").strip().lower()
        base_score = CyberScoringService._base_score(station)
        firmware_age_days = int(station.firmware_age_days or 0)
        fault_count = int(station.fault_count or 0)
        temperature = float(station.temperature_celsius or 0)
        power_status = (station.power_status or "").lower()
        safety_score = float(station.safety_score or 0)
        status = station.status

        score_value = base_score
        note = "Evaluated using station telemetry and current cyber posture indicators."

        def _match(*names: str) -> bool:
            return name in {n.strip().lower() for n in names}

        if _match("Secure Firmware Update Mechanism", "Firmware Version Currency", "Patch Management Process",
                  "Secure Update Mechanism", "Outdated Component Management"):
            if firmware_age_days >= 300:
                score_value = 4
            elif firmware_age_days >= 120:
                score_value = 2
            else:
                score_value = 0
            note = f"Firmware age is {firmware_age_days} days."
        elif _match("Physical Tamper Protection", "Malware Protection Controls"):
            if fault_count >= 4 or status == StationStatus.faulty:
                score_value = 4
            elif fault_count >= 2:
                score_value = 2
            else:
                score_value = 0
            note = f"Station fault count is {fault_count}."
        elif _match("Secure Communication Encryption", "Data at Rest Protection",
                    "Data Encryption in Transit", "Data Encryption at Rest",
                    "Certificate and Key Management"):
            if safety_score >= 80 or power_status == "unstable":
                score_value = 4
            elif safety_score >= 45 or power_status == "fluctuation":
                score_value = 2
            else:
                score_value = 0
            note = f"Safety score is {safety_score:.1f} and power status is '{station.power_status or 'Unknown'}'."
        elif _match("Security Monitoring and Alerting", "Incident Response Readiness", "DoS Resilience"):
            if status in {StationStatus.faulty, StationStatus.offline}:
                score_value = 4
            elif status == StationStatus.maintenance:
                score_value = 2
            else:
                score_value = max(base_score - 1, 0)
            note = f"Station status is '{status.value if status else 'unknown'}'."
        elif _match("Weak Default Password Protection", "Default Credential Elimination",
                    "Multi-Factor Authentication", "Role-Based Access Control",
                    "Least Privilege Administration", "Password Policy Enforcement"):
            if safety_score >= 80:
                score_value = 4
            elif safety_score >= 45:
                score_value = 2
            else:
                score_value = 0
            note = f"Access-control proxy score derived from station safety score {safety_score:.1f}."
        elif _match("Network Segmentation", "Port and Service Hardening",
                    "Insecure Network Services Protection", "Insecure Ecosystem Interface Protection",
                    "Insecure Ecosystem Interface Protection", "Lack of Secure Default Settings Protection",
                    "Secure Configuration Management"):
            if power_status == "unstable" or status in {StationStatus.faulty, StationStatus.offline}:
                score_value = 4
            elif power_status == "fluctuation" or status == StationStatus.maintenance:
                score_value = 2
            else:
                score_value = 0
            note = f"Network exposure proxy derived from station status '{status.value if status else 'unknown'}' and power status '{station.power_status or 'Unknown'}'."
        elif _match("Backup and Recovery Security", "Secure Boot Integrity",
                    "Vulnerability Disclosure Readiness", "Secure Device Management"):
            score_value = 4 if base_score >= 4 else 2 if base_score >= 2 else 0
            note = f"Overall base cyber score for the station is {base_score}."
        elif _match("Account Lockout Protection", "Session Timeout Control",
                    "Device Identity Management", "Secure Remote Access"):
            score_value = 4 if safety_score >= 80 else 2 if safety_score >= 45 else 0
            note = f"Identity and session control proxy derived from station safety score {safety_score:.1f}."
        elif _match("Personal Data Privacy Controls", "Privacy Protection Controls",
                    "Telemetry and Diagnostic Exposure Control"):
            if temperature >= 45 or fault_count >= 4:
                score_value = 4
            elif temperature >= 35 or fault_count >= 2:
                score_value = 2
            else:
                score_value = 0
            note = f"Operational anomaly proxy derived from temperature {temperature:.1f}C and fault count {fault_count}."

        return score_value, note

    @staticmethod
    def score_station(db: Session, station: ChargingStation) -> int:
        criteria = db.query(CyberCriterion).order_by(CyberCriterion.criterion_name.asc()).all()
        if not criteria:
            return 0

        db.query(CyberScore).filter(CyberScore.station_id == station.id).delete()

        created = 0
        evaluated_at = datetime.utcnow()
        highest_risk = CyberRiskLevel.low

        for criterion in criteria:
            score_value, notes = CyberScoringService._criterion_score(station, criterion)
            risk_rating = CyberScoringService._score_to_risk_level(score_value, criterion)

            if risk_rating == CyberRiskLevel.high:
                highest_risk = CyberRiskLevel.high
            elif risk_rating == CyberRiskLevel.medium and highest_risk == CyberRiskLevel.low:
                highest_risk = CyberRiskLevel.medium

            db.add(
                CyberScore(
                    station_id=station.id,
                    criterion_id=criterion.id,
                    score_value=score_value,
                    risk_rating=risk_rating,
                    evaluated_at=evaluated_at,
                    notes=notes,
                )
            )
            created += 1

        station.cyber_risk_level = highest_risk
        station.last_scored_at = evaluated_at
        return created

    @staticmethod
    def score_all_stations(db: Session) -> dict[str, int]:
        stations = db.query(ChargingStation).all()
        scored_stations = 0
        created_scores = 0

        for station in stations:
            created_for_station = CyberScoringService.score_station(db, station)
            if created_for_station:
                scored_stations += 1
                created_scores += created_for_station

        db.commit()
        return {
            "stations_scored": scored_stations,
            "score_rows_created": created_scores,
        }
