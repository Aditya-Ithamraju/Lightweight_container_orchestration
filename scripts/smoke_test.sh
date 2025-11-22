#!/usr/bin/env bash
# Simple smoke test: list nodes, deploy, poll agent for container endpoint
LEADER=${1:-127.0.0.1:8000}
echo "Nodes:"
curl -s http://$LEADER/nodes | jq

echo "Deploying test-app (this may fail if image isn't available on agent)"
./scripts/deploy_test.sh $LEADER docker.io/library/mini/test-app:latest miniapp
