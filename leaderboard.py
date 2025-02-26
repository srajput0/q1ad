import os
from pymongo import MongoClient

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://quiz:quiz123@+@cluster0.yzjqw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
leaderboard_collection = db["leaderboard"]

# Load leaderboard data
def load_leaderboard():
    leaderboard = {}
    for entry in leaderboard_collection.find():
        leaderboard[entry["user_id"]] = entry["score"]
    return leaderboard

# Save leaderboard data
def save_leaderboard(data):
    for user_id, score in data.items():
        leaderboard_collection.update_one(
            {"user_id": user_id},
            {"$set": {"score": score}},
            upsert=True
        )
