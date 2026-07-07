#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
source "${ROOT}/installer/macos/common.sh"
BUILD_DIR="${BUILD_DIR:-${ROOT}/build/macos}"
PRODUCTS_DIR="${PRODUCTS_DIR:-${BUILD_DIR}/Build/Products/Release}"
EXT_BUNDLE_NAME="${EXT_BUNDLE_NAME:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
APP_BUNDLE="${APP_BUNDLE:-}"
PKG_PATH="${PKG_PATH:-${BUILD_DIR}/VirtualCamera.pkg}"
ZIP_PATH="${ZIP_PATH:-${BUILD_DIR}/VirtualCamera.zip}"
STAGING_DIR="${STAGING_DIR:-${BUILD_DIR}/zip-staging}"
export COPYFILE_DISABLE=1

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi

rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

if [[ -d "${APP_BUNDLE}" ]]; then
  cp -R "${APP_BUNDLE}" "${STAGING_DIR}/"
  find "${STAGING_DIR}/$(basename "${APP_BUNDLE}")" -name '._*' -type f -delete 2>/dev/null || true
fi

if [[ -f "${PKG_PATH}" ]]; then
  cp -f "${PKG_PATH}" "${STAGING_DIR}/"
fi

if [[ -z "$(find "${STAGING_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "[macos-build-zip] nothing to archive" >&2
  exit 2
fi

find "${STAGING_DIR}" -name '._*' -type f -delete 2>/dev/null || true

(cd "${STAGING_DIR}" && /usr/bin/zip -qry "${ZIP_PATH}" .)
echo "[macos-build-zip] created ${ZIP_PATH}"
