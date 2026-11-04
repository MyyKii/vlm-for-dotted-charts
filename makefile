check:
	ruff format
	ruff check --fix
	pytest

ruff: 
	ruff format
	ruff check --fix

cov:
	pytest --cov=. --cov-report=term-missing
