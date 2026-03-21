#!/usr/bin/env sh
set -eu

CAMOUFOX_OVERRIDE_DIR="${CAMOUFOX_OVERRIDE_DIR:-/app/camoufox_override}"

apply_camoufox_override() {
  if [ ! -d "$CAMOUFOX_OVERRIDE_DIR" ]; then
    return 0
  fi

  python_bin="${VIRTUAL_ENV:-/opt/venv}/bin/python"
  pip_bin="${VIRTUAL_ENV:-/opt/venv}/bin/pip"
  if [ ! -x "$python_bin" ]; then
    python_bin="python"
  fi
  if [ ! -x "$pip_bin" ]; then
    pip_bin="pip"
  fi

  # Priority 1: wheel override (e.g. camoufox-*.whl)
  if ls "$CAMOUFOX_OVERRIDE_DIR"/camoufox*.whl >/dev/null 2>&1; then
    echo "Applying camoufox wheel override from $CAMOUFOX_OVERRIDE_DIR"
    # shellcheck disable=SC2086
    "$pip_bin" install --no-deps --force-reinstall $CAMOUFOX_OVERRIDE_DIR/camoufox*.whl
    return 0
  fi

  # Priority 2: source package override (directory named `camoufox`)
  if [ -d "$CAMOUFOX_OVERRIDE_DIR/camoufox" ]; then
    site_pkg="$("$python_bin" -c 'import site; print(site.getsitepackages()[0])')"
    if [ -n "$site_pkg" ] && [ -d "$site_pkg" ]; then
      echo "Applying camoufox source override from $CAMOUFOX_OVERRIDE_DIR/camoufox"
      rm -rf "$site_pkg/camoufox"
      cp -a "$CAMOUFOX_OVERRIDE_DIR/camoufox" "$site_pkg/"
      return 0
    fi
  fi
}

apply_camoufox_override

/app/scripts/init_storage.sh
python /app/scripts/wait_for_storage.py

exec "$@"
