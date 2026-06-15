.PHONY: build run run-once run-local install dev test lint logs clean help

# ── Variables ──────────────────────────────────────────────────────────────────
IMAGE_NAME   := au-news-agent
CONTAINER    := au-news-agent
PYTHON       := python3

# ── Docker commands ────────────────────────────────────────────────────────────

build:         ## Build the Docker image
	docker build -t $(IMAGE_NAME):latest .

run: build     ## Build and run the agent in daemon (loop) mode
	docker compose up -d
	@echo "Agent running. Use 'make logs' to follow output."

run-once: build  ## Run the agent once and exit
	docker run --rm --env-file .env \
		-v "$$(pwd)/output:/app/output" \
		-v "$$(pwd)/config:/app/config:ro" \
		$(IMAGE_NAME):latest --loop=false || \
	docker run --rm --env-file .env \
		-v "$$(pwd)/output:/app/output" \
		-v "$$(pwd)/config:/app/config:ro" \
		$(IMAGE_NAME):latest

stop:          ## Stop the running container
	docker compose down

logs:          ## Tail container logs
	docker logs -f $(CONTAINER)

# ── Local (non-Docker) commands ────────────────────────────────────────────────

install:       ## Install Python dependencies locally
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

run-local:     ## Run locally (once)
	$(PYTHON) main.py

dev:           ## Run locally with debug logging
	LOG_LEVEL=DEBUG $(PYTHON) main.py

# ── Development commands ───────────────────────────────────────────────────────

test:          ## Run tests
	$(PYTHON) -m pytest tests/ -v

lint:          ## Lint with ruff
	$(PYTHON) -m ruff check agents/ main.py

format:        ## Auto-format with ruff
	$(PYTHON) -m ruff format agents/ main.py

# ── Utilities ──────────────────────────────────────────────────────────────────

posts:         ## Print all generated posts
	@if [ -f output/posts.jsonl ]; then \
		cat output/posts.jsonl | python3 -c \
		"import sys,json; [print(f\"[{o['score']:.1f}] {o['text']}\n\") for o in map(json.loads, sys.stdin)]"; \
	else \
		echo "No posts yet — run 'make run-once' first"; \
	fi

clean:         ## Remove output files and Docker image
	rm -rf output/posts.jsonl output/state.json
	docker rmi $(IMAGE_NAME):latest 2>/dev/null || true

setup:         ## First-time setup: copy .env.example and create dirs
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env — add your ANTHROPIC_API_KEY"; fi
	mkdir -p output

help:          ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
