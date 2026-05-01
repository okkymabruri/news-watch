.PHONY: test lint format release-notes release-notes-file release-notes-publish release release-patch release-minor release-major

test:
	@uv run --extra dev pytest

lint:
	@uv run --extra dev ruff check

format:
	@uv run --extra dev ruff format

release-notes:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@uv run python scripts/release_notes.py $(VERSION)

release-notes-file:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@uv run python scripts/release_notes.py $(VERSION) > /tmp/news-watch-v$(VERSION)-notes.md
	@echo /tmp/news-watch-v$(VERSION)-notes.md

release-notes-publish:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@uv run python scripts/release_notes.py $(VERSION) > /tmp/news-watch-v$(VERSION)-notes.md
	@gh release edit v$(VERSION) --notes-file /tmp/news-watch-v$(VERSION)-notes.md

release-patch:
	@uv run python scripts/version.py release

release-minor:
	@uv run python scripts/version.py release --minor

release-major:
	@uv run python scripts/version.py release --major

release:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@uv run python scripts/version.py release $(VERSION)
