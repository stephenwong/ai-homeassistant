#!/bin/bash
# Wrapper for curl to Home Assistant API
# Usage: tools/ha-curl.sh [curl options] <endpoint>
# Example: tools/ha-curl.sh -X POST /api/states/sensor.test -d '{"state": "on"}'

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../.env"

if [ -z "$HA_URL" ] || [ -z "$HA_TOKEN" ]; then
    echo "Error: HA_URL and HA_TOKEN must be set in .env" >&2
    exit 1
fi

# Extract endpoint (last argument that starts with /)
args=()
endpoint=""
for arg in "$@"; do
    if [[ "$arg" == /* ]]; then
        endpoint="$arg"
    else
        args+=("$arg")
    fi
done

if [ -z "$endpoint" ]; then
    echo "Error: No endpoint provided (must start with /)" >&2
    exit 1
fi

curl -s "${args[@]}" "${HA_URL}${endpoint}" \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    -H "Content-Type: application/json"
