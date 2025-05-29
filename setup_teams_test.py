#!/usr/bin/env python3
"""
Quick setup script for testing bot in Teams
"""

import os
import subprocess
import json

def setup_teams_testing():
    """Setup bot for Teams testing"""
    
    print("🚀 Setting up Sinhala Transcription Bot for Teams testing...")
    
    # Check if ngrok is installed
    try:
        subprocess.run(["ngrok", "version"], check=True, capture_output=True)
        print("✅ ngrok is installed")
    except:
        print("❌ ngrok not found. Please install from https://ngrok.com/")
        return
    
    # Start ngrok in background
    print("🌐 Starting ngrok tunnel...")
    ngrok_process = subprocess.Popen(
        ["ngrok", "http", "8080"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print("⏳ Waiting for ngrok to start...")
    import time
    time.sleep(3)
    
    # Get ngrok URL
    try:
        import requests
        response = requests.get("http://localhost:4040/api/tunnels")
        tunnels = response.json()["tunnels"]
        public_url = tunnels[0]["public_url"]
        print(f"✅ ngrok URL: {public_url}")
        
        # Update environment variables
        os.environ["BOT_ENDPOINT"] = f"{public_url}/api/messages"
        
        print("\n📋 Next steps:")
        print(f"1. Go to Azure Portal and create a Bot resource")
        print(f"2. Set messaging endpoint to: {public_url}/api/messages")
        print(f"3. Copy App ID and Password to your .env file")
        print(f"4. Install the bot in Teams using the manifest")
        print(f"5. Start a Teams call and say 'start transcription'")
        
        return public_url
        
    except Exception as e:
        print(f"❌ Error getting ngrok URL: {str(e)}")
        return None

if __name__ == "__main__":
    setup_teams_testing()
