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

## 3. Sandboxed LLM API Key Routing (The Antigravity Key Rule)
* **Antigravity Key Prefix**: Sandbox API keys start with `AQ.` (Antigravity context-bound keys). Sending requests containing these keys directly to standard Vertex AI or Generative Language endpoints will fail.
* **Proxy Requirement**: Route all LLM calls locally through the `antigravity_proxy` daemon on port `8001` (`http://127.0.0.1:8001/v1`).
* **Routing Check**: Always check if the proxy is running before routing LLM calls, and start it if offline.
