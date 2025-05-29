# Create this script to help with Azure setup
import requests
import json

def create_bot_registration():
    """
    Steps to register your bot:
    1. Go to Azure Portal (portal.azure.com)
    2. Create "Azure Bot" resource
    3. Use your ngrok URL as messaging endpoint
    """
    
    bot_config = {
        "messaging_endpoint": "https://your-ngrok-url.ngrok.io/api/messages",
        "app_id": "your-app-id",  # From Azure App Registration
        "app_password": "your-app-password"
    }
    
    print("Bot configuration:")
    print(json.dumps(bot_config, indent=2))
    
    return bot_config

if __name__ == "__main__":
    create_bot_registration()
