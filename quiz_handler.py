import logging
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data, save_chat_data
from leaderboard_handler import add_score, get_top_scores
import random
import json
import os
from pymongo import MongoClient
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzes_collection = db["used_quizzes"]
message_status_collection = db["message_status"]

def load_quizzes(category):
    file_path = os.path.join('quizzes', f'{category}.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        logger.error(f"Quiz file for category '{category}' not found.")
        return []

def send_quiz(context: CallbackContext):
    chat_id = context.job.context['chat_id']
    used_questions = context.job.context['used_questions']
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 40:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    else:
        if message_status is None or not message_status.get("limit_reached", False):
            context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "limit_reached": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"limit_reached": True}})
        next_quiz_time = datetime.combine(datetime.now() + timedelta(days=1), datetime.min.time())
        context.job_queue.run_once(send_quiz, next_quiz_time, context=context.job.context)
        return

    if not questions:
        if message_status is None or not message_status.get("no_questions", False):
            context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "no_questions": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"no_questions": True}})
        return

    used_question_ids = used_quizzes_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        if message_status is None or not message_status.get("no_new_questions", False):
            context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "no_new_questions": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"no_new_questions": True}})
        return

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzes_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

    message = context.bot.send_poll(
        chat_id=chat_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

def send_quiz_immediately(context: CallbackContext, chat_id):
    chat_data = load_chat_data(chat_id)
    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    if not questions:
        context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        return

    used_question_ids = used_quizzes_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
        return

    question = random.choice(available_questions)
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzes_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

    message = context.bot.send_poll(
        chat_id=chat_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

def handle_poll_answer(update: Update, context: CallbackContext):
    answer = update.poll_answer
    poll_id = answer.poll_id
    selected_option = answer.option_ids[0]

    if poll_id in context.bot_data:
        quiz_data = context.bot_data[poll_id]
        chat_id = quiz_data['chat_id']
        correct_option_id = quiz_data['correct_option_id']

        if selected_option == correct_option_id:
            user_id = answer.user.id
            add_score(user_id, 10)  # Add 10 points for correct answers
            context.bot.send_message(chat_id=chat_id, text=f"Correct answer by {answer.user.first_name}!")

def send_channel_quiz(context: CallbackContext, channel_id: str):
    chat_data = load_chat_data(channel_id)
    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": channel_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": channel_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": channel_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 40:
        quizzes_sent_collection.update_one({"chat_id": channel_id, "date": today}, {"$inc": {"count": 1}})
    else:
        if message_status is None or not message_status.get("limit_reached", False):
            context.bot.send_message(chat_id=channel_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": channel_id, "date": today, "limit_reached": True})
            else:
                message_status_collection.update_one({"chat_id": channel_id, "date": today}, {"$set": {"limit_reached": True}})
        next_quiz_time = datetime.combine(datetime.now() + timedelta(days=1), datetime.min.time())
        context.job_queue.run_once(send_channel_quiz, next_quiz_time, context={"chat_id": channel_id, "used_questions": chat_data.get("used_questions", [])})
        return

    if not questions:
        if message_status is None or not message_status.get("no_questions", False):
            context.bot.send_message(chat_id=channel_id, text="No questions available for this category.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": channel_id, "date": today, "no_questions": True})
            else:
                message_status_collection.update_one({"chat_id": channel_id, "date": today}, {"$set": {"no_questions": True}})
        return

    used_question_ids = used_quizzes_collection.find_one({"chat_id": channel_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        if message_status is None or not message_status.get("no_new_questions", False):
            context.bot.send_message(chat_id=channel_id, text="No more new questions available.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": channel_id, "date": today, "no_new_questions": True})
            else:
                message_status_collection.update_one({"chat_id": channel_id, "date": today}, {"$set": {"no_new_questions": True}})
        return

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": channel_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzes_collection.insert_one({"chat_id": channel_id, "used_questions": [question]})

    context.bot.send_poll(
        chat_id=channel_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

def broadcast_to_channel(context: CallbackContext, channel_id: str, text_content: str, content_type: str = 'text', file_id: str = None, reply_markup = None):
    try:
        if content_type == 'photo':
            context.bot.send_photo(chat_id=channel_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id=channel_id, text=text_content, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error broadcasting to channel {channel_id}: {e}")
