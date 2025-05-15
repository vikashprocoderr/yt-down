#! /usr/bin/env bash

# Exit on error
set -e

# Update system and install required packages
apt-get update
apt-get install -y wget gnupg2 unzip ffmpeg

# Install Google Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list
apt-get update
apt-get install -y google-chrome-stable

# Update pip and install Python dependencies
python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt
pip install --no-cache-dir --upgrade yt-dlp

# Create downloads directory with proper permissions
mkdir -p downloads
chmod 777 downloads
