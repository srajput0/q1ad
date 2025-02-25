import json
import os

CHAT_IDS_FILE = 'config/chat_ids.json'

# Load chat data
def load_chat_data():
    if os.path.exists(CHAT_IDS_FILE):
        with open(CHAT_IDS_FILE, 'r') as file:
            try:
                data = json.load(file)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}

# Save chat data
def save_chat_data(chat_data):
    with open(CHAT_IDS_FILE, 'w') as file:
        json.dump(chat_data, file)
