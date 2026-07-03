#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
source "${ROOT}/installer/macos/common.sh"
BUILD_DIR="${BUILD_DIR:-${ROOT}/build/macos}"
PRODUCTS_DIR="${PRODUCTS_DIR:-${BUILD_DIR}/Build/Products/Release}"
EXT_BUNDLE_NAME="${EXT_BUNDLE_NAME:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
APP_BUNDLE="${APP_BUNDLE:-}"
PKG_PATH="${PKG_PATH:-${BUILD_DIR}/VirtualCamera.pkg}"
COMPONENT_PKG_PATH="${COMPONENT_PKG_PATH:-${BUILD_DIR}/VirtualCamera.component.pkg}"
STAGING_DIR="${STAGING_DIR:-${BUILD_DIR}/pkg-staging}"
PKG_ROOT_DIR="${PKG_ROOT_DIR:-}"
INSTALL_LOCATION="${INSTALL_LOCATION:-/Applications}"
PACKAGE_IDENTIFIER="${PACKAGE_IDENTIFIER:-com.akvc.virtual-camera.pkg}"
PACKAGE_VERSION="${PACKAGE_VERSION:-0.5.0}"
PRODUCTSIGN_IDENTITY="${PRODUCTSIGN_IDENTITY:-}"
export COPYFILE_DISABLE=1

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi

detect_productsign_identity() {
  if ! command -v security >/dev/null 2>&1; then
    return 1
  fi
  security find-identity -v -p basic 2>/dev/null | \
    awk -F'"' '/Developer ID Installer:/ { print $2; exit }'
}

if [[ -z "${PRODUCTSIGN_IDENTITY}" ]]; then
  PRODUCTSIGN_IDENTITY="$(detect_productsign_identity || true)"
fi

force_remove_dir() {
  local target="$1"
  local output_file
  if [[ ! -e "${target}" ]]; then
    return 0
  fi
  output_file="$(mktemp)"
  chmod -R u+w "${target}" >"${output_file}" 2>&1 || true
  find "${target}" -type d -exec chmod u+rwx {} + >>"${output_file}" 2>&1 || true
  if rm -rf "${target}" >>"${output_file}" 2>&1; then
    rm -f "${output_file}"
    return 0
  fi
  rm -f "${output_file}"
  return 1
}

mkdir -p "${BUILD_DIR}"
if ! force_remove_dir "${STAGING_DIR}"; then
  FALLBACK_STAGING_DIR="$(mktemp -d "${BUILD_DIR}/pkg-staging.XXXXXX")"
  echo "[macos-build-pkg] warning: failed to reuse staging dir ${STAGING_DIR}; using ${FALLBACK_STAGING_DIR} instead" >&2
  STAGING_DIR="${FALLBACK_STAGING_DIR}"
else
  mkdir -p "${STAGING_DIR}"
fi

if [[ -z "${PKG_ROOT_DIR}" ]]; then
  PKG_ROOT_DIR="${STAGING_DIR}/root"
fi

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "[macos-build-pkg] missing app bundle: ${APP_BUNDLE}" >&2
  exit 2
fi

echo "[macos-build-pkg] app bundle: ${APP_BUNDLE}"
echo "[macos-build-pkg] component pkg: ${COMPONENT_PKG_PATH}"
echo "[macos-build-pkg] final pkg: ${PKG_PATH}"

STAGED_APP="${PKG_ROOT_DIR}/$(basename "${APP_BUNDLE}")"
ditto --norsrc --noextattr "${APP_BUNDLE}" "${STAGED_APP}"
find "${STAGED_APP}" -name '._*' -type f -delete 2>/dev/null || true
xattr -cr "${PKG_ROOT_DIR}" 2>/dev/null || true
find "${PKG_ROOT_DIR}" -name '._*' -type f -delete 2>/dev/null || true

pkgbuild \
  --root "${PKG_ROOT_DIR}" \
  --filter '(^|/)\._.*' \
  --install-location "${INSTALL_LOCATION}" \
  --identifier "${PACKAGE_IDENTIFIER}" \
  --version "${PACKAGE_VERSION}" \
  "${COMPONENT_PKG_PATH}"

REPACK_DIR="${STAGING_DIR}/repack"
REPACK_FULL_DIR="${REPACK_DIR}/full"
REPACK_RAW_DIR="${REPACK_DIR}/raw"
REPACK_CLEAN_PKG="${REPACK_DIR}/clean.pkg"
force_remove_dir "${REPACK_DIR}"
mkdir -p "${REPACK_DIR}"
pkgutil --expand-full "${COMPONENT_PKG_PATH}" "${REPACK_FULL_DIR}"
pkgutil --expand "${COMPONENT_PKG_PATH}" "${REPACK_RAW_DIR}"
mkbom -s "${REPACK_FULL_DIR}/Payload" "${REPACK_RAW_DIR}/Bom"
(
  cd "${REPACK_FULL_DIR}/Payload"
  find . -print | LC_ALL=C sort | LC_ALL=C cpio -o --format odc | gzip -c > "${REPACK_RAW_DIR}/Payload"
)
pkgutil --flatten "${REPACK_RAW_DIR}" "${REPACK_CLEAN_PKG}"
mv -f "${REPACK_CLEAN_PKG}" "${COMPONENT_PKG_PATH}"

mv -f "${COMPONENT_PKG_PATH}" "${PKG_PATH}"

if [[ -n "${PRODUCTSIGN_IDENTITY}" ]]; then
  UNSIGNED_PATH="${PKG_PATH%.pkg}.unsigned.pkg"
  mv -f "${PKG_PATH}" "${UNSIGNED_PATH}"
  productsign --sign "${PRODUCTSIGN_IDENTITY}" "${UNSIGNED_PATH}" "${PKG_PATH}"
  rm -f "${UNSIGNED_PATH}"
fi

pkgutil --check-signature "${PKG_PATH}" || true
echo "[macos-build-pkg] created ${PKG_PATH}"
