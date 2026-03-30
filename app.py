from flask import Flask, request, send_file, jsonify, render_template, send_from_directory, Response
from flask_cors import CORS
from yt_dlp import YoutubeDL
import zipfile
import os
import re
from io import BytesIO
import time
import random
import threading
from queue import Queue
import json
import subprocess

def kill_all_threads():

    print("Cleaning old threads...")

    for thread in threading.enumerate():

        if thread is not threading.main_thread():

            try:
                print("Stopping:", thread.name)
            except:
                pass

kill_all_threads()

def kill_existing_download_processes():

    print("Cleaning old download processes...")

    if os.name == "nt":

        for proc in ["ffmpeg.exe", "yt-dlp.exe"]:
            subprocess.call(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

    else:

        subprocess.call(["pkill", "-f", "ffmpeg"])
        subprocess.call(["pkill", "-f", "yt-dlp"])

    print("Cleanup complete.")


kill_existing_download_processes()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD_DIR = "downloads"

download_events = Queue()
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

IMPORT_DIR = os.path.join(BASE_DIR, "import_queue")
os.makedirs(IMPORT_DIR, exist_ok=True)

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', name)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config["DOWNLOAD_FOLDER"] = "downloads"
CORS(app)
@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route("/downloads/<path:filename>")
def serve_download(filename):
    return send_from_directory(
        DOWNLOAD_DIR,
        filename,
        as_attachment=False
    )

@app.route('/playlist')
def playlist_page():
    playlist_name = request.args.get('name')
    return render_template('index.html', playlist=playlist_name)

def download_logic(url):
    print("Download started:", url)

    if not url:
        print("No URL provided")

    try:
        tmpdir = DOWNLOAD_DIR
        output_template = os.path.join(tmpdir, '%(title)s.%(ext)s')
    
        ydl_opts_base = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'js_runtimes': {
                    'node': {'path': r"C:\Program Files\nodejs\node.exe"}
                },
                'remote_components': ['ejs:github'],
                'outtmpl': output_template,
                'quiet': True,
                'ffmpeg_location': r"C:\Users\akamr\OneDrive\Documents\Music-Player-main\ffmpeg-2026-02-26-git-6695528af6-essentials_build\bin\ffmpeg.exe",
                'continuedl': True,
                'retries': 5,
                'concurrent_fragment_downloads': 5,
                'http_chunk_size': 10485760,
                'no_warnings': True,
                'nocheckcertificate': True,

                # human behaviour
                'sleep_interval': 2,
                'max_sleep_interval': 6,

                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

        # Step 1: Detect if it's a playlist and get flat list of entries
        with YoutubeDL({
            'quiet': True,
            'extract_flat': True,
            'noplaylist': False
        }) as ydl_info:

            info = ydl_info.extract_info(url, download=False)

        is_playlist = info.get("_type") == "playlist"

        print("Is playlist:", is_playlist)

        if not is_playlist:
            # Single video - download normally
            ydl_opts = ydl_opts_base.copy()
            ydl_opts['noplaylist'] = True

            with YoutubeDL(ydl_opts) as ydl:
                download_info = ydl.extract_info(url, download=True)

            filename = ydl.prepare_filename(download_info)
            mp3_filename = os.path.splitext(filename)[0] + ".mp3"

            filename_only = os.path.basename(mp3_filename)

            download_events.put({   
                "filename": filename_only
            })

            print("Added:", filename_only)

            print("Single video download completed")
            return

        else:
            # Playlist → extract video URLs only
            playlist_title = info.get('title') or info.get('playlist_title') or 'YouTube Playlist'
            entries = info['entries']

            mp3_files = []

            for entry in entries:
                if not entry or 'url' not in entry:
                    continue
                    
                video_id = entry.get("id")

                if not video_id:
                    continue

                video_url = f"https://youtube.com/watch?v={video_id}"
                    
                ydl_opts = ydl_opts_base.copy()
                ydl_opts['noplaylist'] = True

                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        ydl.extract_info(video_url, download=True)

                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=True)

                    filename = ydl.prepare_filename(info)
                    mp3_filename = os.path.splitext(filename)[0] + ".mp3"

                    file_only = os.path.basename(mp3_filename)

                    # prevent duplicates
                    if mp3_filename not in mp3_files:

                        mp3_files.append(mp3_filename)

                        download_events.put({
                            "filename": file_only
                        })

                        print("Added:", file_only)

                    wait = random.randint(2,5)
                    print("Downloading:", video_url)
                    print("Resting",wait,"seconds")
                    time.sleep(wait) # ← delay between downloads (adjust 1.5–4 sec)

                    if len(mp3_files) % 5 == 0:
                        long_rest = random.randint(15,30)
                        print("Cooldown:", long_rest)
                        time.sleep(long_rest)

                except Exception as inner_e:
                    print(f"Skipped video {video_url}: {inner_e}")
                    continue  # skip failed ones, don't crash whole process

                if not mp3_files:
                    print("No MP3 files generated from playlist")

            print("Playlist download completed")
            return

    except Exception as e:
        print("Download error:", e)
    
@app.route('/download', methods=['POST'])
def download():
    url = request.json["url"]

    threading.Thread(
        target=download_logic,
        args=(url,),
        daemon=True
    ).start()

    return jsonify({"status":"started"})

@app.route("/download-events")
def download_events_stream():

    def stream():
        while True:
            event = download_events.get()
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        stream(),
        mimetype="text/event-stream"
    )

@app.route("/import-files/<filename>")
def serve_import_file(filename):

    return send_from_directory(
        IMPORT_DIR,
        filename
    )

@app.route("/flush-import", methods=["POST"])
def flush_import():

    files = []

    for file in os.listdir(IMPORT_DIR):

        if file.lower().endswith(
            (".mp3", ".wav", ".m4a", ".flac", ".ogg")
        ):
            files.append(file)

    return jsonify({
        "files": files
    })

@app.route("/delete-import-file", methods=["POST"])
def delete_import_file():

    filename = request.json["filename"]

    path = os.path.join(IMPORT_DIR, filename)

    if os.path.exists(path):
        os.remove(path)

    return jsonify({"status": "deleted"})


if __name__ == '__main__':
    app.run(debug=True, port=8000, use_reloader=False)