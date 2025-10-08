.PHONY: help install lint format test coverage pre-commit clean package docker-up docker-down docker-logs

help:
	@echo "Available commands:"
	@echo "  install     - Install dependencies"
	@echo "  lint        - Run linting checks"
	@echo "  format      - Format code"
	@echo "  test        - Run tests"
	@echo "  coverage    - Run tests with coverage"
	@echo "  pre-commit  - Run pre-commit hooks"
	@echo "  clean       - Remove generated files"
	@echo "  package     - Create distribution package"
	@echo "  docker-up   - Start Docker test server"
	@echo "  docker-down - Stop Docker test server"
	@echo "  docker-logs - View Docker logs"

install:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check .
	mypy custom_components/your_integration


format:
	ruff format .
	ruff check --fix .

test:
	pytest

coverage:
	pytest --cov --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

package:
	python -m build
	@echo "Package created in dist/"

docker-up:
	docker compose up -d
	@echo "Home Assistant running at http://localhost:8123"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
