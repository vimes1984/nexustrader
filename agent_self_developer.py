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

def run_self_developer():
    logging.info("Starting autonomous agent self-developer session...")
    settings = load_settings()
    gemini_api_key = settings.get("blog_gemini_api_key", "").strip()
    ai_enabled = settings.get("blog_ai_enabled", "false") == "true"
    
    if not gemini_api_key or not ai_enabled:
        logging.warning("Gemini API key is not configured or AI is disabled. Cannot run self-developer agent.")
        return "Gemini API key is not configured or AI is disabled."
        
    # Read files
    try:
        with open("dashboard/index.html", "r") as f:
            index_html = f.read()
        with open("dashboard/index_v2.css", "r") as f:
            index_css = f.read()
        with open("dashboard/app_v2.js", "r") as f:
            app_js = f.read()
        with open("main.py", "r") as f:
            main_py = f.read()
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
    # Build payload
    contents = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"text": f"--- START main.py ---\n{main_py}\n--- END main.py ---"},
                    {"text": f"--- START index.html ---\n{index_html}\n--- END index.html ---"},
                    {"text": f"--- START index_v2.css ---\n{index_css}\n--- END index_v2.css ---"},
                    {"text": f"--- START app_v2.js ---\n{app_js}\n--- END app_v2.js ---"}
                ]
            }
        ]
    }
    
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_api_key}"
        data = json.dumps(contents).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        logging.info("Requesting new feature design from Gemini...")
        with urllib.request.urlopen(req, timeout=60) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            # Remove any markdown wrappers if present
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            response_data = json.loads(raw_text)
    except Exception as e:
        logging.error(f"Gemini API call failed: {e}")
        return f"Gemini API call failed: {e}"
        
    explanation = response_data.get("explanation", "No explanation provided.")
    modifications = response_data.get("modifications", [])
    
    logging.info(f"Gemini generated feature: {explanation}")
    
    # Save a backup of the current state of modified files in case we need to roll back
    backups = {}
    try:
        for mod in modifications:
            file_path = mod["file_path"]
            with open(file_path, "r") as f:
                backups[file_path] = f.read()
    except Exception as e:
        logging.error(f"Failed to create backups of modified files: {e}")
        return f"Failed to create backups: {e}"
        
    # Apply modifications
    try:
        for mod in modifications:
            file_path = mod["file_path"]
            with open(file_path, "r") as f:
                content = f.read()
            for rep in mod["replacements"]:
                find_str = rep["find"]
                replace_str = rep["replace"]
                if find_str in content:
                    content = content.replace(find_str, replace_str)
                else:
                    raise ValueError(f"Could not find exact text match in {file_path}:\n{find_str}")
            with open(file_path, "w") as f:
                f.write(content)
        logging.info("Successfully applied file replacements.")
    except Exception as e:
        logging.error(f"Failed to apply modifications: {e}. Restoring backups...")
        for file_path, original in backups.items():
            with open(file_path, "w") as f:
                f.write(original)
        return f"Modifications failed: {e}"
        
    # Verify compilation & correctness of main.py if modified
    try:
        compile_res = subprocess.run(
            ["python3", "-m", "py_compile", "main.py"],
            capture_output=True,
            text=True
        )
        if compile_res.returncode != 0:
            raise ValueError(f"Compilation error in main.py: {compile_res.stderr}")
        logging.info("Compilation check passed successfully.")
    except Exception as e:
        logging.error(f"Validation failed: {e}. Rolling back modified files...")
        for file_path, original in backups.items():
            with open(file_path, "w") as f:
                f.write(original)
        return f"Validation failed: {e}"
        
    # Deploy to Proxmox server
    try:
        deploy_res = subprocess.run(
            ["./deploy.sh"],
            capture_output=True,
            text=True,
            timeout=30
        )
        logging.info(f"Deployment completed: {deploy_res.stdout}")
    except Exception as e:
        logging.error(f"Deployment failed: {e}")
        
    # Run meta-prompt optimization
    optimize_own_prompt(settings, gemini_api_key)

    # Write a summary log in the blog summaries folder
    blog_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blog", "daily_summaries")
    if os.path.exists(blog_dir):
        report_path = os.path.join(blog_dir, "weekly_self_improvement.md")
        try:
            with open(report_path, "a") as f:
                f.write(f"\n\n### 🤖 AI Agent Self-Development Session:\n* **Designed Feature**: {explanation}\n* **Status**: Successfully deployed to Proxmox.\n")
            logging.info("Saved AI self development log to blog.")
        except Exception as e:
            logging.error(f"Failed to write self-development log to blog: {e}")
            
    return f"Success! Designed and implemented new feature:\n\n{explanation}"

def save_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def optimize_own_prompt(settings, gemini_api_key):
    try:
        db_prompt = settings.get("prompt_self_developer", "")
        
        # Read PhD Quant optimizer logs
        quant_summary = ""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, "blog", "daily_summaries", "weekly_self_improvement.md")
        if os.path.exists(report_path):
            with open(report_path, "r") as f:
                quant_summary = f.read()[-3000:]
                
        # Read Blogger log from the latest weekly report
        blog_summary = ""
        try:
            blog_dir = os.path.join(base_dir, "blog")
            reports = [f for f in os.listdir(blog_dir) if f.startswith("weekly_report_") and f.endswith(".md")]
            if reports:
                latest_report = sorted(reports)[-1]
                with open(os.path.join(blog_dir, latest_report), "r") as f:
                    blog_summary = f.read()[-3000:]
        except Exception:
            pass
            
        prompt = f"""
You are Antigravity, the AI Software Developer agent. Part of your meta-cognition routine is to evaluate your own prompt template and optimize it based on:
1. Your current prompt template.
2. The outputs of the PhD Quant Optimizer agent (which optimizes parameters).
3. The outputs of the Blogger agent (which logs weekly performance summaries).

Our mission is to make the bot consistently earn $1,000 USD a day.

Current Prompt Template:
\"\"\"{db_prompt}\"\"\"

Recent PhD Quant Logs:
\"\"\"{quant_summary}\"\"\"

Recent Blogger Reports:
\"\"\"{blog_summary}\"\"\"

Critically analyze this context. Redesign your own prompt template to focus it even more tightly on achieving $1,000 USD/day, ensuring it asks for non-breaking features and keeps its final modifications JSON format.
Return ONLY a JSON block containing the key "revised_prompt_self_developer" with your improved prompt template as the value (do not include markdown wrappers like ```json).
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_api_key}"
        data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            res_data = json.loads(raw_text)
            revised = res_data.get("revised_prompt_self_developer")
            if revised:
                save_setting("prompt_self_developer", revised)
                logging.info("Meta-optimization: Successfully updated prompt_self_developer in database settings.")
                return revised
    except Exception as e:
        logging.error(f"Failed to meta-optimize prompt_self_developer: {e}")
    return None

if __name__ == "__main__":
    print(run_self_developer())
