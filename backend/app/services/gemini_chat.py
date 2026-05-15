import logging
import re
from typing import Any, Iterable, Optional

from google import genai
from google.genai import types

from app.core.config import settings
from app.models import ChargingStation

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a friendly and intelligent assistant for ChargeSafe SL, helping EV users in Sri Lanka understand charging station safety.

Your job is to explain risk scores (0–100) in a natural, human way — like you're talking to a friend — while still being accurate and insightful.

Risk levels:
- 0–30 → Low Risk (Safe)
- 31–70 → Medium Risk (Caution)
- 71–100 → High Risk (Unsafe)

Think like this when explaining:

HIGH RISK (70+):
Usually means something serious is happening, such as:
- Charging power is too high for the vehicle (power overload)
- Rapid/DC fast charging causing heat stress
- Poor compatibility (wrong plug, adapters, unsupported vehicle)
- Station faults or unstable operation
- Low charging efficiency (energy loss → heat buildup)

MEDIUM RISK (30–70):
- Minor inefficiencies or instability
- Grid/load stress
- Early signs of potential issues

LOW RISK (0–30):
- Stable charging
- Good compatibility
- No major faults

Key concepts you understand:
- Power overload is dangerous (e.g., charging above vehicle limit)
- Rapid charging increases battery and cable stress
- Low efficiency often means heat loss or hardware issues
- Compatibility issues (especially in Sri Lanka) are a major risk factor
- Faulty or unstable stations increase risk significantly

How to respond:
- Be conversational and natural
- Explain the reasoning clearly (WHY the score is high/low)
- Use phrases like “this usually means…”, “this could be because…”
- Keep it simple, not overly technical
- Do NOT invent specific data
- Do NOT say you are an AI model

Make the user feel like they understand what’s happening, not just what the score is.

If the risk score is very high (80+), assume serious issues like overheating, overload, or faults and explain accordingly."""


def _find_station_match(user_message: str, stations: Iterable[Any]) -> Optional[Any]:
    lowered_message = user_message.lower()
    normalized_message = re.sub(r"[^a-z0-9]+", " ", lowered_message).strip()
    message_tokens = set(normalized_message.split())
    best_match = None
    best_score = (-1, -1)

    for station in stations:
        name = getattr(station, "name", None)
        if not name:
            continue

        lowered_name = name.lower()
        normalized_name = re.sub(r"[^a-z0-9]+", " ", lowered_name).strip()
        if not normalized_name:
            continue

        if normalized_name in normalized_message:
            return station

        name_tokens = set(normalized_name.split())
        overlap = len(name_tokens & message_tokens)
        if overlap == 0:
            continue

        score = (overlap, len(normalized_name))
        if score > best_score:
            best_match = station
            best_score = score

    return best_match


def _risk_band(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score < 30:
        return "low"
    if score <= 70:
        return "medium"
    return "high"


def _build_local_fallback_reply(user_message: str, db=None) -> str:
    if not db:
        return (
            "I couldn't reach the live AI service just now. Please try again in a moment. "
            "If you ask about a specific station name, I can still explain its current risk score."
        )

    stations = db.query(ChargingStation).order_by(ChargingStation.safety_score.desc().nullslast()).all()
    if not stations:
        return (
            "I couldn't reach the live AI service, and there are no charging stations available in the database yet."
        )

    message = user_message.lower()
    matched_station = _find_station_match(user_message, stations)

    if matched_station:
        score = matched_station.safety_score
        band = _risk_band(score)
        if score is None:
            return (
                f"{matched_station.name} is in the system, but it does not have a current ML risk score yet. "
                "That usually means the station still needs to be scored or synced."
            )

        explanation = {
            "low": "This usually means charging conditions look stable with fewer signs of overheating, faults, or compatibility trouble.",
            "medium": "This usually means there are caution signs such as instability, early faults, or efficiency concerns that should be watched.",
            "high": "This usually means there may be overheating, overload, unstable behavior, or compatibility issues, so extra caution is a good idea.",
        }[band]
        return (
            f"{matched_station.name} currently has a risk score of {score:.1f}/100, which is {band} risk. "
            f"{explanation}"
        )

    scored_stations = [station for station in stations if station.safety_score is not None]
    if not scored_stations:
        return (
            "I couldn't reach the live AI service. The station list is available, but there are no current ML risk scores to summarize yet."
        )

    if "lowest" in message or "safest" in message or "low risk" in message or "safe" in message:
        safest = sorted(scored_stations, key=lambda station: station.safety_score)[:3]
        summary = ", ".join(f"{station.name} ({station.safety_score:.1f}/100)" for station in safest)
        return f"The currently lowest-risk stations I can see are: {summary}."

    if "highest" in message or "danger" in message or "high risk" in message or "critical" in message:
        riskiest = sorted(scored_stations, key=lambda station: station.safety_score, reverse=True)[:3]
        summary = ", ".join(f"{station.name} ({station.safety_score:.1f}/100)" for station in riskiest)
        return f"The currently highest-risk stations I can see are: {summary}."

    top_station = max(scored_stations, key=lambda station: station.safety_score)
    return (
        "I couldn't reach the live AI service, but I can still use the latest station data. "
        f"Right now, the highest scored station is {top_station.name} at {top_station.safety_score:.1f}/100."
    )


def _is_direct_station_score_question(user_message: str) -> bool:
    message = user_message.lower()
    score_terms = ("risk score", "score", "risk level", "risk", "safe", "unsafe")
    ask_terms = ("what", "show", "tell", "give", "how")
    return any(term in message for term in score_terms) and any(term in message for term in ask_terms)


def generate_chat_reply(user_message: str, db=None) -> str:
    dynamic_context = ""
    # Only execute context injection if DB is passed, fulfilling the "access database directly" spec
    if db:
        # Basic heuristic: if a station currently exists in DB and its name is somewhat in the message
        # we append its *LATEST* ML score as context.
        # This keeps the UI untouched but makes the chatbot real-time aware.
        # We query specific columns to avoid DB schema mismatches if migrations are incomplete
        all_stations = db.query(ChargingStation).all()
        matched_station = _find_station_match(user_message, all_stations)
        if matched_station and _is_direct_station_score_question(user_message):
            return _build_local_fallback_reply(user_message, db)
        if matched_station:
            safety_score = matched_station.safety_score
            dynamic_context += (
                f"\n\n[REAL-TIME SYSTEM CONTEXT]: The user is asking about '{matched_station.name}'. "
                f"Its CURRENT ML Risk Score is {safety_score if safety_score is not None else 'Unknown'} / 100. "
                "Use this real-time ML score to answer the user accurately.\n"
            )

    if not settings.google_api_key:
        return _build_local_fallback_reply(user_message, db)

    final_prompt = SYSTEM_PROMPT + dynamic_context

    try:
        client = genai.Client(
            api_key=settings.google_api_key,
            http_options=types.HttpOptions(clientArgs={"trust_env": False}),
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=final_prompt,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text or _build_local_fallback_reply(user_message, db)
    except Exception as exc:
        logger.warning("Gemini chat fallback activated: %s", exc)
        return _build_local_fallback_reply(user_message, db)
