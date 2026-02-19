#!/usr/bin/env bash
set -euo pipefail

CLIENT_ID="${GITHUB_CLIENT_ID:-Iv1.b507a08c87ecfe98}"
SCOPE="${GITHUB_SCOPE:-read:user}"
ENV_FILE="${1:-.env}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

json_get() {
  local key="$1"
  python3 -c '
import json
import sys

key = sys.argv[1]
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception:
    print("")
    raise SystemExit(0)
value = data.get(key, "")
if value is None:
    value = ""
if isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
' "$key"
}

upsert_env_key() {
  local key="$1"
  local value="$2"
  local file="$3"

  touch "$file"
  if grep -q "^${key}=" "$file"; then
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" '
      BEGIN { done = 0 }
      $0 ~ ("^" k "=") {
        if (!done) {
          print k "=" v
          done = 1
        }
        next
      }
      { print }
      END {
        if (!done) print k "=" v
      }
    ' "$file" >"$tmp"
    mv "$tmp" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >>"$file"
  fi
}

poll_access_token() {
  local device_code="$1"
  local interval="$2"

  while true; do
    local poll_resp token err
    poll_resp="$(curl -fsS https://github.com/login/oauth/access_token \
      -H 'Accept: application/json' \
      -H 'Content-Type: application/json' \
      -d "{\"client_id\":\"${CLIENT_ID}\",\"device_code\":\"${device_code}\",\"grant_type\":\"urn:ietf:params:oauth:grant-type:device_code\"}")"

    token="$(printf '%s' "$poll_resp" | json_get access_token)"
    if [[ -n "$token" ]]; then
      printf '%s\n' "$token"
      return 0
    fi

    err="$(printf '%s' "$poll_resp" | json_get error)"
    case "$err" in
      authorization_pending)
        ;;
      slow_down)
        interval=$((interval + 5))
        ;;
      access_denied)
        echo "Authorization denied by user." >&2
        return 1
        ;;
      expired_token)
        echo "Device code expired. Re-run the script." >&2
        return 1
        ;;
      *)
        if [[ -n "$err" ]]; then
          echo "OAuth polling error: $err" >&2
          return 1
        fi
        ;;
    esac
    sleep "$interval"
  done
}

require_cmd curl
require_cmd python3

echo "Requesting GitHub device code..."
device_resp="$(curl -fsS https://github.com/login/device/code \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"${CLIENT_ID}\",\"scope\":\"${SCOPE}\"}")"

device_code="$(printf '%s' "$device_resp" | json_get device_code)"
user_code="$(printf '%s' "$device_resp" | json_get user_code)"
verify_url="$(printf '%s' "$device_resp" | json_get verification_uri)"
interval="$(printf '%s' "$device_resp" | json_get interval)"

if [[ -z "$device_code" || -z "$user_code" || -z "$verify_url" ]]; then
  echo "Failed to get device code response: $device_resp" >&2
  exit 1
fi
if [[ -z "$interval" ]]; then
  interval=5
fi

echo
echo "Open this URL and enter the code:"
echo "  URL : $verify_url"
echo "  Code: $user_code"
echo
echo "Waiting for authorization..."

token="$(poll_access_token "$device_code" "$interval")"
upsert_env_key "GITHUB_TOKEN" "$token" "$ENV_FILE"

echo
echo "GITHUB_TOKEN updated in $ENV_FILE"
echo "Token preview: ${token:0:8}..."
