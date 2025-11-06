import os
import subprocess
import json
import re
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# === CONFIG ===
API_KEY = os.getenv("API_KEY", "420679f1-73e2-42a0-bbea-a10b99bd5fde")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

# === AUTO CLEANUP ===
def auto_cleanup():
    while True:
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(path) and now - os.path.getmtime(path) > 300:
                os.remove(path)
        time.sleep(300)

threading.Thread(target=auto_cleanup, daemon=True).start()

# === UTILS ===
def clean_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()[:180] or "audio"

def clean_url(url: str) -> str:
    url = re.sub(r"&list=[^&]+", "", url)
    url = re.sub(r"&start_radio=\\d+", "", url)
    url = re.sub(r"&index=\\d+", "", url)
    return url.strip()

# === ROUTES ===
@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/info", methods=["POST"])
def api_info():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing URL"}), 400

    url = clean_url(url)
    try:
        cmd = [
            "yt-dlp", "--no-warnings", "--skip-download",
            "--extractor-args", "youtubetab:skip=authcheck",
            "--cookies", "cookies.txt", "-j", url
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if not result.stdout.strip():
            raise RuntimeError("yt-dlp returned no output")

        info = json.loads(result.stdout.strip().split("\n")[0])
        title = info.get("title", "Unknown Title")
        thumb = info.get("thumbnail", "")

        return jsonify({
            "title": title,
            "thumbnail": thumb,
            "qualities": [{
                "label": "🎵 Download Best Quality (MP3)",
                "type": "mp3",
                "url": url
            }]
        })

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout: YouTube took too long to respond"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["POST"])
def api_download():
    if request.headers.get("X-API-Key") != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403

    data = request.get_json() or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing URL"}), 400

    url = clean_url(url)
    try:
        info_cmd = [
            "yt-dlp", "--no-warnings", "--skip-download",
            "--cookies", "cookies.txt", "-j", url
        ]
        info_proc = subprocess.run(info_cmd, capture_output=True, text=True, timeout=180)
        info = json.loads(info_proc.stdout.strip().split("\n")[0])
        title = clean_filename(info.get("title", "audio"))
        filename = f"{title}.mp3"
        out_path = os.path.join(DOWNLOAD_DIR, filename)

        cmd = [
            "yt-dlp", "--extract-audio", "--audio-format", "mp3",
            "--audio-quality", "0",  # best quality
            "--cookies", "cookies.txt",
            "-o", out_path, url
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)

        if not os.path.exists(out_path):
            raise FileNotFoundError("Download failed")

        return jsonify({"download_url": f"/downloads/{filename}"})

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout while downloading audio"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    print("\n✅ MP3 Server ready!")
    print(f"API Key: {API_KEY}")
    print(f"  info: http://localhost:5000/api/info")
    print(f"  download: http://localhost:5000/api/download\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
