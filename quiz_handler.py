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
from telegram.error import BadRequest, TimedOut, NetworkError, RetryAfter 

logger = logging.getLogger(__name__)

# MongoDB connection
# MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_URI = "mongodb+srv://2004:2005@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"


# MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzesss_collection = db["used_quizzesssss"]
message_status_collection = db["message_status"]



def retry_on_failure(func):
    """Decorator to retry function on transient errors"""
    def wrapper(*args, **kwargs):
        retries = 3
        while retries > 0:
            try:
                return func(*args, **kwargs)
            except (TimedOut, NetworkError, RetryAfter) as e:
                logger.warning(f"Retryable error occurred: {e}. Retrying...")
                retries -= 1
            except Exception as e:
                logger.error(f"Unrecoverable error occurred: {e}")
                break
        logger.error(f"Function {func.__name__} failed after retries.")
    return wrapper
    
def load_quizzes(category):
    file_path = os.path.join('quizzes', f'{category}.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        logger.error(f"Quiz file for category '{category}' not found.")
        return []


def get_daily_quiz_limit(chat_type):
    """Set daily quiz limits based on chat type."""
    if chat_type == 'private':
        return 40
    if chat_type in ['group', 'supergroup']:
        return 100


@retry_on_failure
def send_quiz(context: CallbackContext):
    chat_id = context.job.context['chat_id']
    used_questions = context.job.context['used_questions']
    chat_type = context.job.context.get('chat_type', 'private')  # Default to private if not provided
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})

    daily_limit = get_daily_quiz_limit(chat_type)
    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 0})  # Initialize count with 0
        quizzes_sent = {"count": 0}  # Ensure quizzes_sent has a default structure

    if quizzes_sent["count"] >= daily_limit:
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

    used_question_ids = used_quizzesss_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        # Reset used questions if no new questions are available
        used_quizzesss_collection.update_one({"chat_id": chat_id}, {"$set": {"used_questions": []}})
        used_question_ids = []
        available_questions = questions
        context.bot.send_message(chat_id=chat_id, text="All quizzes have been used. Restarting with all available quizzes.")

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzesss_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzesss_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

    try:
        message = context.bot.send_poll(
            chat_id=chat_id,
            question=question['question'],
            options=question['options'],
            type='quiz',
            correct_option_id=question['correct_option_id'],
            is_anonymous=False
        )
        # Increment the count only after successfully sending the quiz
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    except BadRequest as e:
        logger.error(f"Failed to send quiz to chat {chat_id}: {e}")
        context.bot.send_message(chat_id=chat_id, text="Failed to send quiz. Please check the chat ID and permissions.")
        return

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }
    
@retry_on_failure
def send_quiz_immediately(context: CallbackContext, chat_id: str):
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})

    daily_limit = get_daily_quiz_limit(chat_type)
    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 0})  # Initialize count with 0
        quizzes_sent = {"count": 0}  # Ensure quizzes_sent has a default structure

    if quizzes_sent["count"] >= daily_limit:
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

    used_question_ids = used_quizzesss_collection.find_one({"chat_id": chat_id})
    used_question_ids = used_question_ids["used_questions"] if used_question_ids else []

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        # Reset used questions if no new questions are available
        used_quizzesss_collection.update_one({"chat_id": chat_id}, {"$set": {"used_questions": []}})
        used_question_ids = []
        available_questions = questions
        context.bot.send_message(chat_id=chat_id, text="All quizzes have been used. Restarting with all available quizzes.")

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzesss_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzesss_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

    try:
        message = context.bot.send_poll(
            chat_id=chat_id,
            question=question['question'],
            options=question['options'],
            type='quiz',
            correct_option_id=question['correct_option_id'],
            is_anonymous=False
        )
        # Increment the count only after successfully sending the quiz
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    except BadRequest as e:
        logger.error(f"Failed to send quiz to chat {chat_id}: {e}")
        context.bot.send_message(chat_id=chat_id, text="Failed to send quiz. Please check the chat ID and permissions.")
        return

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }



def handle_poll_answer(update: Update, context: CallbackContext):
    poll_answer = update.poll_answer
    user_id = str(poll_answer.user.id)
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None

    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(poll_id)

    if not poll_data:
        return

    correct_option_id = poll_data['correct_option_id']

    # Update the score
    if selected_option == correct_option_id:
        add_score(user_id, 1)
