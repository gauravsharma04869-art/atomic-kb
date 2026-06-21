"""
Seed atomic-server via HTTP API after server starts.
Generates an Ed25519 agent, accepts the /setup invite, and POSTs seed data.
Saves agent secret for reuse on subsequent boots.

Usage: python3 /seed_via_api.py <server_url>
"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

SEED_FILE = "/seed_backup.jsonad"
AGENT_SECRET_FILE = "/atomic-storage/agent_secret.json"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def generate_agent():
    """Generate Ed25519 keypair and return (private_key, public_key_b64, agent_subject)."""
    private_key = Ed25519PrivateKey.generate()
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_b64 = b64(public_bytes)
    return private_key, public_b64


def get_setup_invite(server_url):
    """Get the /setup invite resource, or None if not found."""
    url = f"{server_url}/setup"
    req = urllib.request.Request(url, headers={"Accept": "application/ad+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def accept_invite(server_url, public_b64):
    """Accept setup invite by GET /setup?public-key=<b64>. Returns agent URL or None."""
    params = urllib.parse.urlencode({"public-key": public_b64})
    url = f"{server_url}/setup?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/ad+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            agent = body.get("https://atomicdata.dev/properties/redirectAgent", "")
            return agent if agent else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        print(f"  [seed] Invite failed ({e.code}): {body[:200]}")
        return None
    except Exception as e:
        print(f"  [seed] Invite error: {e}")
        return None


def sign_message(private_key, message: str) -> str:
    return b64(private_key.sign(message.encode("utf-8")))


def make_auth_headers(private_key, public_b64, agent_subject):
    timestamp = str(int(time.time() * 1000))
    message = f"{agent_subject} {timestamp}"
    sig = sign_message(private_key, message)
    return {
        "x-atomic-public-key": public_b64,
        "x-atomic-signature": sig,
        "x-atomic-timestamp": timestamp,
        "x-atomic-agent": agent_subject,
        "Content-Type": "application/ad+json",
        "Accept": "application/ad+json",
    }


def post_resource(server_url, private_key, public_b64, agent_subject, resource):
    """POST a resource to its URL to create it."""
    subject = resource.get("@id", "")
    if not subject:
        return False
    name = resource.get("https://atomicdata.dev/properties/name", subject)

    body_json = json.dumps(resource)
    headers = make_auth_headers(private_key, public_b64, agent_subject)

    req = urllib.request.Request(
        subject, data=body_json.encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        if e.code == 409:
            # Already exists — not an error
            print(f"  [seed] Skipped (exists): {name}")
            return True
        desc = ""
        try:
            desc = json.loads(body).get(
                "https://atomicdata.dev/properties/description", ""
            )
        except Exception:
            desc = body[:200]
        print(f"  [seed] Failed: {name} ({e.code}): {desc[:100]}")
        return False
    except Exception as e:
        print(f"  [seed] Error: {name}: {e}")
        return False


def save_agent_secret(private_key, public_b64, agent_subject):
    """Save agent secret for reuse on subsequent boots."""
    try:
        priv_bytes = private_key.private_bytes(
            encoding=Encoding.Raw,
            format=PrivateFormat.Raw,
            encryption_algorithm=NoEncryption(),
        )
    except Exception:
        # Can't serialize, skip
        return
    secret = {
        "privateKey": b64(priv_bytes),
        "publicKey": public_b64,
        "subject": agent_subject,
    }
    try:
        os.makedirs(os.path.dirname(AGENT_SECRET_FILE), exist_ok=True)
        with open(AGENT_SECRET_FILE, "w") as f:
            json.dump(secret, f)
        print(f"  [seed] Agent secret saved to {AGENT_SECRET_FILE}")
    except Exception as e:
        print(f"  [seed] Could not save agent secret: {e}")


def load_agent_secret():
    """Load previously saved agent secret."""
    try:
        with open(AGENT_SECRET_FILE, "r") as f:
            secret = json.load(f)
        priv_b64 = secret.get("privateKey", "")
        public_b64 = secret.get("publicKey", "")
        subject = secret.get("subject", "")
        if priv_b64 and public_b64 and subject:
            private_key = Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(priv_b64)
            )
            print(f"  [seed] Loaded existing agent: {subject}")
            return private_key, public_b64, subject
    except Exception:
        pass
    return None, None, None


def main():
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9883"
    print(f"[seed] Seeding data at {server_url}")

    # Check seed file exists
    if not os.path.exists(SEED_FILE):
        print("[seed] No seed file found, skipping")
        return

    # Load seed data
    with open(SEED_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("http://localhost:10000", server_url)
    resources = json.loads(content)
    print(f"[seed] Loaded {len(resources)} resources from seed file")

    # Try to load existing agent, or create new one
    private_key, public_b64, agent_subject = load_agent_secret()

    if private_key is None:
        print("[seed] No existing agent, creating new one...")
        # Generate keys
        private_key, public_b64 = generate_agent()

        # Check invite
        invite = get_setup_invite(server_url)
        if invite is None:
            print("[seed] No /setup invite found, skipping")
            return

        usages = invite.get(
            "https://atomicdata.dev/properties/invite/usagesLeft", 0
        )
        if usages < 1:
            print("[seed] Invite has no usages left, skipping")
            return

        # Accept invite
        print("[seed] Accepting setup invite...")
        agent_url = accept_invite(server_url, public_b64)
        if not agent_url:
            print("[seed] Failed to accept invite")
            return
        agent_subject = agent_url
        print(f"[seed] Agent created: {agent_subject}")

        # Save agent secret
        save_agent_secret(private_key, public_b64, agent_subject)

    # POST each resource
    print(f"[seed] Posting {len(resources)} resources...")
    success = 0
    failed = 0
    for i, resource in enumerate(resources):
        ok = post_resource(
            server_url, private_key, public_b64, agent_subject, resource
        )
        if ok:
            success += 1
        else:
            failed += 1
            if failed >= 5:
                print("  [seed] Too many failures, stopping")
                break

    print(f"[seed] Done: {success} OK, {failed} failed")


if __name__ == "__main__":
    main()
