#!/usr/bin/env bash
# One-shot local setup for BadCop: virtualenv, editable install, tests, sample workspace.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "BadCop needs Python 3.11 or newer (found: $("$PYTHON" --version 2>&1))" >&2
  exit 1
fi

"$PYTHON" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e .

echo "Running tests..."
python -m unittest discover -s tests -v

if [ ! -f badcop.toml ]; then
  echo "Creating a sample workspace in ./workspace ..."
  badcop init --dir workspace
fi

cat <<MSG

BadCop is installed in .venv. Next steps:
  source .venv/bin/activate
  cd workspace && edit badcop.toml and invoices.csv
  export BADCOP_SMTP_PASSWORD='...'      # your SMTP password / API token
  badcop run --dry-run --verbose         # see what would go out
  badcop run                             # send for real (schedule this daily)
MSG
