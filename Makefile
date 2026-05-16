.PHONY: test lint format release-notes release-notes-file release-notes-publish release release-patch release-minor release-major release-validate

test:
	@uv run --extra dev pytest

lint:
	@uv run --extra dev ruff check

format:
	@uv run --extra dev ruff format

release-validate:
	@test -n "$(VERSION)" || (echo "Error: Set VERSION=x.y.z" && exit 1)
	@echo "Checking pyproject.toml version..."
	@FILE_VERSION=$$(awk -F'"' '/^version/ {print $$2; exit}' pyproject.toml); \
	if [ "$(VERSION)" != "$$FILE_VERSION" ]; then \
		echo "Error: VERSION=$(VERSION) does not match pyproject.toml version=$$FILE_VERSION"; \
		exit 1; \
	fi
	@echo "Checking docs/changelog.md for [$(VERSION)] section..."
	@if ! grep -q "^## \[$(VERSION)\]" docs/changelog.md; then \
		echo "Error: No ## [$(VERSION)] section found in docs/changelog.md"; \
		echo "Add release notes to docs/changelog.md before publishing."; \
		exit 1; \
	fi
	@echo "Release validation passed for v$(VERSION)"

release-notes: release-validate
	@uv run python scripts/release_notes.py $(VERSION)

release-notes-file: release-validate
	@uv run python scripts/release_notes.py $(VERSION) > /tmp/news-watch-v$(VERSION)-notes.md
	@echo /tmp/news-watch-v$(VERSION)-notes.md

release-notes-publish: release-validate
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
