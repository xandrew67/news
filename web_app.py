"""
AU News Review Web App
Browse, edit, and approve X posts before publishing.

Usage:
    python web_app.py          # http://localhost:8080
    python main.py --serve     # equivalent
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from agents.pre_post_review_edit_publish import PrePostReviewEditPublish

load_dotenv()

app = Flask(__name__, template_folder="templates")
queue = PrePostReviewEditPublish()

logger = logging.getLogger(__name__)

# ── Pipeline run state ────────────────────────────────────────────────────────

_run_state: dict = {"status": "idle", "last_run": None, "error": None}
_run_lock = threading.Lock()


def _run_pipeline() -> None:
    global _run_state
    try:
        from agents.orchestrator import Orchestrator
        orch = Orchestrator()
        posts = orch.run_once()
        with _run_lock:
            _run_state = {
                "status": "idle",
                "last_run": datetime.utcnow().isoformat(),
                "error": None,
                "added": len(posts),
            }
        logger.info("Pipeline run complete — %d posts queued", len(posts))
    except Exception as exc:
        logger.error("Pipeline run failed: %s", exc, exc_info=True)
        with _run_lock:
            _run_state = {
                "status": "idle",
                "last_run": datetime.utcnow().isoformat(),
                "error": str(exc),
                "added": 0,
            }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/posts")
def get_posts():
    status = request.args.get("status", "all")
    items = queue.get_all() if status == "all" else queue.get_by_status(status)
    return jsonify(sorted(items, key=lambda x: x["score"], reverse=True))


@app.get("/api/run/status")
def run_status():
    with _run_lock:
        return jsonify(_run_state)


@app.post("/api/run")
def run_pipeline():
    with _run_lock:
        if _run_state["status"] == "running":
            return jsonify({"ok": False, "error": "Pipeline already running"}), 409
        import urllib.request
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        try:
            urllib.request.urlopen(ollama_url, timeout=2)
        except Exception:
            return jsonify({"ok": False, "error": f"Ollama not reachable at {ollama_url}"}), 400
        _run_state["status"] = "running"
        _run_state["error"] = None

    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()
    return jsonify({"ok": True})


@app.post("/api/posts/<item_id>/approve")
def approve(item_id: str):
    data = request.get_json(silent=True) or {}
    final_text = data.get("text") or None
    ok = queue.approve(item_id, final_text)
    return jsonify({"ok": ok})


@app.post("/api/posts/<item_id>/reject")
def reject(item_id: str):
    ok = queue.reject(item_id)
    return jsonify({"ok": ok})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    Path("output").mkdir(exist_ok=True)
    print(f" * Review UI: http://localhost:{args.port}")
    app.run(debug=False, port=args.port, host=args.host)
