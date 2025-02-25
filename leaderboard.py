import json
import os

LEADERBOARD_FILE = 'config/leaderboard.json'

# Load leaderboard data
def load_leaderboard():
    if os.path.exists(LEADERBOARD_FILE):
        with open(LEADERBOARD_FILE, 'r') as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return {}
    return {}

# Save leaderboard data
def save_leaderboard(data):
    with open(LEADERBOARD_FILE, 'w') as file:
        json.dump(data, file, indent=4)
