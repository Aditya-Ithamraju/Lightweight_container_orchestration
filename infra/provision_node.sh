#!/usr/bin/env bash
# Run inside VM via: multipass exec <vm> -- bash -s < infra/provision_node.sh
set -e

sudo apt update && sudo apt upgrade -y
sudo apt install -y curl gnupg lsb-release apt-transport-https ca-certificates

# Install containerd (simple apt way)
sudo apt install -y containerd

# start and enable containerd
sudo systemctl enable --now containerd

# Install Python & tools
sudo apt install -y python3 python3-venv python3-pip

# Install psutil (used by agent)
sudo pip3 install psutil requests flask

# Create project dir placeholder
mkdir -p ~/edge-mini-k8s
echo "Provisioning done. Copy your project into ~/edge-mini-k8s"
