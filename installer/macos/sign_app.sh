#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
source "${ROOT}/installer/macos/common.sh"
BUILD_DIR="${BUILD_DIR:-${ROOT}/build/macos}"
PRODUCTS_DIR="${PRODUCTS_DIR:-${BUILD_DIR}/Build/Products/Release}"
EXT_BUNDLE_NAME="${EXT_BUNDLE_NAME:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
APP_BUNDLE="${APP_BUNDLE:-}"
EXT_BUNDLE="${EXT_BUNDLE:-${PRODUCTS_DIR}/com.sidus.amaran-desktop.cameraextension.systemextension}"
EMBEDDED_EXT_BUNDLE="${EMBEDDED_EXT_BUNDLE:-${APP_BUNDLE}/Contents/Library/SystemExtensions/$(basename "${EXT_BUNDLE}")}"
DEMO_APP_BUNDLE="${DEMO_APP_BUNDLE:-${PRODUCTS_DIR}/akvc-demo-app.app}"
DIRECT_SENDER_LIB="${DIRECT_SENDER_LIB:-${PRODUCTS_DIR}/libakvc-macos-direct-sender.dylib}"
COMMAND_TOOLS=(
  "${PRODUCTS_DIR}/akvc-macos-status"
  "${PRODUCTS_DIR}/akvc-macos-install"
  "${PRODUCTS_DIR}/akvc-macos-uninstall"
  "${PRODUCTS_DIR}/akvc-macos-list-devices"
  "${PRODUCTS_DIR}/akvc-macos-sync-ipc"
)
SIGN_IDENTITY="${SIGN_IDENTITY:-}"
ENTITLEMENTS_DEMO_APP="${ENTITLEMENTS_DEMO_APP:-${ROOT}/virtualcam/macos/demo_app/DemoApp.entitlements}"
ENTITLEMENTS_APP="${ENTITLEMENTS_APP:-${ENTITLEMENTS_DEMO_APP}}"
ENTITLEMENTS_EXT="${ENTITLEMENTS_EXT:-${ROOT}/virtualcam/macos/camera_extension/CameraExtension.entitlements}"
HOST_PROVISIONING_PROFILE="${HOST_PROVISIONING_PROFILE:-}"
EXTENSION_PROVISIONING_PROFILE="${EXTENSION_PROVISIONING_PROFILE:-}"
DEMO_APP_PROVISIONING_PROFILE="${DEMO_APP_PROVISIONING_PROFILE:-}"
HOST_EXPECTED_APP_ID="${HOST_EXPECTED_APP_ID:-XP3H66JF79.com.sidus.amaran-desktop}"
EXT_EXPECTED_APP_ID="${EXT_EXPECTED_APP_ID:-XP3H66JF79.com.sidus.amaran-desktop.cameraextension}"
DEMO_APP_EXPECTED_APP_ID="${DEMO_APP_EXPECTED_APP_ID:-XP3H66JF79.com.sidus.amaran-desktop.demo-app}"

if [[ -z "${APP_BUNDLE}" ]]; then
  APP_BUNDLE="$(akvc_autodetect_container_app_bundle "${PRODUCTS_DIR}" "${EXT_BUNDLE_NAME}" || true)"
fi
EMBEDDED_EXT_BUNDLE="${EMBEDDED_EXT_BUNDLE:-${APP_BUNDLE}/Contents/Library/SystemExtensions/$(basename "${EXT_BUNDLE}")}"

detect_sign_identity() {
  if ! command -v security >/dev/null 2>&1; then
    return 1
  fi
  security find-identity -v -p codesigning 2>/dev/null | \
    awk -F'"' '/Developer ID Application:/ { print $2; exit }'
}

if [[ -z "${SIGN_IDENTITY}" ]]; then
  SIGN_IDENTITY="$(detect_sign_identity || true)"
fi

if [[ -z "${SIGN_IDENTITY}" ]]; then
  echo "[macos-sign] SIGN_IDENTITY is required (or install an accessible Developer ID Application identity)" >&2
  exit 2
fi

