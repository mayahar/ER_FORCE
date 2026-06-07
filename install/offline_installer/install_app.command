#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_APP="$SCRIPT_DIR/payload/app"
INSTALL_DIR="${1:-$HOME/Applications/ER_FORCE}"
VENV_DIR="$INSTALL_DIR/.venv"

echo
echo "ERR_FORCE macOS installer (experimental)"
echo "Install directory: $INSTALL_DIR"
echo

if [[ ! -d "$PAYLOAD_APP" ]]; then
  echo "Missing installer payload: $PAYLOAD_APP" >&2
  exit 1
fi

PYTHON_BIN=""
for candidate in python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.10 or newer is required on macOS." >&2
  echo "Install it from python.org or Homebrew, then run this file again." >&2
  exit 2
fi

mkdir -p "$INSTALL_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "$PAYLOAD_APP"/ "$INSTALL_DIR"/
else
  cp -R "$PAYLOAD_APP"/. "$INSTALL_DIR"/
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

if [[ -f "$INSTALL_DIR/eye_tracking_setup/requirements.txt" ]]; then
  "$VENV_DIR/bin/python" -m pip install -r "$INSTALL_DIR/eye_tracking_setup/requirements.txt" || {
    echo
    echo "Warning: eye-tracking extras did not install on macOS."
    echo "The app may still run, but Tobii/eye tracking may need a separate macOS setup."
  }
fi

cat > "$INSTALL_DIR/ERR_FORCE.command" <<EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
exec "$VENV_DIR/bin/python" -m ui.app "\$@"
EOF
chmod +x "$INSTALL_DIR/ERR_FORCE.command"

DESKTOP_DIR="$HOME/Desktop"
if [[ -d "$DESKTOP_DIR" ]]; then
  cp "$INSTALL_DIR/ERR_FORCE.command" "$DESKTOP_DIR/ERR_FORCE.command"
  chmod +x "$DESKTOP_DIR/ERR_FORCE.command"
fi

echo
echo "macOS installation completed."
echo "Run: $INSTALL_DIR/ERR_FORCE.command"
echo
echo "Note: FlightGear, Tobii drivers/SDK, and hardware calibration may require"
echo "separate macOS-specific setup."
