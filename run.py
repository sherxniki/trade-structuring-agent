"""Start the Streamlit app on the port the platform provides (default 8080)."""

import os
import sys

port = os.environ.get("PORT", "8080")
args = [
    sys.executable, "-m", "streamlit", "run", "app.py",
    "--server.port", port,
    "--server.address", "0.0.0.0",
    "--server.headless", "true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--browser.gatherUsageStats", "false",
    "--client.toolbarMode", "minimal",
    "--theme.base", "light",
    "--theme.primaryColor", "#2563eb",
]
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.execv(sys.executable, args)
