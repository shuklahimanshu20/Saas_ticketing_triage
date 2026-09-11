# AI Ticket Triage Agent

A browser-based AI Agent that triages incoming customer support tickets for a SaaS
company: it categorizes each ticket, sets a priority, decides whether it needs
**immediate escalation**, assigns a team, and explains its reasoning with a
confidence score - flagging anything it can't confidently classify for **human
review** instead of guessing.

This is a single, independent agent built for an assignment. It is **not** an
end-to-end support platform and does **not** perform workflow orchestration or
connect to any real company system (billing, engineering ticketing, CRM, etc.).
All team names and sample tickets are mock data for demonstration purposes.

---

## 1. What problem does this Agent solve?

SaaS support teams receive a constant stream of tickets that must be triaged
quickly. A handful of them - live outages, security incidents, data breaches,
legal issues - need to bypass the normal queue and get immediate attention.
Manually reading and routing every ticket is slow and error-prone. This Agent
automates the *first, highest-leverage* decision in that pipeline: read the
ticket, understand it, and decide what should happen to it next.

## 2. Why is this an "Agent" and not just a classifier script?

It perceives an input (the raw ticket text), reasons about it against a fixed
policy (the categories, priorities, and the critical escalation rule), and
autonomously decides an outcome (category, priority, escalation, team,
confidence) - all without a human in the loop for the initial triage step. It
also knows the boundary of its own competence: when it isn't confident, it
deliberately abstains from guessing and routes the ticket to **Human Review
Required** rather than fabricating an answer. That combination - autonomous
decision-making plus a built-in refusal path - is what makes it an agent rather
than a plain if/else script.

## 3. How the Agent works

1. The Streamlit UI collects the ticket text and passes it to
   `agent.ticket_triage_agent.analyze_ticket()`.
2. If `ANTHROPIC_API_KEY` is set, the Agent sends the ticket to the Anthropic
   Claude API with a strict prompt asking for a JSON verdict constrained to the
   allowed categories/priorities/escalation states.
3. The LLM's JSON response is **validated** (correct keys, allowed enum values,
   confidence in range) before it is ever shown to the user. If validation
   fails, or the API call errors for any reason, the Agent automatically falls
   back to a deterministic **DEMO/MOCK** classifier instead of crashing or
   showing garbage.
4. If no API key is configured at all, the Agent runs entirely in DEMO/MOCK
   mode from the start, and the UI clearly labels this so no one mistakes mock
   output for a real model call.
5. A hard-coded safety rule always forces `priority = Critical` and
   `escalation = Immediate` for `Service Outage` / `Legal/Security` categories,
   even if the LLM's own answer was inconsistent - the critical escalation rule
   is never left entirely to model judgment.

## 4. Architecture

```
Streamlit UI (app.py)
        │
        ▼
agent/ticket_triage_agent.py   <-- all business logic lives here, no Streamlit imports
        │
        ├── ANTHROPIC_API_KEY set?  ── yes ──► Anthropic Claude API ──► validate response
        │                                                                 │
        │                                                            (on failure)
        │                                                                 ▼
        └── no / failure ─────────────────────────────────────► rule-based mock classifier
```

The UI layer and the agent/LLM logic are fully separate: `app.py` only renders
widgets and calls `analyze_ticket()`; it contains no classification rules and
never touches the API key directly.

## 5. Project structure

```
ticket-triage-agent/
│
├── app.py                          # Streamlit browser UI
├── agent/
│   ├── __init__.py
│   └── ticket_triage_agent.py      # Core agent logic (LLM + mock + validation)
├── data/
│   └── sample_tickets.json         # The 7 sample tickets used by the UI and tests
├── tests/
│   └── test_triage.py              # pytest suite for the 7 required test cases
├── .env.example                    # Template for ANTHROPIC_API_KEY
├── requirements.txt
└── README.md
```

## 6. Installation

From inside the `ticket-triage-agent` folder:

```bash
pip install -r requirements.txt
```

## 7. Configuring the API key

The Agent reads the key from the `ANTHROPIC_API_KEY` environment variable. It
is **never hard-coded** anywhere in the source.

Option A - `.env` file (recommended for local development):

```bash
cp .env.example .env
# then edit .env and paste your real key
```

Option B - set it directly in your shell for the current session:

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "your_api_key_here"

# macOS/Linux
export ANTHROPIC_API_KEY="your_api_key_here"
```

If no key is present, the app automatically and visibly runs in **DEMO/MOCK
mode** using a deterministic rule-based classifier - it is always usable and
demonstrable without any API key or cost.

## 8. Running the browser application

```bash
streamlit run app.py
```

Streamlit will print a local URL (typically `http://localhost:8501`) - open
that in your browser.

## 9 & 10. Example tickets and expected outputs

| Sample | Ticket text | Expected category | Expected priority | Expected escalation |
|---|---|---|---|---|
| Login problem | "I forgot my password and cannot login." | Account/Login | Normal | Standard |
| Billing problem | "I was charged incorrectly for my subscription." | Billing | Normal | Standard |
| Feature request | "Can you please add dark mode?" | Feature Request | Normal | Standard |
| Bug | "The application crashes whenever I upload a PDF." | Bug | Normal/High | Standard |
| Widespread outage | "Nobody in our organization can access the platform. The service is down for everyone." | Service Outage | Critical | **Immediate** |
| Security/data breach | "We believe our account has been hacked and customer data may have been exposed." | Legal/Security | Critical | **Immediate** |
| Unclear ticket | "Hello, I need help." | Unknown | Normal | **Human Review Required** |

All seven are pre-loaded via the "Load Sample Ticket" buttons in the UI and
also covered by the automated test suite.

## 11. Escalation logic

If the ticket text indicates any of: a live service outage, widespread system
failure, a legal issue, a security issue, a data breach, or hacking, the Agent
**always** sets `priority = Critical` and `escalation = Immediate`, and the UI
shows a prominent red "🚨 IMMEDIATE ESCALATION" banner along with the reason.
This rule is enforced in code (`_validate_response`) even when using the live
LLM, so a borderline or inconsistent model answer cannot silently skip it.

## 12. Human review logic

If the Agent cannot confidently classify a ticket - the text is too vague,
empty, or doesn't match any recognizable pattern - it sets
`category = Unknown` and `escalation = Human Review Required` with a low
confidence score, and the UI shows a clear amber warning banner. The Agent
never fabricates a category or reason it isn't confident about.

## 13. Running the tests

```bash
pytest
```

The tests force DEMO/MOCK mode (by clearing `ANTHROPIC_API_KEY`) so they are
deterministic, free, and don't require network access. They cover the 7
required test cases from the assignment spec.

## 14. AI tools used to build this project

This project was built with **Claude Code** (Anthropic), using the Claude
Sonnet 5 model, based on a detailed specification provided by the developer.
Claude Code was used to scaffold the project structure, write the agent logic,
the Streamlit UI, the test suite, and this README.

## 15. What was manually reviewed or modified

- The keyword rule-set in the mock classifier was reviewed against all 7
  required test cases to confirm each one resolves to the expected category,
  priority, and escalation.
- The critical escalation rule was deliberately hard-coded as a
  non-overridable safety check in `_validate_response`, rather than trusted
  entirely to LLM output, so it holds even in live mode.
- The `.env.example` and README's "no API key" guidance were checked against
  the actual `analyze_ticket()` fallback behavior to ensure the DEMO/MOCK
  label in the UI accurately reflects what's happening under the hood.
