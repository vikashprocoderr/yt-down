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

# Ensure latest pip version
curl -sS https://bootstrap.pypa.io/get-pip.py | python3

# Install Python dependencies with latest pip
python3 -m pip install --no-cache-dir -r requirements.txt
python3 -m pip install --no-cache-dir --upgrade yt-dlp

# Create downloads directory with proper permissions
mkdir -p downloads
chmod 777 downloads
