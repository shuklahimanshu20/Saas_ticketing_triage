"""
Ticket Triage Agent - core classification logic (UI-independent).

This module is intentionally kept separate from the Streamlit UI (app.py) so it can be
imported and unit tested on its own, and so the LLM integration is isolated from
presentation concerns.

The agent supports two modes:
  - "llm"  : a real call to the Anthropic Claude API (used when ANTHROPIC_API_KEY is set).
  - "mock" : a deterministic, rule-based classifier used for DEMO purposes when no API
             key is configured, or if the LLM call fails for any reason.

The agent NEVER invents information. If it cannot confidently classify a ticket, it
returns category="Unknown" and escalation="Human Review Required" instead of guessing.
"""

import json
import os
import re

# ---------------------------------------------------------------------------
# Allowed enum values (kept in one place so the UI and validation stay in sync)
# ---------------------------------------------------------------------------
ALLOWED_CATEGORIES = {
    "Account/Login",
    "Billing",
    "Technical Issue",
    "Bug",
    "Feature Request",
    "General Inquiry",
    "Service Outage",
    "Legal/Security",
    "Unknown",
}

ALLOWED_PRIORITIES = {"Critical", "High", "Normal", "Low"}

# "Standard" = normal queue handling. "Immediate" and "Human Review Required" are the
# two special states the assignment calls out explicitly.
ALLOWED_ESCALATIONS = {"Immediate", "Standard", "Human Review Required"}

MODEL_NAME = "claude-sonnet-5"

# Minimum confidence the agent will accept before deferring to a human instead of
# displaying a guess.
CONFIDENCE_FLOOR = 0.5


def analyze_ticket(text: str) -> dict:
    """
    Main entry point. Takes the raw customer ticket text and returns a structured
    result dict with keys: category, priority, escalation, assigned_team,
    confidence, reason, mode.

    "mode" is either "llm" or "mock" so callers (the UI, tests) always know whether
    the result came from a real model call or the deterministic demo classifier -
    the agent must never claim a mock result came from the LLM.
    """
    if not text or not text.strip():
        return _human_review_result(
            reason="No ticket text was provided.", confidence=0.0
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            data = _classify_with_llm(text)
            result = _validate_response(data)
            result["mode"] = "llm"
            return result
        except Exception:
            # Any LLM/parsing failure falls back to the mock classifier rather than
            # crashing the UI or showing a malformed result.
            result = _classify_with_mock(text)
            result["mode"] = "mock"
            result["reason"] += " (LLM call failed; demo classifier used instead.)"
            return result

    result = _classify_with_mock(text)
    result["mode"] = "mock"
    return result


def _human_review_result(reason: str, confidence: float = 0.4) -> dict:
    return {
        "category": "Unknown",
        "priority": "Normal",
        "escalation": "Human Review Required",
        "assigned_team": "Customer Support",
        "confidence": confidence,
        "reason": reason,
        "mode": "mock",
    }


# ---------------------------------------------------------------------------
# LLM path (Anthropic Claude)
# ---------------------------------------------------------------------------
def _classify_with_llm(text: str) -> dict:
    """
    Calls the Anthropic API to classify the ticket. Raises on any failure so the
    caller (analyze_ticket) can fall back to the mock classifier.
    """
    from anthropic import Anthropic  # imported lazily so mock mode never requires it

    client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    prompt = f"""You are a support ticket triage classifier for a SaaS company.

Read the ticket below and respond with ONLY a single JSON object (no markdown, no
extra text) with exactly these keys:

- "category": one of {sorted(ALLOWED_CATEGORIES)}
- "priority": one of {sorted(ALLOWED_PRIORITIES)}
- "escalation": one of {sorted(ALLOWED_ESCALATIONS)}
- "assigned_team": a short team name string
- "confidence": a number between 0 and 1
- "reason": a short one or two sentence explanation

Rules:
- If the ticket indicates a live service outage, widespread system failure, legal
  issue, security issue, data breach, or hacking: category must be "Service Outage"
  or "Legal/Security", priority must be "Critical", and escalation must be
  "Immediate".
- If you cannot confidently classify the ticket, set category to "Unknown" and
  escalation to "Human Review Required" with a low confidence score. Do not guess.
- Never invent facts that are not present in the ticket text.

Ticket:
\"\"\"{text}\"\"\"
"""

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)
    return json.loads(json_text)


def _extract_json(raw_text: str) -> str:
    """Strips markdown code fences etc. in case the model wraps its JSON output."""
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM response.")
    return match.group(0)


