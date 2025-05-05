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
    """Update user statistics including all metrics"""
    user = leaderboard_collection.find_one({"user_id": user_id})
    
    if user:
        # Update existing user stats
        leaderboard_collection.update_one(
            {"user_id": user_id},
            {
                "$inc": {
                    "attempted_quizzes": 1,
                    "correct_answers": 1 if is_correct else 0,
                    "incorrect_answers": 0 if is_correct else 1,
                    "score": 2 if is_correct else 0  # 2 points for correct answer
                },
                "$set": {
                    "last_updated": datetime.utcnow()
                }
            }
        )
    else:
        # Create new user stats
        leaderboard_collection.insert_one({
            "user_id": user_id,
            "score": 2 if is_correct else 0,
            "attempted_quizzes": 1,
            "correct_answers": 1 if is_correct else 0,
            "incorrect_answers": 0 if is_correct else 1,
            "last_updated": datetime.utcnow()
        })

def get_user_rank(user_id: str) -> int:
    """Get user's rank based on score"""
    user = leaderboard_collection.find_one({"user_id": user_id})
    if not user:
        return 0
    
    # Count users with higher scores
    higher_scores = leaderboard_collection.count_documents({
        "score": {"$gt": user["score"]}
    })
    return higher_scores + 1

def get_user_percentile(user_id: str) -> float:
    """Calculate user's percentile"""
    user = leaderboard_collection.find_one({"user_id": user_id})
    if not user:
        return 0.0
    
    total_users = leaderboard_collection.count_documents({})
    users_below = leaderboard_collection.count_documents({
        "score": {"$lt": user["score"]}
    })
    
    if total_users == 0:
        return 0.0
    return (users_below / total_users) * 100

def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get comprehensive user statistics"""
    user = leaderboard_collection.find_one({"user_id": user_id})
    if not user:
        return {
            "score": 0,
            "rank": 0,
            "percentile": 0.0,
            "attempted_quizzes": 0,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "accuracy": 0.0
        }
    
    attempted = user.get("attempted_quizzes", 0)
    correct = user.get("correct_answers", 0)
    accuracy = (correct / attempted * 100) if attempted > 0 else 0
    
    return {
        "score": user.get("score", 0),
        "rank": get_user_rank(user_id),
        "percentile": get_user_percentile(user_id),
        "attempted_quizzes": attempted,
        "correct_answers": correct,
        "incorrect_answers": user.get("incorrect_answers", 0),
        "accuracy": accuracy
    }



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
