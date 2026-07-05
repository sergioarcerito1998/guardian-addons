#!/usr/bin/with-contenv bashio

set -e

export HA_URL="http://supervisor/core"
export HA_TOKEN="${SUPERVISOR_TOKEN}"

INTERVAL="$(bashio::config 'interval')"

mkdir -p /data

while true; do
    python3 -m connector.guardian_connector --output /data/house-passport.json
    bashio::log.info "House Passport generated successfully."
    sleep "${INTERVAL}"
done

