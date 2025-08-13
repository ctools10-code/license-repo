from flask import Flask, request, jsonify
import json, os, requests

app = Flask(__name__)

DB_FILE = "licenses.json"
GUMROAD_PRODUCT_ID = "OB0SQvGWsL_FFse_Jf5lOQ=="

# Load database
if os.path.exists(DB_FILE):
    with open(DB_FILE) as f:
        licenses = json.load(f)
else:
    licenses = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(licenses, f)

@app.route("/check")
def check_license():
    key = request.args.get("license_key")
    hwid = request.args.get("hwid")

    if key in licenses:
        if licenses[key] == hwid:
            return jsonify({"status": "valid"})
        else:
            return jsonify({"status": "invalid"})
    else:
        return jsonify({"status": "not_activated"})

@app.route("/activate")
def activate_license():
    key = request.args.get("license_key")
    hwid = request.args.get("hwid")

    # Verify with Gumroad
    r = requests.post("https://api.gumroad.com/v2/licenses/verify", data={
        "product_id": GUMROAD_PRODUCT_ID,
        "license_key": key
    })
    gumroad_data = r.json()

    if not gumroad_data.get("success"):
        return jsonify({"status": "invalid_key"})

    licenses[key] = hwid
    save_db()
    return jsonify({"status": "activated"})

@app.route("/")
def home():
    return "License server is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
