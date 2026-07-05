#!/usr/bin/env bash
# Block private/local artifacts from commits and CI merges.
# Path rules: .gitignore is canonical; this script adds .cache/* only (symlink ceiling).
# See docs/development.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="commit"
CHECK_PATH=""
SCAN_DIFF_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ci)
      MODE=ci
      shift
      ;;
    --push)
      MODE=push
      shift
      ;;
    --check-path)
      CHECK_PATH="${2:-}"
      if [[ -z "$CHECK_PATH" ]]; then
        echo "usage: $0 --check-path <path>" >&2
        exit 2
      fi
      shift 2
      ;;
    --scan-diff-file)
      SCAN_DIFF_FILE="${2:-}"
      if [[ -z "$SCAN_DIFF_FILE" || ! -f "$SCAN_DIFF_FILE" ]]; then
        echo "usage: $0 --scan-diff-file <file>" >&2
        exit 2
      fi
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

path_is_forbidden() {
  local path="$1"

  # ponytail: .cache/* — git check-ignore fails on symlinked .cache/frida
  case "$path" in
    .cache/*) return 0 ;;
  esac

  git check-ignore -q "$path" 2>/dev/null
}

resolve_diff_range() {
  case "$MODE" in
    commit)
      echo --cached
      ;;
    ci)
      if git rev-parse --verify origin/main >/dev/null 2>&1; then
        echo origin/main...HEAD
      elif git rev-parse --verify main >/dev/null 2>&1; then
        echo main...HEAD
      else
        echo HEAD~1...HEAD
      fi
      ;;
    push)
      if git rev-parse --verify @{push} >/dev/null 2>&1; then
        echo @{push}..HEAD
      elif git rev-parse --verify origin/main >/dev/null 2>&1; then
        echo origin/main...HEAD
      else
        echo HEAD~1...HEAD
      fi
      ;;
    *)
      echo "unknown mode: $MODE" >&2
      exit 2
      ;;
  esac
}

collect_paths() {
  local range
  range="$(resolve_diff_range)"
  if [[ "$range" == --cached ]]; then
    git diff --cached --name-only --diff-filter=ACMR
  else
    git diff --name-only --diff-filter=ACMR "$range"
  fi
}

collect_grpc_json_diff() {
  local range path grpc_paths=()
  range="$(resolve_diff_range)"

  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    case "$path" in
      scripts/grpc/*.json) grpc_paths+=("$path") ;;
    esac
  done < <(collect_paths | sort -u)

  ((${#grpc_paths[@]} == 0)) && return 0

  if [[ "$range" == --cached ]]; then
    git diff --cached --diff-filter=ACMR -U0 -- "${grpc_paths[@]}"
  else
    git diff "$range" --diff-filter=ACMR -U0 -- "${grpc_paths[@]}"
  fi
}

is_placeholder_value() {
  local key="$1"
  local value="$2"

  case "$key" in
    session_key)
      [[ "$value" =~ ^0+$ ]]
      return
      ;;
    hmac_key)
      [[ "$value" =~ ^1+$ ]]
      return
      ;;
    device_id | key_id)
      [[ "$value" == "00000000-0000-0000-0000-000000000001" || "$value" == "00000000-0000-0000-0000-000000000002" ]]
      return
      ;;
    refresh_token | access_token)
      [[ -z "$value" || "$value" == "REDACTED" || "$value" == "example" ]]
      return
      ;;
  esac

  return 1
}

scan_secrets_in_diff() {
  local diff_file="$1"
  local line key value
  local found=0

  while IFS= read -r line; do
    [[ "$line" != +* ]] && continue
    line="${line#+}"

    if [[ "$line" =~ \"(session_key|hmac_key|refresh_token|access_token|device_id|key_id)\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]]; then
      key="${BASH_REMATCH[1]}"
      value="${BASH_REMATCH[2]}"
      if ! is_placeholder_value "$key" "$value"; then
        echo "credential-like JSON field \"$key\" in added lines"
        found=1
      fi
    fi
  done <"$diff_file"

  return "$found"
}

main() {
  if [[ -n "$CHECK_PATH" ]]; then
    if path_is_forbidden "$CHECK_PATH"; then
      exit 1
    fi
    exit 0
  fi

  if [[ -n "$SCAN_DIFF_FILE" ]]; then
    scan_secrets_in_diff "$SCAN_DIFF_FILE"
    exit $?
  fi

  local paths=()
  local path
  local forbidden=()
  local diff_file
  local secret_hits=()

  mapfile -t paths < <(collect_paths | sort -u)

  for path in "${paths[@]}"; do
    [[ -z "$path" ]] && continue
    if path_is_forbidden "$path"; then
      forbidden+=("$path")
    fi
  done

  diff_file="$(mktemp)"
  trap 'rm -f "$diff_file"' EXIT
  collect_grpc_json_diff >"$diff_file"

  mapfile -t secret_hits < <(scan_secrets_in_diff "$diff_file" || true)

  if ((${#forbidden[@]} == 0)) && ((${#secret_hits[@]} == 0)); then
    exit 0
  fi

  echo "error: private/local artifacts must not be committed or pushed." >&2
  echo >&2

  if ((${#forbidden[@]} > 0)); then
    echo "Forbidden paths:" >&2
    printf '  - %s\n' "${forbidden[@]}" >&2
    echo >&2
    echo "Unstage with: git reset HEAD -- <path>" >&2
    echo >&2
  fi

  if ((${#secret_hits[@]} > 0)); then
    echo "Credential-shaped content in scripts/grpc/*.json:" >&2
    printf '  - %s\n' "${secret_hits[@]}" >&2
    echo >&2
  fi

  echo "See docs/development.md." >&2
  exit 1
}

main
