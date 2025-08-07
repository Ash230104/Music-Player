from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
from yt_dlp import YoutubeDL
import tempfile
import os
import re
from io import BytesIO

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', name)

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)
@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/playlist')
def playlist_page():
    playlist_name = request.args.get('name')
    return render_template('index.html', playlist=playlist_name)

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, '%(title)s.%(ext)s')
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'noplaylist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
            mp3_filename = None
            
            for file in os.listdir(tmpdir):
                if file.endswith(".mp3"):
                    mp3_filename = os.path.join(tmpdir, file)
                    break

            if not mp3_filename or not os.path.isfile(mp3_filename):
                return jsonify({"error": f"MP3 file not found in {tmpdir}"}), 500

            with open(mp3_filename, 'rb') as f:
                file_data = f.read()

            return send_file(
                BytesIO(file_data),
                as_attachment=True,
                download_name=f"{info['title']}.mp3",
                mimetype="audio/mpeg"
            )


    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)
