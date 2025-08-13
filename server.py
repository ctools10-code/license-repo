from flask import Flask, request, jsonify
import json
import os

app = Flask(__name__)

DATA_FILE = "licenses.json"

# Load licenses
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        licenses = json.load(f)
else:
    licenses = {}

@app.route("/check_license", methods=["POST"])
def check_license():
    data = request.json
    license_key = data.get("license_key")
    hwid = data.get("hardware_id")

    if license_key not in licenses:
        # New license → store it
        licenses[license_key] = hwid
        save_data()
        return jsonify({"success": True, "message": "License bound to this PC"})

    if licenses[license_key] == hwid:
        return jsonify({"success": True, "message": "Valid license"})

    return jsonify({"success": False, "message": "License already used on another PC"})

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(licenses, f)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
