#!/usr/bin/env bash
# PeerFold installer — macOS and Linux. Fetches the latest GitHub release.
set -euo pipefail

REPO="vincenzoml/PeerFold"
BASE_URL="https://github.com/${REPO}/releases/latest/download"

_PEERFOLD_TMP=""
_PEERFOLD_MOUNT=""

if ! command -v curl >/dev/null 2>&1; then
  echo "PeerFold install requires curl." >&2
  exit 1
fi

_peerfold_cleanup() {
  if [[ -n "${_PEERFOLD_MOUNT}" && -d "${_PEERFOLD_MOUNT}/PeerFold.app" ]]; then
    hdiutil detach "${_PEERFOLD_MOUNT}" -quiet 2>/dev/null || true
  fi
  if [[ -n "${_PEERFOLD_TMP}" && -d "${_PEERFOLD_TMP}" ]]; then
    rm -rf "${_PEERFOLD_TMP}"
  fi
  _PEERFOLD_MOUNT=""
  _PEERFOLD_TMP=""
}

OS="$(uname -s)"

install_macos() {
  if ! command -v hdiutil >/dev/null 2>&1; then
    echo "PeerFold macOS install requires hdiutil." >&2
    exit 1
  fi

  local dest apps_dir
  _PEERFOLD_TMP="$(mktemp -d)"
  _PEERFOLD_MOUNT="${_PEERFOLD_TMP}/mount"
  mkdir -p "${_PEERFOLD_MOUNT}"
  trap _peerfold_cleanup EXIT

  echo "Downloading PeerFold for macOS…"
  curl -fsSL -o "${_PEERFOLD_TMP}/peerfold.dmg" "${BASE_URL}/peerfold-macos.dmg"
  hdiutil attach -nobrowse -quiet -mountpoint "${_PEERFOLD_MOUNT}" "${_PEERFOLD_TMP}/peerfold.dmg"

  if [[ ! -d "${_PEERFOLD_MOUNT}/PeerFold.app" ]]; then
    echo "PeerFold.app not found in disk image." >&2
    exit 1
  fi

  if [[ -w /Applications ]]; then
    apps_dir="/Applications"
  else
    apps_dir="${HOME}/Applications"
    mkdir -p "${apps_dir}"
  fi
  dest="${apps_dir}/PeerFold.app"
  rm -rf "${dest}"
  cp -R "${_PEERFOLD_MOUNT}/PeerFold.app" "${dest}"

  _peerfold_cleanup
  trap - EXIT

  echo "Installed PeerFold to ${dest}"
  open -R "${dest}"
  echo "PeerFold is selected in Finder — double-click to open and choose your PDF."
}

install_linux() {
  local bin_dir dest
  bin_dir="${PEERFOLD_BIN_DIR:-${HOME}/.local/bin}"
  mkdir -p "${bin_dir}"
  dest="${bin_dir}/peerfold"

  echo "Downloading PeerFold for Linux…"
  curl -fsSL -o "${dest}" "${BASE_URL}/peerfold-linux"
  chmod +x "${dest}"

  echo "Installed peerfold to ${dest}"
  case ":${PATH}:" in
    *":${bin_dir}:"*) ;;
    *)
      echo "Add to your shell profile: export PATH=\"${bin_dir}:\$PATH\""
      ;;
  esac
  echo "Run: peerfold manuscript.pdf --reviewer RB"
}

case "${OS}" in
  Darwin) install_macos ;;
  Linux) install_linux ;;
  *)
    echo "Unsupported OS: ${OS}" >&2
    echo "Try pipx: pipx install peerfold-review" >&2
    exit 1
    ;;
esac
