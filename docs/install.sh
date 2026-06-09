#!/usr/bin/env bash
# PeerFold installer — macOS and Linux. Fetches the latest GitHub release.
set -euo pipefail

REPO="vincenzoml/PeerFold"
BASE_URL="https://github.com/${REPO}/releases/latest/download"

if ! command -v curl >/dev/null 2>&1; then
  echo "PeerFold install requires curl." >&2
  exit 1
fi

OS="$(uname -s)"

install_macos() {
  if ! command -v hdiutil >/dev/null 2>&1; then
    echo "PeerFold macOS install requires hdiutil." >&2
    exit 1
  fi

  local tmp mount_point dest apps_dir
  tmp="$(mktemp -d)"
  mount_point="${tmp}/mount"
  mkdir -p "$mount_point"

  cleanup() {
    if [[ -n "${mount_point:-}" && -d "${mount_point}/PeerFold.app" ]]; then
      hdiutil detach "$mount_point" -quiet 2>/dev/null || true
    fi
    if [[ -n "${tmp:-}" && -d "${tmp}" ]]; then
      rm -rf "$tmp"
    fi
  }
  trap cleanup EXIT

  echo "Downloading PeerFold for macOS…"
  curl -fsSL -o "${tmp}/peerfold.dmg" "${BASE_URL}/peerfold-macos.dmg"
  hdiutil attach -nobrowse -quiet -mountpoint "$mount" "${tmp}/peerfold.dmg"

  if [[ ! -d "${mount}/PeerFold.app" ]]; then
    echo "PeerFold.app not found in disk image." >&2
    exit 1
  fi

  if [[ -w /Applications ]]; then
    apps_dir="/Applications"
  else
    apps_dir="${HOME}/Applications"
    mkdir -p "$apps_dir"
  fi
  dest="${apps_dir}/PeerFold.app"
  rm -rf "$dest"
  cp -R "${mount}/PeerFold.app" "$dest"

  echo "Installed PeerFold to ${dest}"
  echo "Open PeerFold from Applications and choose your PDF."
}

install_linux() {
  local bin_dir dest
  bin_dir="${PEERFOLD_BIN_DIR:-${HOME}/.local/bin}"
  mkdir -p "$bin_dir"
  dest="${bin_dir}/peerfold"

  echo "Downloading PeerFold for Linux…"
  curl -fsSL -o "$dest" "${BASE_URL}/peerfold-linux"
  chmod +x "$dest"

  echo "Installed peerfold to ${dest}"
  case ":${PATH}:" in
    *":${bin_dir}:"*) ;;
    *)
      echo "Add to your shell profile: export PATH=\"${bin_dir}:\$PATH\""
      ;;
  esac
  echo "Run: peerfold manuscript.pdf --reviewer RB"
}

case "$OS" in
  Darwin) install_macos ;;
  Linux) install_linux ;;
  *)
    echo "Unsupported OS: ${OS}" >&2
    echo "Try pipx: pipx install peerfold-review" >&2
    exit 1
    ;;
esac
