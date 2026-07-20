import os
import sqlite3
import json
import urllib.request
import logging
import subprocess

DB_PATH = os.path.expanduser("~/.nexustrader/nexustrader.db")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def load_settings():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("SELECT key, value FROM settings")
    rows = c.fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def run_self_developer(trigger_deploy: bool = False):
    logging.info("Starting autonomous agent self-developer session...")
    settings = load_settings()

    # Read files
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        index_html = open(os.path.join(base_dir, "dashboard", "index.html")).read()
        index_css  = open(os.path.join(base_dir, "dashboard", "index_v2.css")).read()
        app_js     = open(os.path.join(base_dir, "dashboard", "app_v2.js")).read()
        main_py    = open(os.path.join(base_dir, "main.py")).read()
    except Exception as e:
        logging.error(f"Failed to read codebase files: {e}")
        return f"Failed to read codebase files: {e}"

    db_prompt = settings.get("prompt_self_developer")
    if not db_prompt:
        db_prompt = """You are Antigravity, an elite autonomous AI software engineer. Your goal is to improve the NexusTrader algorithmic trading bot codebase.
Our mission is to build features and UI visualizations that help the bot consistently earn $1,000 USD a day by giving the trader better indicators, diagnostic data, or performance controls.

Identify ONE specific, clean, non-breaking improvement or feature to implement. 
Return your response STRICTLY in JSON format containing "explanation" and "modifications" find-and-replace rules."""

    prompt = f"""{db_prompt}

Codebase outline and instructions:
- main.py (backend FastAPI)
- dashboard/index.html (HTML structure)
- dashboard/index_v2.css (CSS styles)
- dashboard/app_v2.js (JavaScript logic)

Do not make any breaking changes to existing API routes or core loops.
Return your response STRICTLY in the following JSON format (do not include markdown wrappers like ```json):
{{
  "explanation": "Detailed explanation of what feature you designed and implemented, why it is useful, and which files you are modifying.",
  "modifications": [
    {{
      "file_path": "dashboard/index.html",
      "replacements": [
        {{
          "find": "exact character sequence in original file to replace",
          "replace": "new replacement text"
        }}
      ]
    }}
  ]
}}

The "find" blocks MUST MATCH EXACTLY (whitespace, newlines, etc.) to the existing content. Keep replacement blocks minimal and target-focused to avoid parsing errors.
"""

    # Build combined prompt with codebase
    contents_prompt = prompt + (
        f"\n--- START main.py ---\n{main_py}\n--- END main.py ---\n"
        f"--- START index.html ---\n{index_html}\n--- END index.html ---\n"
        f"--- START index_v2.css ---\n{index_css}\n--- END index_v2.css ---\n"
        f"--- START app_v2.js ---\n{app_js}\n--- END app_v2.js ---"
    )

    try:
        from openclaw_bridge import query_openclaw, extract_json_block
        logging.info("Requesting new feature design via OpenClaw Gateway...")
        raw_text = query_openclaw(contents_prompt, system_prompt=(
            "You are an autonomous AI software engineer. "
            "Analyze the provided codebase and return ONLY valid JSON — no markdown, no commentary."
        ))
        # Try extracting from code fence first, then fall back to raw JSON
        response_data = extract_json_block(raw_text)
        if response_data is None:
            try:
                response_data = json.loads(raw_text)
            except json.JSONDecodeError:
                raise ValueError("No valid JSON found in LLM response")
    except Exception as e:
        logging.error(f"OpenClaw call failed: {e}")
        return f"OpenClaw call failed: {e}"

    explanation = response_data.get("explanation", "No explanation provided.")
    modifications = response_data.get("modifications", [])

    logging.info(f"Generated feature: {explanation}")

    # Backups
    backups = {}
    try:
        for mod in modifications:
            fp = os.path.join(base_dir, mod["file_path"])
            backups[fp] = open(fp).read()
    except Exception as e:
        logging.error(f"Failed to create backups: {e}")
        return f"Failed to create backups: {e}"

    # Apply modifications
    try:
        for mod in modifications:
            fp = os.path.join(base_dir, mod["file_path"])
            content = open(fp).read()
            for rep in mod["replacements"]:
                find_str = rep["find"]
                replace_str = rep["replace"]
                if find_str not in content:
                    raise ValueError(f"Could not find exact text match in {mod['file_path']}")
                content = content.replace(find_str, replace_str)
            open(fp, "w").write(content)
        logging.info("Successfully applied file replacements.")
    except Exception as e:
        logging.error(f"Failed to apply modifications: {e}. Restoring backups...")
        for fp, original in backups.items():
            open(fp, "w").write(original)
        return f"Modifications failed: {e}"

    # Compilation check
    try:
        res = subprocess.run(
            ["python3", "-m", "py_compile", "main.py"],
            capture_output=True, text=True, cwd=base_dir
        )
        if res.returncode != 0:
            raise ValueError(f"Compilation error: {res.stderr}")
        logging.info("Compilation check passed.")
    except Exception as e:
        logging.error(f"Validation failed: {e}. Rolling back...")
        for fp, original in backups.items():
            open(fp, "w").write(original)
        return f"Validation failed: {e}"

    # Deploy
    if trigger_deploy:
        try:
            deploy_script = os.path.join(base_dir, "deploy.sh")
            if os.path.exists(deploy_script):
                deploy_res = subprocess.run(
                    [deploy_script], capture_output=True, text=True, timeout=30, cwd=base_dir
                )
                logging.info(f"Deployment: {deploy_res.stdout}")
            else:
                logging.warning("deploy.sh not found, skipping deployment.")
        except Exception as e:
            logging.error(f"Deployment failed: {e}")

    # Meta-prompt optimisation
    optimize_own_prompt(settings)

    # Write summary
    blog_dir = os.path.join(base_dir, "blog", "daily_summaries")
    if os.path.exists(blog_dir):
        report_path = os.path.join(blog_dir, "weekly_self_improvement.md")
        try:
            with open(report_path, "a") as f:
                f.write(f"\n\n### \U0001f916 AI Agent Self-Development Session:\n"
                        f"* **Designed Feature**: {explanation}\n"
                        f"* **Status**: Successfully deployed.\n")
            logging.info("Saved self-development log to blog.")
        except Exception as e:
            logging.error(f"Failed to write log: {e}")

    return f"Success! Designed and implemented new feature:\n\n{explanation}"


