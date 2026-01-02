from flask import Flask, request, render_template, send_file, redirect, url_for, flash
import yt_dlp
import tempfile
import os
import shutil
import threading
import uuid
import zipfile
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", str(uuid.uuid4()))

# Allowed hostnames for prioritized platforms
ALLOWED_HOSTS = {
    "instagram.com", "www.instagram.com", "instagr.am",
    "tiktok.com", "www.tiktok.com", "m.tiktok.com",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
    "facebook.com", "www.facebook.com", "fb.watch",
    "youtube.com", "www.youtube.com", "youtu.be",
}

# Simple max download size check (bytes) to avoid huge files (example: 200 MB)
MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_DOWNLOAD_BYTES", 200 * 1024 * 1024))

def cleanup_later(path, delay=30):
    def _cleanup():
        try:
            import time
            time.sleep(delay)
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass
    threading.Thread(target=_cleanup, daemon=True).start()

def is_allowed_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host = host.lower()
        return host in ALLOWED_HOSTS
    except Exception:
        return False

def detect_platform(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host or "instagr.am" in host:
        return "instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "twitter.com" in host or "x.com" in host:
        return "x"
    if "facebook.com" in host or "fb.watch" in host:
        return "facebook"
    return "unknown"

def ydl_options_for(platform: str, choice: str, outtmpl: str):
    # choice: "video", "audio", "best"
    opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
    }

    if choice == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    elif choice == "video":
        opts["format"] = "bv[ext=mp4]+ba[ext=m4a]/bestvideo+bestaudio/best"
    else:
        opts["format"] = "best"

    opts.setdefault("http_headers", {})
    opts["http_headers"]["User-Agent"] = "Mozilla/5.0 (compatible; Joomax-Downloader/1.0)"
    return opts

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url", "").strip()
    choice = request.form.get("choice", "video")
    if not url:
        flash("Masukkan URL terlebih dahulu.")
        return redirect(url_for("index"))

    if not is_allowed_url(url):
        flash("URL tidak termasuk platform yang didukung atau domain tidak diizinkan.")
        return redirect(url_for("index"))

    platform = detect_platform(url)
    tempdir = tempfile.mkdtemp(prefix="download_")
    outtmpl = os.path.join(tempdir, "%(title)s.%(ext)s")

    ydl_opts = ydl_options_for(platform, choice, outtmpl)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # collect downloaded files
        files = []
        total_bytes = 0
        for root, _, filenames in os.walk(tempdir):
            for fn in filenames:
                fp = os.path.join(root, fn)
                try:
                    size = os.path.getsize(fp)
                except OSError:
                    size = 0
                total_bytes += size
                files.append(fp)

        if total_bytes > MAX_DOWNLOAD_BYTES:
            shutil.rmtree(tempdir, ignore_errors=True)
            flash("File terlalu besar. Batas unduhan: {} MB".format(MAX_DOWNLOAD_BYTES // (1024*1024)))
            return redirect(url_for("index"))

        if not files:
            shutil.rmtree(tempdir, ignore_errors=True)
            flash("Tidak ada file yang berhasil diunduh dari URL tersebut.")
            return redirect(url_for("index"))

        if len(files) == 1:
            file_path = files[0]
            filename = os.path.basename(file_path)
            cleanup_later(tempdir, delay=30)
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            zip_path = os.path.join(tempdir, "media_bundle.zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, arcname=os.path.basename(f))
            cleanup_later(tempdir, delay=30)
            return send_file(zip_path, as_attachment=True, download_name="media_bundle.zip")
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(tempdir, ignore_errors=True)
        flash(f"Gagal mengunduh: {e}")
        return redirect(url_for("index"))
    except Exception as e:
        shutil.rmtree(tempdir, ignore_errors=True)
        flash(f"Terjadi kesalahan: {e}")
        return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))