import os
from pymongo import MongoClient

# MongoDB connection
# MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
chat_data_collection = db["chat_data"]

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