if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "[macos-sign] missing app bundle: ${APP_BUNDLE}" >&2
  exit 2
fi

if [[ ! -d "${EXT_BUNDLE}" ]]; then
  echo "[macos-sign] missing extension bundle: ${EXT_BUNDLE}" >&2
  exit 2
fi

if [[ ! -d "${EMBEDDED_EXT_BUNDLE}" ]]; then
  echo "[macos-sign] missing embedded extension bundle: ${EMBEDDED_EXT_BUNDLE}" >&2
  exit 2
fi

if [[ ! -f "${ENTITLEMENTS_APP}" ]]; then
  echo "[macos-sign] missing app entitlements: ${ENTITLEMENTS_APP}" >&2
  exit 2
fi

if [[ ! -f "${ENTITLEMENTS_EXT}" ]]; then
  echo "[macos-sign] missing extension entitlements: ${ENTITLEMENTS_EXT}" >&2
  exit 2
fi

if [[ -d "${DEMO_APP_BUNDLE}" && "${DEMO_APP_BUNDLE}" != "${APP_BUNDLE}" && ! -f "${ENTITLEMENTS_DEMO_APP}" ]]; then
  echo "[macos-sign] missing demo app entitlements: ${ENTITLEMENTS_DEMO_APP}" >&2
  exit 2
fi

if [[ -n "${HOST_PROVISIONING_PROFILE}" && ! -f "${HOST_PROVISIONING_PROFILE}" ]]; then
  echo "[macos-sign] missing host provisioning profile: ${HOST_PROVISIONING_PROFILE}" >&2
  exit 2
fi

if [[ -n "${EXTENSION_PROVISIONING_PROFILE}" && ! -f "${EXTENSION_PROVISIONING_PROFILE}" ]]; then
  echo "[macos-sign] missing extension provisioning profile: ${EXTENSION_PROVISIONING_PROFILE}" >&2
  exit 2
fi

if [[ -n "${DEMO_APP_PROVISIONING_PROFILE}" && ! -f "${DEMO_APP_PROVISIONING_PROFILE}" ]]; then
  echo "[macos-sign] missing demo app provisioning profile: ${DEMO_APP_PROVISIONING_PROFILE}" >&2
  exit 2
fi

current_provisioning_udid() {
  if ! command -v system_profiler >/dev/null 2>&1; then
    return 0
  fi
  system_profiler SPHardwareDataType 2>/dev/null | awk -F': ' '/Provisioning UDID/ { print $2; exit }'
}

profile_application_identifier() {
  local profile_path="$1"
  if ! command -v security >/dev/null 2>&1 || [[ ! -x /usr/libexec/PlistBuddy ]]; then
    return 0
  fi
  local decoded_plist
  decoded_plist="$(mktemp "${TMPDIR:-/tmp}/akvc-profile.XXXXXX.plist")"
  if ! security cms -D -i "${profile_path}" > "${decoded_plist}" 2>/dev/null; then
    rm -f "${decoded_plist}"
    return 0
  fi
  /usr/libexec/PlistBuddy -c "Print :Entitlements:com.apple.application-identifier" "${decoded_plist}" 2>/dev/null || true
  rm -f "${decoded_plist}"
}

profile_contains_device_udid() {
  local profile_path="$1"
  local udid="$2"
  if [[ -z "${udid}" ]]; then
    return 0
  fi
  if ! command -v security >/dev/null 2>&1 || [[ ! -x /usr/libexec/PlistBuddy ]]; then
    return 0
  fi
  local decoded_plist devices_output
  decoded_plist="$(mktemp "${TMPDIR:-/tmp}/akvc-profile.XXXXXX.plist")"
  if ! security cms -D -i "${profile_path}" > "${decoded_plist}" 2>/dev/null; then
    rm -f "${decoded_plist}"
    return 0
  fi
  devices_output="$(/usr/libexec/PlistBuddy -c "Print :ProvisionedDevices" "${decoded_plist}" 2>/dev/null || true)"
  rm -f "${decoded_plist}"
  if [[ -z "${devices_output}" ]]; then
    return 0
  fi
  [[ "${devices_output}" == *"${udid}"* ]]
}

