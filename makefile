.PHONY: help install lint format test coverage pre-commit clean

help:
	@echo "Available commands:"
	@echo "  install   - Install dependencies"
	@echo "  lint      - Run linting checks"
	@echo "  format    - Format code"
	@echo "  test      - Run tests"
	@echo "  coverage  - Run tests with coverage"
	@echo "  pre-commit - Run pre-commit hooks"
	@echo "  clean     - Remove generated files"

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
