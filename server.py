import os
import json
import datetime
import hashlib
import requests
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify

# ===== Settings via environment variables =====
GUMROAD_PRODUCT_ID = os.environ.get("GUMROAD_PRODUCT_ID", "").strip()
PRIVATE_KEY_PEM = os.environ.get("PRIVATE_KEY_PEM", "").encode()
TOKEN_YEARS = int(os.environ.get("TOKEN_YEARS", "3"))
DATABASE_URL = os.environ.get("DATABASE_URL")

app = Flask(__name__)

# ===== Database helpers =====
def init_db():
    """Create table if not exists"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            hwid TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def load_store():
    """Load all licenses into a dict {license_key: hwid}"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    cur.execute("SELECT license_key, hwid FROM licenses")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {row["license_key"]: row["hwid"] for row in rows}

def save_store(data: dict):
    """Replace all licenses in DB with given dict"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("TRUNCATE licenses")
    for license_key, hwid in data.items():
        cur.execute(
            "INSERT INTO licenses (license_key, hwid) VALUES (%s, %s)",
            (license_key, hwid)
        )
    conn.commit()
    cur.close()
    conn.close()

# ===== Gumroad check =====
def verify_with_gumroad(license_key: str) -> bool:
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
    license_key = request.form.get("license_key") or (request.json or {}).get("license_key")
    hwid = request.form.get("hwid") or (request.json or {}).get("hwid")
    if not license_key or not hwid:
        return jsonify({"status": "error", "message": "Missing license_key or hwid"}), 400
    if not GUMROAD_PRODUCT_ID:
        return jsonify({"status": "error", "message": "Server misconfigured: GUMROAD_PRODUCT_ID missing"}), 500
    if not PRIVATE_KEY_PEM:
        return jsonify({"status": "error", "message": "Server misconfigured: PRIVATE_KEY_PEM missing"}), 500

    if not verify_with_gumroad(license_key):
        return jsonify({"status": "error", "message": "Invalid or unknown Gumroad license"}), 403

    store = load_store()
    bound = store.get(license_key)
    if bound is None:
        store[license_key] = hwid
        save_store(store)
    else:
        if bound != hwid:
            return jsonify({"status": "error", "message": "License already in use on another device"}), 403

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

    store = load_store()
    bound = store.get(data.get("license_key"))
    if not bound or bound != hwid:
        return jsonify({"status": "error", "message": "HWID mismatch or not bound"}), 403

    return jsonify({"status": "valid"})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)