validate_profile_for_current_device() {
  local profile_path="$1"
  local label="$2"
  local expected_app_id="$3"
  if [[ -z "${profile_path}" ]]; then
    return 0
  fi

  local current_udid actual_app_id
  current_udid="$(current_provisioning_udid)"
  actual_app_id="$(profile_application_identifier "${profile_path}")"

  if [[ -n "${expected_app_id}" && -n "${actual_app_id}" && "${actual_app_id}" != "${expected_app_id}" ]]; then
    echo "[macos-sign] ${label} provisioning profile app identifier mismatch: expected ${expected_app_id}, got ${actual_app_id}" >&2
    exit 2
  fi

  if ! profile_contains_device_udid "${profile_path}" "${current_udid}"; then
    echo "[macos-sign] ${label} provisioning profile does not include this Mac's Provisioning UDID (${current_udid}): ${profile_path}" >&2
    exit 2
  fi
}

validate_profile_for_current_device "${HOST_PROVISIONING_PROFILE}" "host" "${HOST_EXPECTED_APP_ID}"
validate_profile_for_current_device "${EXTENSION_PROVISIONING_PROFILE}" "extension" "${EXT_EXPECTED_APP_ID}"
validate_profile_for_current_device "${DEMO_APP_PROVISIONING_PROFILE}" "demo app" "${DEMO_APP_EXPECTED_APP_ID}"

for tool in "${COMMAND_TOOLS[@]}"; do
  if [[ ! -f "${tool}" ]]; then
    echo "[macos-sign] missing command tool: ${tool}" >&2
    exit 2
  fi
done

if [[ ! -f "${DIRECT_SENDER_LIB}" ]]; then
  echo "[macos-sign] missing direct sender library: ${DIRECT_SENDER_LIB}" >&2
  exit 2
fi

codesign_with_runtime() {
  local output_file
  output_file="$(mktemp)"
  if codesign --force --timestamp --options runtime "$@" 2>"${output_file}"; then
    rm -f "${output_file}"
    return 0
  fi

  if grep -Eiq "timestamp service is not available|timestamp server|a timestamp was expected" "${output_file}"; then
    cat "${output_file}" >&2
    echo "[macos-sign] warning: timestamp service unavailable, retrying without --timestamp for local validation" >&2
    rm -f "${output_file}"
    codesign --force --options runtime "$@"
    return $?
  fi

  cat "${output_file}" >&2
  rm -f "${output_file}"
  return 1
}

clear_xattrs_if_available() {
  local target="$1"
  if command -v xattr >/dev/null 2>&1; then
    xattr -cr "${target}" 2>/dev/null || true
  fi
}

copy_target_for_stage() {
  local source="$1"
  local destination="$2"
  if [[ -d "${source}" ]]; then
    cp -R "${source}" "${destination}"
  else
    cp -p "${source}" "${destination}"
  fi
}

replace_target_with_stage() {
  local source="$1"
  local destination="$2"
  rm -rf "${destination}"
  mkdir -p "$(dirname "${destination}")"
  mv "${source}" "${destination}"
}

scrub_bundle_before_sign() {
  local bundle="$1"
  clear_xattrs_if_available "${bundle}"
  rm -rf "${bundle}/Contents/_CodeSignature" 2>/dev/null || true
}

scrub_file_before_sign() {
  local target="$1"
  clear_xattrs_if_available "${target}"
  codesign --remove-signature "${target}" >/dev/null 2>&1 || true
}

embed_provisioning_profile_if_configured() {
  local bundle="$1"
  local profile_path="${2:-}"
  local destination
  destination="${bundle}/Contents/embedded.provisionprofile"
  rm -f "${destination}"
  if [[ -z "${profile_path}" ]]; then
    return 0
  fi
  cp -p "${profile_path}" "${destination}"
}

