"""
Launcher script for XAUUSD Scalping M5 Secret System WebApp.
Checks dependencies, starts the FastAPI server, and opens the browser.
"""

import os
import sys
import webbrowser
import subprocess
import time

try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

def main():
    print("===================================================================")
    print(" 🚀 Starting XAUUSD Scalping M5 Secret System WebApp")
    print("===================================================================")

    # Change working directory to this script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Launch uvicorn
    import uvicorn
    import json

    config_path = os.path.join(script_dir, "config.json")
    host = "0.0.0.0"
    port = 8000
    default_token = "GOLD_VIP_2026"

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                host = cfg.get("server", {}).get("host", "0.0.0.0")
                port = cfg.get("server", {}).get("port", 8000)
                tokens = cfg.get("auth", {}).get("access_tokens", ["GOLD_VIP_2026"])
                if tokens:
                    default_token = tokens[0]
        except Exception:
            pass

    url = f"http://{host}:{port}"
    print(f"\n🌐 WebApp Dashboard URL: {url}")
    print(f"🔑 Access Token: {default_token}\n")

    from main import app
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
