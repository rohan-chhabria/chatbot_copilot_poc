.PHONY: install install-dev lint type-check test test-unit test-integration validate run clean

install:
	pip install -r requirements.txt

install-dev: install
	pip install -r requirements-dev.txt

lint:
	ruff check src/ tests/ --output-format=github

lint-fix:
	ruff check --fix src/ tests/

type-check:
	mypy src/ --ignore-missing-imports || true

test:
	pytest tests/ -v --tb=short

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short

validate:
	sam validate --template infra/template.yaml --lint

run:
	uvicorn src.api.handler:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -f test-results.xml
