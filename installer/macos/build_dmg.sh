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
STAGING_DIR="${STAGING_DIR:-${BUILD_DIR}/dmg-staging}"
VOLUME_NAME="${VOLUME_NAME:-VirtualCamera}"

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi

rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

if [[ -d "${APP_BUNDLE}" ]]; then
  cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"
fi

if [[ -f "${PKG_PATH}" ]]; then
  cp -f "${PKG_PATH}" "${STAGING_DIR}/"
fi

if [[ -z "$(find "${STAGING_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "[macos-build-dmg] nothing to package" >&2
  exit 2
fi

hdiutil create \
  -volname "${VOLUME_NAME}" \
  -srcfolder "${STAGING_DIR}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

echo "[macos-build-dmg] created ${DMG_PATH}"
