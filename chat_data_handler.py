import os
from pymongo import MongoClient

# MongoDB connection
# MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# client = MongoClient(MONGO_URI)

client = MongoClient(MONGO_URI)db = client["telegram_bot"]
chat_data_collection = db["chat_data"]
served_chats_collection = db["served_chats"]
served_users_collection = db["served_users"]

# Load chat data
def load_chat_data(chat_id):
    chat_data = chat_data_collection.find_one({"chat_id": chat_id})
    if chat_data:
        return chat_data["data"]
    return {}

# Save chat data
def save_chat_data(chat_id, data):
    chat_data_collection.update_one(
        {"chat_id": chat_id},
        {"$set": {"data": data}},
        upsert=True
    )

# Get served chats
def get_served_chats():
    return list(served_chats_collection.find({}, {"_id": 0, "chat_id": 1}))

# Get served users
def get_served_users():
    return list(served_users_collection.find({}, {"_id": 0, "user_id": 1}))
