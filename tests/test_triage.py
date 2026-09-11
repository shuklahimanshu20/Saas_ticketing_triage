"""
Automated tests for the Ticket Triage Agent.

These tests explicitly clear ANTHROPIC_API_KEY so they always exercise the
deterministic mock classifier - this keeps them fast, free, and independent of
network access or a real API key, while still proving the required behavior.
"""

import sys
from pathlib import Path

# Allow running `pytest` from the project root without extra path configuration.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agent.ticket_triage_agent import analyze_ticket


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_login_problem():
    result = analyze_ticket("I forgot my password and cannot login.")
    assert result["category"] == "Account/Login"
    assert result["priority"] == "Normal"
    assert result["escalation"] != "Immediate"


def test_billing_problem():
    result = analyze_ticket("I was charged incorrectly for my subscription.")
    assert result["category"] == "Billing"
    assert result["priority"] == "Normal"


def test_feature_request():
    result = analyze_ticket("Can you please add dark mode?")
    assert result["category"] == "Feature Request"
    assert result["priority"] == "Normal"


def test_bug():
    result = analyze_ticket("The application crashes whenever I upload a PDF.")
    assert result["category"] == "Bug"
    assert result["priority"] in ("High", "Normal")


def test_widespread_outage():
    result = analyze_ticket(
        "Nobody in our organization can access the platform. "
        "The service is down for everyone."
    )
    assert result["category"] == "Service Outage"
    assert result["priority"] == "Critical"
    assert result["escalation"] == "Immediate"


def test_security_data_breach():
    result = analyze_ticket(
        "We believe our account has been hacked and customer data may have been exposed."
    )
    assert result["category"] == "Legal/Security"
    assert result["priority"] == "Critical"
    assert result["escalation"] == "Immediate"


def test_unclear_ticket():
    result = analyze_ticket("Hello, I need help.")
    assert result["category"] == "Unknown"
    assert result["escalation"] == "Human Review Required"
