from flask import Flask, jsonify
app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify({"status": "alive"}), 200

@app.get("/")
def root():
    return jsonify({"service": "runtime"}), 200
