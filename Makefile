.PHONY: install dev run test lint format clean docker-build docker-run

install:
	uv pip install -e ".[dev]"

dev:
	hook-trap --port 8080 --open-browser

run:
	hook-trap --port 8080

test:
	pytest -v tests/

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-build:
	docker build -t hook-trap .

docker-run:
	docker run -p 8080:8080 -v hook_trap_data:/data hook-trap
