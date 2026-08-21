# PLUMA

**Local voice + screen-aware Windows 11 agent.**

Smart when active. Featherweight when idle.

## Engineering philosophy

PLUMA is a Windows control system with a replaceable local reasoning layer,
not a chatbot that controls Windows. It accepts voice or text commands, inspects
the active screen when required, executes through deterministic typed tools,
verifies every state change, records exactly what happened, and returns heavy
components to an idle state after use.

## Build status

Phase 0 — contracts and benchmark harness.

## Requirements

- Windows 11
- Python 3.12+
- See `requirements.txt` (runtime) and `requirements-dev.txt` (dev/test)

## Quick start (development)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
pytest
```

## Repository structure

See `PLUMA_MASTER_SPEC.md` §19 for the authoritative module map.

## Specification

- `PLUMA_MASTER_SPEC.md` — authoritative product and engineering specification
- `PLUMA_BUILD_PLAN.md` — ordered implementation phases
- `PLUMA_ACCEPTANCE_TESTS.md` — release gates
- `PLUMA_TECH_STACK.md` — technology contract
- `AGENTS.md` — safety and architecture contract for coding agents