sign_bundle_in_clean_stage() {
  local bundle="$1"
  local entitlements="$2"
  local verify_args="$3"
  local provisioning_profile="${4:-}"
  local stage_root staged_bundle
  stage_root="$(mktemp -d "${TMPDIR:-/tmp}/akvc-sign-bundle.XXXXXX")"
  staged_bundle="${stage_root}/$(basename "${bundle}")"
  copy_target_for_stage "${bundle}" "${staged_bundle}"
  scrub_bundle_before_sign "${staged_bundle}"
  embed_provisioning_profile_if_configured "${staged_bundle}" "${provisioning_profile}"
  codesign_with_runtime --sign "${SIGN_IDENTITY}" \
    --entitlements "${entitlements}" \
    "${staged_bundle}"
  # shellcheck disable=SC2086
  codesign --verify ${verify_args} "${staged_bundle}"
  replace_target_with_stage "${staged_bundle}" "${bundle}"
  # shellcheck disable=SC2086
  codesign --verify ${verify_args} "${bundle}"
  rm -rf "${stage_root}"
}

sign_file_in_clean_stage() {
  local target="$1"
  local entitlements="${2:-}"
  local stage_root staged_target
  stage_root="$(mktemp -d "${TMPDIR:-/tmp}/akvc-sign-file.XXXXXX")"
  staged_target="${stage_root}/$(basename "${target}")"
  copy_target_for_stage "${target}" "${staged_target}"
  scrub_file_before_sign "${staged_target}"
  if [[ -n "${entitlements}" ]]; then
    codesign_with_runtime --sign "${SIGN_IDENTITY}" \
      --entitlements "${entitlements}" \
      "${staged_target}"
  else
    codesign_with_runtime --sign "${SIGN_IDENTITY}" "${staged_target}"
  fi
  codesign --verify --strict --verbose=2 "${staged_target}"
  replace_target_with_stage "${staged_target}" "${target}"
  codesign --verify --strict --verbose=2 "${target}"
  rm -rf "${stage_root}"
}

echo "[macos-sign] extension: ${EXT_BUNDLE}"
sign_bundle_in_clean_stage "${EXT_BUNDLE}" "${ENTITLEMENTS_EXT}" "--strict --verbose=2" "${EXTENSION_PROVISIONING_PROFILE}"

if [[ "${EMBEDDED_EXT_BUNDLE}" != "${EXT_BUNDLE}" ]]; then
  echo "[macos-sign] embedded extension: ${EMBEDDED_EXT_BUNDLE}"
  sign_bundle_in_clean_stage "${EMBEDDED_EXT_BUNDLE}" "${ENTITLEMENTS_EXT}" "--strict --verbose=2" "${EXTENSION_PROVISIONING_PROFILE}"
fi

for tool in "${COMMAND_TOOLS[@]}"; do
  echo "[macos-sign] tool: ${tool}"
  sign_file_in_clean_stage "${tool}"
done

echo "[macos-sign] direct sender dylib: ${DIRECT_SENDER_LIB}"
sign_file_in_clean_stage "${DIRECT_SENDER_LIB}"

echo "[macos-sign] app: ${APP_BUNDLE}"
sign_bundle_in_clean_stage "${APP_BUNDLE}" "${ENTITLEMENTS_APP}" "--deep --strict --verbose=2" "${HOST_PROVISIONING_PROFILE}"

if [[ -d "${DEMO_APP_BUNDLE}" && "${DEMO_APP_BUNDLE}" != "${APP_BUNDLE}" ]]; then
  echo "[macos-sign] demo app: ${DEMO_APP_BUNDLE}"
  sign_bundle_in_clean_stage "${DEMO_APP_BUNDLE}" "${ENTITLEMENTS_DEMO_APP}" "--deep --strict --verbose=2" "${DEMO_APP_PROVISIONING_PROFILE}"
fi

if command -v spctl >/dev/null 2>&1; then
  spctl -a -vvv "${APP_BUNDLE}" || true
  if [[ -d "${DEMO_APP_BUNDLE}" && "${DEMO_APP_BUNDLE}" != "${APP_BUNDLE}" ]]; then
    spctl -a -vvv "${DEMO_APP_BUNDLE}" || true
  fi
fi
echo "[macos-sign] signing complete"
