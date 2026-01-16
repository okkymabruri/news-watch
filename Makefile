.PHONY: test lint format release release-patch release-minor release-major

test:
	@uv run pytest

lint:
	@uv run ruff check

format:
	@uv run ruff format

release-patch:
	@uv run python scripts/version.py release

release-minor:
	@uv run python scripts/version.py release --minor

release-major:
	@uv run python scripts/version.py release --major

release:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@uv run python scripts/version.py release $(VERSION)
