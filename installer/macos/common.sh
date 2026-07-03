#!/usr/bin/env bash
set -euo pipefail

AKVC_DEFAULT_EXTENSION_BUNDLE_NAME="${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME:-com.sidus.amaran-desktop.cameraextension.systemextension}"

akvc_is_preferred_container_app() {
  local basename
  basename="$(basename "$1")"
  case "${basename}" in
    akvc-host.app)
      return 1
      ;;
    *)
      return 0
      ;;
  esac
}

akvc_app_embeds_extension() {
  local app_bundle="$1"
  local extension_bundle_name="${2:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
  [[ -d "${app_bundle}/Contents/Library/SystemExtensions/${extension_bundle_name}" ]]
}

akvc_autodetect_container_app_bundle() {
  local search_dir="$1"
  local extension_bundle_name="${2:-${AKVC_DEFAULT_EXTENSION_BUNDLE_NAME}}"
  local app_bundle

  [[ -d "${search_dir}" ]] || return 1

  while IFS= read -r -d '' app_bundle; do
    if akvc_app_embeds_extension "${app_bundle}" "${extension_bundle_name}" \
      && akvc_is_preferred_container_app "${app_bundle}"; then
      printf '%s\n' "${app_bundle}"
      return 0
    fi
  done < <(find "${search_dir}" -maxdepth 1 -mindepth 1 -type d -name '*.app' -print0 | sort -z)

  while IFS= read -r -d '' app_bundle; do
    if akvc_app_embeds_extension "${app_bundle}" "${extension_bundle_name}"; then
      printf '%s\n' "${app_bundle}"
      return 0
    fi
  done < <(find "${search_dir}" -maxdepth 1 -mindepth 1 -type d -name '*.app' -print0 | sort -z)

  return 1
}