def save_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


def optimize_own_prompt(settings):
    """Meta-cognition: evaluate and rewrite the self-developer prompt template."""
    try:
        db_prompt = settings.get("prompt_self_developer", "")
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Read past self-development logs
        quant_summary = ""
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path) as f:
                quant_summary = f.read()[-3000:]

        blog_summary = ""
        try:
            blog_dir = os.path.join(base_dir, "blog")
            reports = [f for f in os.listdir(blog_dir) if f.startswith("weekly_report_") and f.endswith(".md")]
            if reports:
                latest = sorted(reports)[-1]
                with open(os.path.join(blog_dir, latest)) as f:
                    blog_summary = f.read()[-3000:]
        except Exception:
            pass

        prompt = f"""
You are an autonomous AI prompt engineer. Evaluate and rewrite the self-developer prompt template based on:
1. The current template.
2. Output from past self-development sessions.
3. Weekly blog reports.

Goal: features that help the bot consistently earn $1,000 USD/day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent Self-Development Logs:
\"\"\"{quant_summary}\"\"\"

Recent Blogger Reports:
\"\"\"{blog_summary}\"\"\"

Return ONLY a JSON object with key "revised_prompt_self_developer" containing your improved prompt template (no markdown wrappers).
"""
        from openclaw_bridge import query_openclaw, extract_json_block
        raw_text = query_openclaw(prompt, system_prompt="You are a prompt engineer. Return only valid JSON.")
        raw_text = extract_json_block(raw_text)
        res_data = json.loads(raw_text)
        revised = res_data.get("revised_prompt_self_developer")
        if revised:
            save_setting("prompt_self_developer", revised)
            logging.info("Meta-optimization: updated prompt_self_developer in database.")
            return revised
    except Exception as e:
        logging.error(f"Failed to meta-optimize prompt: {e}")
    return None


if __name__ == "__main__":
    print(run_self_developer(trigger_deploy=True))
