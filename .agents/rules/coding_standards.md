---
name: Workspace Coding & Agentic Standards
description: Enforces test-driven development, clean code quality, diagnostic logging, and proxy routing in sandboxed environments.
always_on: true
---

# 🤖 Workspace AI Coding & Agentic Standards

All agents working on this codebase (including Antigravity, openclaw, and downstream subagents) **MUST** strictly adhere to these development standards.

---

## 1. Test-Driven Development (TDD) Required
* **100% Test Coverage for Edits**: Any new feature, API endpoint, mathematical optimization module, or helper function **MUST** include corresponding unit tests.
* **Test Verification**: Prior to completing any coding cycle or deploy, the agent must run the local test runner for this repository.
* **Correctness Gate**: Build failures or failing unit tests are strictly unacceptable. Do not finalize code changes until all unit tests return a clean pass.

---

## 2. Agentic Self-Healing & Diagnostic Logging
* **Self-Healing Mechanics**: When a runtime exception or API error is identified:
  - Log details with system category prefixes (e.g., `[ERROR]`, `[SYNC]`, etc.).
  - Leverage automated diagnostic routines or self-developer loops to trigger corrections.

---

## 3. Commit & Deploy Discipline
* **Atomic Commits**: One logical change per commit with a descriptive message.
* **Push Before Handoff**: Always push working changes to GitHub before yielding to another agent or ending a session.
* **Deploy via Script**: Use the repository's `deploy.sh` for production deployments — it enforces unit tests and restarts the systemd service cleanly.
