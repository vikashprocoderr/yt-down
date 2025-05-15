#! /usr/bin/env bash
# Update pip first
python -m pip install --upgrade pip

# Install dependencies with upgraded pip
pip install --no-cache-dir -r requirements.txt

# Install latest yt-dlp separately
pip install --no-cache-dir --upgrade yt-dlp
