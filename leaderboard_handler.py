import os
from pymongo import MongoClient

# MongoDB connection
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
leaderboard_collection = db["leaderboard"]

def load_leaderboard():
    leaderboard = {}
    for entry in leaderboard_collection.find():
        leaderboard[entry["user_id"]] = entry["score"]
    return leaderboard

def save_leaderboard(leaderboard):
    leaderboard_collection.delete_many({})
    for user_id, score in leaderboard.items():
        leaderboard_collection.insert_one({"user_id": user_id, "score": score})

def add_score(user_id, score):
    current_score = leaderboard_collection.find_one({"user_id": user_id})
    if current_score:
        new_score = current_score["score"] + score
        leaderboard_collection.update_one({"user_id": user_id}, {"$set": {"score": new_score}})
    else:
        leaderboard_collection.insert_one({"user_id": user_id, "score": score})

def get_top_scores(n=20):
    top_scores = leaderboard_collection.find().sort("score", -1).limit(n)
    return [(entry["user_id"], entry["score"]) for entry in top_scores]

def get_user_score(user_id):
    user = leaderboard_collection.find_one({"user_id": user_id})
    return user["score"] if user else 0
