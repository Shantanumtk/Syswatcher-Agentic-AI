#!/usr/bin/env python3
"""
Reads .env SERVERS list, SSHs into each,
installs node_exporter if not already present.
"""
import os
import subprocess

servers_raw = os.getenv("SERVERS", "")
if not servers_raw.strip():
    print("No remote servers configured — skipping")
    exit(0)

# Parse syswatcher.conf for server details
import re

conf = {}
with open("syswatcher.conf") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            parts = val.strip().split()
            if len(parts) == 3 and re.match(r"\d+\.\d+\.\d+\.\d+", parts[0]):
                conf[key.strip()] = {"ip": parts[0], "user": parts[1], "key": parts[2]}

for name, srv in conf.items():
    print(f"Setting up {name} ({srv['ip']})...")
    try:
        result = subprocess.run([
            "ssh", "-i", srv["key"],
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{srv['user']}@{srv['ip']}",
            "command -v node_exporter && echo EXISTS || echo MISSING"
        ], capture_output=True, text=True, timeout=15)

        if "EXISTS" in result.stdout:
            print(f"  ✓ node_exporter already installed on {name}")
        else:
            subprocess.run([
                "ssh", "-i", srv["key"],
                "-o", "StrictHostKeyChecking=no",
                f"{srv['user']}@{srv['ip']}",
                "bash -s"
            ], stdin=open("scripts/install_node_exporter.sh"), timeout=120)
            print(f"  ✓ node_exporter installed on {name}")
    except Exception as e:
        print(f"  ✗ Could not reach {name}: {e}")
