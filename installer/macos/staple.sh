#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
source "${ROOT}/installer/macos/common.sh"
BUILD_DIR="${BUILD_DIR:-${ROOT}/build/macos}"
PRODUCTS_DIR="${PRODUCTS_DIR:-${BUILD_DIR}/Build/Products/Release}"
EXT_BUNDLE_NAME="${EXT_BUNDLE_NAME:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
APP_BUNDLE="${APP_BUNDLE:-}"
PKG_PATH="${PKG_PATH:-${BUILD_DIR}/VirtualCamera.pkg}"
DMG_PATH="${DMG_PATH:-${BUILD_DIR}/VirtualCamera.dmg}"
STAPLE_TARGETS="${STAPLE_TARGETS:-app,pkg}"

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi

if ! command -v pkgutil >/dev/null 2>&1; then
  echo "[macos-staple] pkgutil is required" >&2
  exit 2
fi

IFS=',' read -r -a REQUESTED_TARGETS <<< "${STAPLE_TARGETS}"
if [[ ${#REQUESTED_TARGETS[@]} -eq 0 ]]; then
  echo "[macos-staple] STAPLE_TARGETS is empty" >&2
  exit 2
fi

for raw_target in "${REQUESTED_TARGETS[@]}"; do
  target="$(echo "${raw_target}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${target}" in
    app)
      if [[ ! -d "${APP_BUNDLE}" ]]; then
        echo "[macos-staple] missing app bundle: ${APP_BUNDLE}" >&2
        exit 2
      fi
      echo "[macos-staple] app: ${APP_BUNDLE}"
      xcrun stapler staple "${APP_BUNDLE}"
      xcrun stapler validate "${APP_BUNDLE}"
      if command -v spctl >/dev/null 2>&1; then
        spctl -a -vvv "${APP_BUNDLE}" || true
      fi
      ;;
    pkg)
      if [[ ! -f "${PKG_PATH}" ]]; then
        echo "[macos-staple] missing pkg: ${PKG_PATH}" >&2
        exit 2
      fi
      echo "[macos-staple] pkg: ${PKG_PATH}"
      pkgutil --check-signature "${PKG_PATH}" || true
      xcrun stapler staple "${PKG_PATH}"
      xcrun stapler validate "${PKG_PATH}"
      if command -v spctl >/dev/null 2>&1; then
        spctl -a -vvv -t install "${PKG_PATH}" || true
      fi
      ;;
    dmg)
      if [[ ! -f "${DMG_PATH}" ]]; then
        echo "[macos-staple] missing dmg: ${DMG_PATH}" >&2
        exit 2
      fi
      echo "[macos-staple] dmg: ${DMG_PATH}"
      xcrun stapler staple "${DMG_PATH}"
      xcrun stapler validate "${DMG_PATH}"
      if command -v spctl >/dev/null 2>&1; then
        spctl -a -vvv -t open "${DMG_PATH}" || true
      fi
      ;;
    "")
      ;;
    *)
      echo "[macos-staple] unsupported target: ${target}" >&2
      exit 2
      ;;
  esac
done

echo "[macos-staple] staple complete"
