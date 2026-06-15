#!/usr/bin/env python3
"""
AU News Intelligence Agent — Main entrypoint

Usage:
    python main.py            # Run pipeline once, queue posts for review
    python main.py --loop     # Run pipeline continuously on schedule
    python main.py --serve    # Start the post review web UI (http://localhost:5000)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env file before anything else
load_dotenv()


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quieten noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="AU News Intelligence Agent")
    parser.add_argument("--loop", action="store_true",
                        help="Run continuously on a schedule")
    parser.add_argument("--serve", action="store_true",
                        help="Start the post review web UI on port 5000")
    parser.add_argument("--port", type=int, default=5000,
                        help="Port for the review web UI (default: 5000)")
    parser.add_argument("--settings", default="config/settings.yaml",
                        help="Path to settings YAML")
    parser.add_argument("--feeds", default="config/feeds.yaml",
                        help="Path to feeds YAML")
    parser.add_argument("--log-level", default=None,
                        help="Override log level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    # Determine log level
    log_level = args.log_level or os.environ.get("LOG_LEVEL", "INFO")
    setup_logging(log_level)
    logger = logging.getLogger("main")

    # Ensure output directory exists
    Path("output").mkdir(exist_ok=True)

    # --serve: start the review web UI (no API key required)
    if args.serve:
        from web_app import app
        logger.info("Starting review web UI on http://localhost:%d", args.port)
        app.run(debug=False, port=args.port, host="0.0.0.0")
        return

    # Verify Ollama is reachable
    import urllib.request
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        urllib.request.urlopen(ollama_url, timeout=3)
    except Exception:
        logger.error("Ollama is not reachable at %s — is it running?", ollama_url)
        sys.exit(1)

    from agents.orchestrator import Orchestrator

    orchestrator = Orchestrator(
        settings_path=args.settings,
        feeds_path=args.feeds,
    )

    if args.loop:
        logger.info("Starting in loop mode")
        orchestrator.run_loop()
    else:
        logger.info("Running single pipeline pass")
        posts = orchestrator.run_once()
        if posts:
            print("\n" + "=" * 60)
            print(f"Generated {len(posts)} X post(s) — open the review UI to approve:")
            print(f"  python main.py --serve")
            print("=" * 60)
            for i, post in enumerate(posts, 1):
                print(f"\n[{i}] Score: {post.score:.1f} | Source: {post.source_name}")
                print(f"    {post.text}")
        else:
            print("\nNo newsworthy posts generated this run.")


if __name__ == "__main__":
    main()