def _validate_response(data: dict) -> dict:
    """
    Validates the LLM's JSON before it is ever displayed to the user. If anything is
    missing or out of range, the ticket is safely downgraded to Human Review Required
    instead of showing a malformed or made-up result.
    """
    if not isinstance(data, dict):
        return _human_review_result("LLM response was not a valid object.")

    category = data.get("category")
    priority = data.get("priority")
    escalation = data.get("escalation")
    assigned_team = data.get("assigned_team")
    confidence = data.get("confidence")
    reason = data.get("reason")

    if category not in ALLOWED_CATEGORIES:
        return _human_review_result("LLM returned an unrecognized category.")
    if priority not in ALLOWED_PRIORITIES:
        return _human_review_result("LLM returned an unrecognized priority.")
    if escalation not in ALLOWED_ESCALATIONS:
        return _human_review_result("LLM returned an unrecognized escalation state.")
    if not isinstance(assigned_team, str) or not assigned_team.strip():
        assigned_team = "Customer Support"
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        return _human_review_result("LLM returned an invalid confidence score.")
    if not isinstance(reason, str) or not reason.strip():
        reason = "No explanation was provided."

    # The LLM must not be allowed to skip the escalation rule for critical categories.
    if category in {"Service Outage", "Legal/Security"} and escalation != "Immediate":
        escalation = "Immediate"
        priority = "Critical"

    if confidence < CONFIDENCE_FLOOR and escalation != "Immediate":
        category = "Unknown"
        escalation = "Human Review Required"

    return {
        "category": category,
        "priority": priority,
        "escalation": escalation,
        "assigned_team": assigned_team,
        "confidence": round(float(confidence), 2),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Mock / DEMO path - deterministic keyword-based classifier
# ---------------------------------------------------------------------------
_SECURITY_LEGAL_KEYWORDS = [
    "hacked", "hack", "breach", "exposed", "data breach", "security incident",
    "lawsuit", "legal action", "sue", "gdpr", "compliance violation",
    "unauthorized access", "leaked", "ransomware", "phishing",
]

_OUTAGE_KEYWORDS = [
    "outage", "down for everyone", "entire organization", "nobody can access",
    "no one can access", "widespread", "service is down", "platform is down",
    "system is down", "everyone is affected", "all users", "down for all",
    "can't access the platform", "cannot access the platform",
]

_LOGIN_KEYWORDS = [
    "password", "login", "log in", "can't log in", "cannot login",
    "account locked", "forgot my password", "username", "2fa", "reset my password",
]

_BILLING_KEYWORDS = [
    "charged", "billing", "invoice", "subscription", "refund", "payment",
    "overcharged", "credit card", "receipt",
]

_BUG_KEYWORDS = [
    "crash", "crashes", "crashed", "error", "bug", "broken", "fails", "failing",
    "not working", "exception", "freezes",
]

_FEATURE_REQUEST_KEYWORDS = [
    "please add", "feature request", "would be great if", "can you add",
    "suggestion", "add dark mode", "add support for", "it would be nice",
]

_GENERAL_INQUIRY_KEYWORDS = [
    "how do i", "how does", "question about", "just wondering", "just curious",
    "pricing plans", "what is the difference",
]


def _contains_any(text_lower: str, keywords: list) -> bool:
    return any(keyword in text_lower for keyword in keywords)


def _classify_with_mock(text: str) -> dict:
    """
    Deterministic rule-based classifier. Used both as the DEMO/MOCK mode shown to
    evaluators without an API key, and to guarantee predictable behavior for the
    required test cases.
    """
    text_lower = text.lower()
    word_count = len(text.split())

    if _contains_any(text_lower, _SECURITY_LEGAL_KEYWORDS):
        return {
            "category": "Legal/Security",
            "priority": "Critical",
            "escalation": "Immediate",
            "assigned_team": "Security / Legal Team",
            "confidence": 0.95,
            "reason": (
                "The ticket references a possible security incident, hacking, or "
                "data exposure, which requires immediate escalation."
            ),
        }

    if _contains_any(text_lower, _OUTAGE_KEYWORDS):
        return {
            "category": "Service Outage",
            "priority": "Critical",
            "escalation": "Immediate",
            "assigned_team": "Incident Response / Engineering",
            "confidence": 0.96,
            "reason": (
                "The ticket indicates a widespread outage affecting many or all "
                "users, which requires immediate escalation."
            ),
        }

    if _contains_any(text_lower, _LOGIN_KEYWORDS):
        return {
            "category": "Account/Login",
            "priority": "Normal",
            "escalation": "Standard",
            "assigned_team": "Customer Support",
            "confidence": 0.9,
            "reason": "The ticket describes a single-user account or login problem.",
        }

    if _contains_any(text_lower, _BILLING_KEYWORDS):
        return {
            "category": "Billing",
            "priority": "Normal",
            "escalation": "Standard",
            "assigned_team": "Billing Support",
            "confidence": 0.9,
            "reason": "The ticket describes a billing or payment discrepancy.",
        }

    if _contains_any(text_lower, _BUG_KEYWORDS):
        return {
            "category": "Bug",
            "priority": "Normal",
            "escalation": "Standard",
            "assigned_team": "Technical Support / Engineering",
            "confidence": 0.85,
            "reason": "The ticket describes unexpected application behavior consistent with a bug.",
        }

    if _contains_any(text_lower, _FEATURE_REQUEST_KEYWORDS):
        return {
            "category": "Feature Request",
            "priority": "Normal",
            "escalation": "Standard",
            "assigned_team": "Product Team",
            "confidence": 0.88,
            "reason": "The ticket is asking for new functionality rather than reporting a problem.",
        }

    if _contains_any(text_lower, _GENERAL_INQUIRY_KEYWORDS):
        return {
            "category": "General Inquiry",
            "priority": "Low",
            "escalation": "Standard",
            "assigned_team": "Customer Support",
            "confidence": 0.75,
            "reason": "The ticket asks a general question without indicating a specific problem.",
        }

    # No confident match - the agent does not guess. Short/vague tickets are the
    # clearest case for this, but any unmatched text falls here too.
    return _human_review_result(
        reason=(
            "The ticket does not contain enough information to confidently "
            "determine the issue."
        ),
        confidence=0.35 if word_count <= 6 else 0.45,
    )
