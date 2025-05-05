import os
from pymongo import MongoClient
from typing import Dict, Any
from datetime import datetime
# MongoDB connection
# MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
leaderboard_collection = db["leaderboard"]

def get_user_stats(user_id: str) -> Dict[str, Any]:
    user = leaderboard_collection.find_one({"user_id": user_id})
    if not user:
        return {
            "user_id": user_id,
            "score": 0,
            "attempted_quizzes": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "last_updated": datetime.utcnow()
        }
    return user

def update_user_stats(user_id: str, is_correct: bool) -> None:
    stats = get_user_stats(user_id)
    
    # Update stats
    stats["attempted_quizzes"] += 1
    if is_correct:
        stats["correct_answers"] += 1
    else:
        stats["incorrect_answers"] += 1
    stats["last_updated"] = datetime.utcnow()
    
    # Calculate accuracy
    total_attempts = stats["attempted_quizzes"]
    stats["accuracy"] = (stats["correct_answers"] / total_attempts * 100) if total_attempts > 0 else 0
    
    # Update or insert the document
    leaderboard_collection.update_one(
        {"user_id": user_id},
        {"$set": stats},
        upsert=True
    )

def get_user_rank(user_id: str) -> int:
    user_score = get_user_stats(user_id)["score"]
    higher_scores = leaderboard_collection.count_documents({"score": {"$gt": user_score}})
    return higher_scores + 1

def get_user_percentile(user_id: str) -> float:
    user_score = get_user_stats(user_id)["score"]
    total_users = leaderboard_collection.count_documents({})
    users_below = leaderboard_collection.count_documents({"score": {"$lt": user_score}})
    return (users_below / total_users * 100) if total_users > 0 else 0


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
