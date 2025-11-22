#!/usr/bin/env bash
# Usage: scripts/deploy_test.sh <leader_ip:port>
LEADER=${1:-127.0.0.1:8000}
IMAGE=${2:-docker.io/library/python:3.10-slim}
NAME=${3:-mini-test}

JSON=$(cat <<EOF
{
  "image": "$IMAGE",
  "name": "$NAME",
  "port": 5000,
  "resources": {"cpu": 0.05, "mem_mb": 30, "min_energy": 10}
}
EOF
)

echo "Sending deploy to leader $LEADER ..."
time curl -s -X POST http://$LEADER/deploy -H "Content-Type: application/json" -d "$JSON" | jq
