#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
source "${ROOT}/installer/macos/common.sh"
APP_PATH="${APP_PATH:-}"
EXT_BUNDLE_NAME="${EXT_BUNDLE_NAME:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
UNINSTALL_TOOL="${UNINSTALL_TOOL:-}"

if [[ -z "${APP_PATH}" ]]; then
  APP_PATH="$(akvc_autodetect_container_app_bundle "/Applications" "${EXT_BUNDLE_NAME}" || true)"
fi

if [[ -z "${UNINSTALL_TOOL}" ]]; then
  for candidate in \
    "${ROOT}/build/macos/Build/Products/Release/akvc-macos-uninstall" \
    "${ROOT}/build/macos/bin/akvc-macos-uninstall" \
    "${ROOT}/build/bin/akvc-macos-uninstall"
  do
    if [[ -x "${candidate}" ]]; then
      UNINSTALL_TOOL="${candidate}"
      break
    fi
  done
fi

if [[ -x "${UNINSTALL_TOOL}" ]]; then
  echo "[macos-uninstall] invoking ${UNINSTALL_TOOL}"
  "${UNINSTALL_TOOL}" || true
fi

if [[ -n "${APP_PATH}" && "${APP_PATH}" != "/" && -d "${APP_PATH}" ]]; then
  echo "[macos-uninstall] removing ${APP_PATH}"
  rm -rf "${APP_PATH}"
fi

echo "[macos-uninstall] completed"
