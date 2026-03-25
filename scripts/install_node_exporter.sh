#!/bin/bash
# Run on remote server via SSH to install node_exporter
set -e

NODE_EXPORTER_VERSION="1.8.0"
ARCH="linux-amd64"

echo "[node_exporter] Installing v${NODE_EXPORTER_VERSION}..."

cd /tmp
wget -q "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz"
tar xf "node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}.tar.gz"
sudo mv "node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}/node_exporter" /usr/local/bin/
rm -rf "node_exporter-${NODE_EXPORTER_VERSION}.${ARCH}"*

# Create systemd service
sudo tee /etc/systemd/system/node_exporter.service > /dev/null << 'SERVICE'
[Unit]
Description=Node Exporter
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/node_exporter
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter

echo "[node_exporter] Installed and running on :9100"
