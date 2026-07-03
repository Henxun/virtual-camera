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
ZIP_PATH="${ZIP_PATH:-${BUILD_DIR}/VirtualCamera.zip}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"
NOTARIZE_TARGETS="${NOTARIZE_TARGETS:-app,pkg}"

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi

submit_for_notarization() {
  local artifact_path="$1"
  local artifact_label="$2"
  if [[ ! -e "${artifact_path}" ]]; then
    echo "[macos-notarize] missing ${artifact_label}: ${artifact_path}" >&2
    exit 2
  fi
  echo "[macos-notarize] ${artifact_label}: ${artifact_path}"
  xcrun notarytool submit "${artifact_path}" \
    --keychain-profile "${NOTARY_PROFILE}" \
    --wait
}

if [[ -z "${NOTARY_PROFILE}" ]]; then
  echo "[macos-notarize] NOTARY_PROFILE is required" >&2
  exit 2
fi

if ! command -v pkgutil >/dev/null 2>&1; then
  echo "[macos-notarize] pkgutil is required" >&2
  exit 2
fi

if ! xcrun --find notarytool >/dev/null 2>&1; then
  echo "[macos-notarize] notarytool is not available via xcrun" >&2
  exit 2
fi

IFS=',' read -r -a REQUESTED_TARGETS <<< "${NOTARIZE_TARGETS}"
if [[ ${#REQUESTED_TARGETS[@]} -eq 0 ]]; then
  echo "[macos-notarize] NOTARIZE_TARGETS is empty" >&2
  exit 2
fi

for raw_target in "${REQUESTED_TARGETS[@]}"; do
  target="$(echo "${raw_target}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${target}" in
    app)
      if [[ ! -d "${APP_BUNDLE}" ]]; then
        echo "[macos-notarize] missing app bundle: ${APP_BUNDLE}" >&2
        exit 2
      fi
      ;;
    pkg)
      if [[ ! -f "${PKG_PATH}" ]]; then
        echo "[macos-notarize] missing pkg: ${PKG_PATH}" >&2
        exit 2
      fi
      SIGNATURE_OUTPUT="$(pkgutil --check-signature "${PKG_PATH}" 2>&1 || true)"
      echo "${SIGNATURE_OUTPUT}"
      if [[ "${SIGNATURE_OUTPUT}" == *"no signature"* ]] || [[ "${SIGNATURE_OUTPUT}" == *"not signed"* ]]; then
        echo "[macos-notarize] pkg must be signed before notarization" >&2
        exit 2
      fi
      ;;
    dmg)
      if [[ ! -f "${DMG_PATH}" ]]; then
        echo "[macos-notarize] missing dmg: ${DMG_PATH}" >&2
        exit 2
      fi
      ;;
    zip)
      if [[ ! -f "${ZIP_PATH}" ]]; then
        echo "[macos-notarize] missing zip: ${ZIP_PATH}" >&2
        exit 2
      fi
      ;;
    "")
      ;;
    *)
      echo "[macos-notarize] unsupported target: ${target}" >&2
      exit 2
      ;;
  esac
done

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

for raw_target in "${REQUESTED_TARGETS[@]}"; do
  target="$(echo "${raw_target}" | tr '[:upper:]' '[:lower:]' | xargs)"
  case "${target}" in
    app)
      APP_ARCHIVE="${TMP_DIR}/$(basename "${APP_BUNDLE}").zip"
      export COPYFILE_DISABLE=1
      /usr/bin/ditto -c -k --keepParent --norsrc "${APP_BUNDLE}" "${APP_ARCHIVE}"
      submit_for_notarization "${APP_ARCHIVE}" "app archive"
      ;;
    pkg)
      submit_for_notarization "${PKG_PATH}" "pkg"
      ;;
    dmg)
      submit_for_notarization "${DMG_PATH}" "dmg"
      ;;
    zip)
      submit_for_notarization "${ZIP_PATH}" "zip"
      ;;
    "")
      ;;
    *)
      echo "[macos-notarize] unsupported target: ${target}" >&2
      exit 2
      ;;
  esac
done

echo "[macos-notarize] notarization accepted"
