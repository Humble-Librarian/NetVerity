"""Lightweight HTTP API Server connecting the NetVerity UI to the Python backend."""

from __future__ import annotations

import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.agent import HybridDiagnosticAgent
from app.evidence import Evidence, EvidenceSource
from app.prolog_engine import PrologEngine
from app.search_engine import DiagnosticSearchEngine
from app.simulator import NetworkEnvironment, Scenario
from app.state import DiagnosticState
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("netverity.server")


class NetVerityAPIHandler(SimpleHTTPRequestHandler):
    """Serves UI files and provides /api/diagnose and /api/infer endpoints."""

    def __init__(self, *args, **kwargs):
        ui_dir = Path(__file__).resolve().parent.parent / "ui"
        super().__init__(*args, directory=str(ui_dir), **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/diagnose":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8")
                
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self.send_error_response(400, "Bad Request: Invalid JSON")
                    return
                
                user_symptoms = data.get("user_symptoms", "")
                env_data = data.get("environment", {})
                
                if not isinstance(env_data, dict):
                    logger.error("Environment is not a dictionary.")
                    self.send_error_response(400, "Bad Request: environment must be an object")
                    return

                injected_user_evidence = data.get("user_evidence", {})

                # Create environment & state
                env = NetworkEnvironment.from_dict(env_data)
                scenario = Scenario(
                    scenario_id="custom_user_session",
                    name="Custom User Diagnosis",
                    description="Dynamically generated from user input",
                    initial_user_symptoms=user_symptoms,
                    environment=env,
                    ground_truth_fault="",
                )

                logger.info("Running diagnostic agent for custom user session...")
                agent = HybridDiagnosticAgent()
                result = agent.diagnose_scenario(scenario)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result.to_dict()).encode("utf-8"))
                logger.info("Diagnosis completed successfully.")
            except Exception as e:
                logger.exception(f"Internal server error: {e}")
                self.send_error_response(500, f"Internal Server Error: {str(e)}")
            return

        super().do_POST()
        
    def send_error_response(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def run_server(port: int = 3000):
    server = HTTPServer(("0.0.0.0", port), NetVerityAPIHandler)
    logger.info(f"NetVerity Server running at http://localhost:{port}")
    print(f"NetVerity Server running at http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
