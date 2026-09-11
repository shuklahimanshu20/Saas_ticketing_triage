"""
AI Ticket Triage Agent - Streamlit browser UI.

This file only handles presentation. All classification logic lives in
agent/ticket_triage_agent.py so the agent stays independently testable and the
LLM integration stays out of the UI layer.

Run with:  streamlit run app.py
"""

import os

import streamlit as st
from dotenv import load_dotenv

from agent.ticket_triage_agent import analyze_ticket

# Loads ANTHROPIC_API_KEY (and any other vars) from a local .env file if present.
# Has no effect if .env doesn't exist - the app still works via real env vars or
# falls back to DEMO/MOCK mode.
load_dotenv()

with open(
    os.path.join(os.path.dirname(__file__), "data", "sample_tickets.json"),
    "r",
    encoding="utf-8",
) as f:
    import json

    SAMPLE_TICKETS = json.load(f)

st.set_page_config(page_title="AI Ticket Triage Agent", page_icon="🎫", layout="centered")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🎫 AI Ticket Triage Agent")
st.write(
    "This Agent reads a customer support ticket, categorizes it, determines its "
    "priority, decides whether it needs **immediate escalation**, assigns it to a "
    "team, and explains its reasoning with a confidence score. If it cannot "
    "confidently classify a ticket, it flags it for **Human Review** instead of "
    "guessing."
)
st.caption(
    "Scope note: this is a single, independent triage agent built for demonstration. "
    "It does not connect to any real billing, engineering, or support system - all "
    "team assignment is illustrative, and sample data is mocked."
)

api_key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
if api_key_present:
    st.success("Mode: **LIVE** - using the Anthropic Claude API for classification.")
else:
    st.warning(
        "Mode: **DEMO / MOCK** - no ANTHROPIC_API_KEY environment variable was found. "
        "Results below come from a deterministic rule-based demo classifier, "
        "NOT a live LLM call. Set ANTHROPIC_API_KEY to enable live classification."
    )

st.divider()

# ---------------------------------------------------------------------------
# Load Sample Ticket
# ---------------------------------------------------------------------------
st.subheader("Load Sample Ticket")

if "ticket_text" not in st.session_state:
    st.session_state.ticket_text = ""

sample_cols = st.columns(4)
for i, sample in enumerate(SAMPLE_TICKETS):
    col = sample_cols[i % 4]
    if col.button(sample["label"], use_container_width=True):
        st.session_state.ticket_text = sample["text"]

st.divider()

# ---------------------------------------------------------------------------
# Ticket input
# ---------------------------------------------------------------------------
st.subheader("Enter customer ticket")
ticket_text = st.text_area(
    label="Enter customer ticket",
    height=180,
    label_visibility="collapsed",
    placeholder="Paste or type the customer's support ticket here...",
    key="ticket_text",
)

analyze_clicked = st.button("Analyze Ticket", type="primary")

# ---------------------------------------------------------------------------
# Analysis + results
# ---------------------------------------------------------------------------
if analyze_clicked:
    if not ticket_text or not ticket_text.strip():
        st.error("Please enter a ticket, or load a sample, before analyzing.")
    else:
        try:
            with st.spinner("Analyzing ticket..."):
                result = analyze_ticket(ticket_text)
            st.session_state.last_result = result
        except Exception as exc:
            st.error(f"Something went wrong while analyzing the ticket: {exc}")
            st.session_state.last_result = None

if st.session_state.get("last_result"):
    result = st.session_state.last_result

    if result["escalation"] == "Immediate":
        st.error(f"IMMEDIATE ESCALATION\n\n{result['reason']}", icon="🚨")
    elif result["escalation"] == "Human Review Required":
        st.warning(f"Human Review Required\n\n{result['reason']}", icon="⚠️")

    st.subheader("Triage Result")
    col1, col2, col3 = st.columns(3)
    col1.metric("Category", result["category"])
    col2.metric("Priority", result["priority"])
    col3.metric("Escalation", result["escalation"])

    col4, col5 = st.columns(2)
    col4.metric("Assigned Team", result["assigned_team"])
    col5.metric("Confidence", f"{result['confidence']:.0%}")

    st.markdown(f"**Reason:** {result['reason']}")

    mode_label = "Live LLM (Anthropic Claude)" if result.get("mode") == "llm" else "Demo/Mock classifier"
    st.caption(f"Classification source: {mode_label}")

    with st.expander("Agent Raw Output"):
        st.json(result)
