#!/usr/bin/env bash
# Launch tiny multipass VMs for leader + 3 edge nodes
# Usage: infra/launch_cluster.sh

set -e

LEADER_NAME="leader"
EDGE_PREFIX="edge"
EDGE_COUNT=3

echo "Launching leader..."
multipass launch jammy --name $LEADER_NAME --cpus 2 --mem 4G --disk 10G

for i in $(seq 1 $EDGE_COUNT); do
  NAME="${EDGE_PREFIX}${i}"
  echo "Launching ${NAME}..."
  multipass launch jammy --name $NAME --cpus 1 --mem 512M --disk 4G
done

echo "All VMs launched. Run infra/provision_node.sh on each VM using multipass exec."
