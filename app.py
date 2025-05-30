from flask import Flask, request, jsonify, send_file, render_template
import os
import subprocess
import uuid
import re
import json
from urllib.parse import urlparse, parse_qs
import tempfile
import shutil
from datetime import datetime, timedelta
import logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import threading
import time

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
DOWNLOAD_FOLDER = os.environ.get('DOWNLOAD_FOLDER', 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
COOKIES_FILE = os.path.join(DOWNLOAD_FOLDER, 'youtube.com_cookies.txt')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Production configurations
if os.environ.get('FLASK_ENV') == 'production':
    app.config['DEBUG'] = False
    app.config['PROPAGATE_EXCEPTIONS'] = True

def get_youtube_cookies():
    """Get YouTube cookies using undetected-chromedriver."""
    try:
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        driver = uc.Chrome(options=options)
        driver.get('https://www.youtube.com')
        time.sleep(5)  # Wait for cookies to be set
        
        cookies = driver.get_cookies()
        driver.quit()
        
        # Format cookies for yt-dlp
        cookie_string = ""
        for cookie in cookies:
            cookie_string += f"{cookie['domain']}\tTRUE\t{cookie['path']}\t"
            cookie_string += f"{'TRUE' if cookie['secure'] else 'FALSE'}\t"
            cookie_string += f"0\t{cookie['name']}\t{cookie['value']}\n"
        
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            f.write(cookie_string)
            
        return True
    except Exception as e:
        logger.error(f"Error getting cookies: {str(e)}")
        return False

def update_cookies_periodically():
    """Update cookies every 30 minutes."""
    while True:
        get_youtube_cookies()
        time.sleep(1800)  # Sleep for 30 minutes

# Start cookie updater thread
cookie_thread = threading.Thread(target=update_cookies_periodically, daemon=True)
cookie_thread.start()

def is_valid_youtube_url(url):
    """Validate YouTube URL format and extract video ID."""
    pattern = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None

def get_video_info(url):
    """Get video information using yt-dlp."""
    try:
        logger.info(f"Attempting to get video info for URL: {url}")
        
        if not os.path.exists(COOKIES_FILE):
            get_youtube_cookies()
        
        command = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            '--no-check-certificates',
            '--geo-bypass',
            '--cookies', COOKIES_FILE,
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            url
        ]
        
        logger.info(f"Running command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info("Successfully got video info")
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running yt-dlp: {str(e)}")
        logger.error(f"stderr: {e.stderr}")
        if "Sign in to confirm you're not a bot" in e.stderr:
            # Try refreshing cookies and retry once
            if get_youtube_cookies():
                try:
                    result = subprocess.run(command, capture_output=True, text=True, check=True)
                    return json.loads(result.stdout)
                except:
                    pass
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return None

def cleanup_old_files():
    """Remove files older than 1 hour."""
    threshold = datetime.now() - timedelta(hours=1)
    for filename in os.listdir(DOWNLOAD_FOLDER):
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)
        try:
            if os.path.getctime(filepath) < threshold.timestamp():
                if os.path.isfile(filepath):
                    os.remove(filepath)
        except OSError:
            pass

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/check-video', methods=['POST'])
def check_video():
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    video_id = is_valid_youtube_url(url)
    if not video_id:
        return jsonify({'success': False, 'error': 'Invalid YouTube URL'})

    video_info = get_video_info(url)
    if not video_info:
        return jsonify({'success': False, 'error': 'Could not fetch video information'})

    return jsonify({
        'success': True,
        'title': video_info.get('title', 'Unknown Title'),
        'thumbnail': video_info.get('thumbnail', ''),
        'duration': video_info.get('duration', 0),
        'formats': video_info.get('formats', [])
    })

@app.route('/download', methods=['POST'])
def download():
    cleanup_old_files()  # Cleanup old files before new download
    data = request.get_json()
    url = data.get('url')
    quality = data.get('quality', '720p')

    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    if not is_valid_youtube_url(url):
        return jsonify({'success': False, 'error': 'Invalid YouTube URL'})

    unique_id = str(uuid.uuid4())
    return download_video(url, quality, unique_id)

def download_video(url, quality, unique_id):
    """Download video using yt-dlp with specified quality."""
    outtmpl = os.path.join(DOWNLOAD_FOLDER, f'{unique_id}.%(ext)s')
    
    format_map = {
        '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
        '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
        '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        'audio': 'bestaudio/best'
    }

    base_command = [
        'yt-dlp',
        '--format', format_map.get(quality, 'best'),
        '--no-playlist',
        '--no-warnings',
        '--progress',
        '--no-check-certificates',
        '--geo-bypass',
        '--extractor-args', 'youtube:player_client=android',
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
        '--fragment-retries', '10',
        '--retries', '10',
        '--concurrent-fragments', '4',
        '--buffer-size', '16K',
        '-o', outtmpl
    ]

    if quality == 'audio':
        base_command.extend(['--extract-audio', '--audio-format', 'mp3', '--audio-quality', '0'])

    try:
        # First clean up any partial downloads
        for filename in os.listdir(DOWNLOAD_FOLDER):
            if filename.endswith(('.part', '.ytdl')):
                try:
                    os.remove(os.path.join(DOWNLOAD_FOLDER, filename))
                except OSError:
                    pass

        # Now run the download command
        process = subprocess.run(
            base_command + [url],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Get downloaded file path
        for file in os.listdir(DOWNLOAD_FOLDER):
            if file.startswith(unique_id):
                return jsonify({
                    'success': True,
                    'link': f'/file/{file}'
                })
                
        return jsonify({
            'success': False, 
            'error': 'File not found after download'
        })
        
    except subprocess.CalledProcessError as e:
        error_message = e.stderr if e.stderr else str(e)
        if 'HTTP Error 429' in error_message:
            error_message = 'Too many requests. Please try again later.'
        elif 'This video is not available' in error_message:
            error_message = 'This video is not available or may be private.'
        elif 'Sign in to confirm your age' in error_message:
            error_message = 'Age-restricted video. Cannot download.'
        elif "Sign in to confirm you're not a bot" in error_message:
            error_message = 'YouTube requires authentication. Please try again in a few minutes.'
        return jsonify({'success': False, 'error': error_message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/file/<filename>')
def serve_file(filename):
    try:
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'File not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health_check():
    try:
        # Check if yt-dlp is installed and working
        version_cmd = ['yt-dlp', '--version']
        version = subprocess.run(version_cmd, capture_output=True, text=True, check=True)
        return jsonify({
            'status': 'healthy',
            'yt_dlp_version': version.stdout.strip(),
            'downloads_dir': os.path.abspath(DOWNLOAD_FOLDER),
            'downloads_writable': os.access(DOWNLOAD_FOLDER, os.W_OK)
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'success': False, 'error': 'Not Found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal Server Error'}), 500

# Initialize: Cleanup downloads folder when app starts
cleanup_old_files()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') != 'production')
