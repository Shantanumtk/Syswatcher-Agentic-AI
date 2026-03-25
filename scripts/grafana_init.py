#!/usr/bin/env python3
"""
Creates a Grafana service account + token.
Writes GRAFANA_TOKEN to .env so agent can post annotations.
Run once after Grafana starts healthy.
"""
import os
import sys
import time
import requests

GRAFANA_URL  = os.getenv("GRAFANA_URL", "http://localhost:3000")
ADMIN_PASS   = os.getenv("GRAFANA_ADMIN_PASSWORD", "admin123")
AUTH         = ("admin", ADMIN_PASS)

def wait_for_grafana(timeout: int = 120):
    print("Waiting for Grafana...")
    waited = 0
    while waited < timeout:
        try:
            r = requests.get(f"{GRAFANA_URL}/api/health", timeout=5)
            if r.status_code == 200:
                print("Grafana is ready")
                return True
        except Exception:
            pass
        time.sleep(5)
        waited += 5
        print(f"  Still waiting... ({waited}s)")
    print("ERROR: Grafana did not become ready")
    return False

def create_service_account() -> int:
    # Check if already exists
    r = requests.get(
        f"{GRAFANA_URL}/api/serviceaccounts/search?query=syswatcher",
        auth=AUTH, timeout=10,
    )
    if r.status_code == 200:
        accounts = r.json().get("serviceAccounts", [])
        for acc in accounts:
            if acc["name"] == "syswatcher-agent":
                print(f"Service account exists: id={acc['id']}")
                return acc["id"]

    # Create new
    r = requests.post(
        f"{GRAFANA_URL}/api/serviceaccounts",
        auth=AUTH,
        json={"name": "syswatcher-agent", "role": "Editor"},
        timeout=10,
    )
    if r.status_code in (200, 201):
        acc_id = r.json()["id"]
        print(f"Service account created: id={acc_id}")
        return acc_id

    print(f"ERROR creating service account: {r.status_code} {r.text}")
    sys.exit(1)

def create_token(acc_id: int) -> str:
    r = requests.post(
        f"{GRAFANA_URL}/api/serviceaccounts/{acc_id}/tokens",
        auth=AUTH,
        json={"name": "syswatcher-token"},
        timeout=10,
    )
    if r.status_code in (200, 201):
        token = r.json()["key"]
        print(f"Token created: {token[:20]}...")
        return token

    # Token may already exist — delete and recreate
    if r.status_code == 409:
        tokens_r = requests.get(
            f"{GRAFANA_URL}/api/serviceaccounts/{acc_id}/tokens",
            auth=AUTH, timeout=10,
        )
        for tok in tokens_r.json():
            if tok["name"] == "syswatcher-token":
                requests.delete(
                    f"{GRAFANA_URL}/api/serviceaccounts/{acc_id}/tokens/{tok['id']}",
                    auth=AUTH, timeout=10,
                )
        return create_token(acc_id)

    print(f"ERROR creating token: {r.status_code} {r.text}")
    sys.exit(1)

def write_token_to_env(token: str):
    env_path = ".env"
    if not os.path.exists(env_path):
        print("WARNING: .env not found — writing token to stdout only")
        print(f"GRAFANA_TOKEN={token}")
        return

    with open(env_path) as f:
        lines = f.readlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith("GRAFANA_TOKEN="):
            new_lines.append(f"GRAFANA_TOKEN={token}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"\nGRAFANA_TOKEN={token}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    print(f"GRAFANA_TOKEN written to {env_path}")

if __name__ == "__main__":
    if not wait_for_grafana():
        sys.exit(1)

    acc_id = create_service_account()
    token  = create_token(acc_id)
    write_token_to_env(token)
    print("Grafana init complete")
