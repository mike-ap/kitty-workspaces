shell_files := "bootstrap.sh install.sh .envrc"

check:
    just format-check
    just lint
    just test

format:
    uv run --locked ruff format .
    shfmt -w {{shell_files}}
    uv run --locked mdformat *.md
    markdownlint-cli2 --fix

format-check:
    uv run --locked ruff format --check .
    shfmt -d {{shell_files}}
    uv run --locked mdformat --check *.md

lint:
    uv run --locked ruff check .
    shellcheck {{shell_files}}
    markdownlint-cli2

test:
    uv run --locked pytest -q

test-integration:
    uv run --locked pytest -q --run-kitty-integration -m kitty_integration tests/integration

# Build and verify the source archive in dist/ using Kitty's interpreter.
dist:
    uv build --sdist
    uv run --locked python scripts/check_dist.py

# Prepare and commit a release, then push its branch and annotated tag to origin.
[positional-arguments]
release version:
    uv run --locked python scripts/release.py "$1"

# Install or update the current checkout in your Kitty config directory.
install:
    sh install.sh

# Remove installed project files; configuration entries are managed manually.
uninstall:
    sh install.sh --uninstall

# Print the current Kitty Workspaces state as JSON.
state:
    kitten @ kitten "{{justfile_directory()}}/src/kitty_workspaces/kitten.py" state | jq .


# Branch coverage for Python running in pytest; Kitty subprocesses are separate.
coverage:
    uv run --locked pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-report=html
