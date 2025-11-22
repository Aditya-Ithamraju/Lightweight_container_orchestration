# test-app/app.py
from flask import Flask, jsonify
import time, os

app = Flask(__name__)
start = time.time()

@app.route("/")
def root():
    return jsonify({
        "msg": "hello from test-app",
        "uptime_s": round(time.time() - start, 2),
        "host": os.uname().nodename
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
