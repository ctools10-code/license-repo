import os
import json
import datetime
import hashlib
import requests
import jwt
from flask import Flask, request, jsonify
from filelock import FileLock

# ===== Settings via environment variables =====
GUMROAD_PRODUCT_ID = os.environ.get("GUMROAD_PRODUCT_ID", "").strip()
PRIVATE_KEY_PEM = os.environ.get("PRIVATE_KEY_PEM", "").encode()  # RSA private key (PEM)
TOKEN_YEARS = int(os.environ.get("TOKEN_YEARS", "3"))  # token expiration (years)
DATA_FILE = os.environ.get("DATA_FILE", "licenses.json")
LOCK_FILE = DATA_FILE + ".lock"

app = Flask(__name__)

# ===== Helpers for JSON storage (simple & free) =====
def _ensure_store():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            f.write("{}")

def load_store():
    _ensure_store()
    with FileLock(LOCK_FILE, timeout=10):
        with open(DATA_FILE, "r") as f:
            raw = f.read().strip()
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

def save_store(data: dict):
    tmp = DATA_FILE + ".tmp"
    with FileLock(LOCK_FILE, timeout=10):
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, DATA_FILE)

def verify_with_gumroad(license_key: str) -> bool:
    """Call Gumroad /v2/licenses/verify"""
    try:
        r = requests.post(
            "https://api.gumroad.com/v2/licenses/verify",
            data={"product_id": GUMROAD_PRODUCT_ID, "license_key": license_key},
            timeout=12
        )
        data = r.json()
        return bool(data.get("success"))
    except Exception:
        return False

def sign_token(license_key: str, hwid: str) -> str:
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=365 * TOKEN_YEARS)
    payload = {
        "license_key": license_key,
        "hwid": hwid,
        "exp": exp,
        "iss": "ctools-license-server"
    }
    token = jwt.encode(payload, PRIVATE_KEY_PEM, algorithm="RS256")
    return token

@app.route("/")
def root():
    return jsonify({"ok": True, "msg": "License server running"})

@app.route("/activate", methods=["POST"])
def activate():
    # Accept form or JSON
    license_key = request.form.get("license_key") or (request.json or {}).get("license_key")
    hwid = request.form.get("hwid") or (request.json or {}).get("hwid")
    if not license_key or not hwid:
        return jsonify({"status": "error", "message": "Missing license_key or hwid"}), 400
    if not GUMROAD_PRODUCT_ID:
        return jsonify({"status": "error", "message": "Server misconfigured: GUMROAD_PRODUCT_ID missing"}), 500
    if not PRIVATE_KEY_PEM:
        return jsonify({"status": "error", "message": "Server misconfigured: PRIVATE_KEY_PEM missing"}), 500

    # Verify Gumroad license
    if not verify_with_gumroad(license_key):
        return jsonify({"status": "error", "message": "Invalid or unknown Gumroad license"}), 403

    # Bind or validate binding
    store = load_store()
    bound = store.get(license_key)
    if bound is None:
        # First activation → bind
        store[license_key] = hwid
        save_store(store)
    else:
        if bound != hwid:
            return jsonify({"status": "error", "message": "License already in use on another device"}), 403

    # Signed token (client can use offline)
    token = sign_token(license_key, hwid)
    return jsonify({"status": "activated", "token": token})

@app.route("/check", methods=["POST"])
def check():
    token = request.form.get("token") or (request.json or {}).get("token")
    hwid = request.form.get("hwid") or (request.json or {}).get("hwid")
    if not token or not hwid:
        return jsonify({"status": "error", "message": "Missing token or hwid"}), 400

    try:
        data = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
    except Exception:
        return jsonify({"status": "error", "message": "Unreadable token"}), 400

    # Optional: also verify binding on server-side store (prevents tampering)
    store = load_store()
    bound = store.get(data.get("license_key"))
    if not bound or bound != hwid:
        return jsonify({"status": "error", "message": "HWID mismatch or not bound"}), 403

    # Full signature verify with private key not needed here; the client does RS256 verify with public key.
    # But you can still verify here if you want, using PRIVATE_KEY_PEM (not necessary for server).
    return jsonify({"status": "valid"})

if __name__ == "__main__":
    # Local run
    app.run(host="0.0.0.0", port=5000)
