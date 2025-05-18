import logging
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data, save_chat_data
from leaderboard_handler import add_score, update_user_stats
import random
import json
import os
from pymongo import MongoClient
from datetime import datetime
from telegram.error import BadRequest, TimedOut, NetworkError, RetryAfter 
# Add these imports at the top
from quiz_thread_manager import QuizThreadManager
import threading


logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = "mongodb+srv://tigerbundle282:tTaRXh353IOL9mj2@testcookies.2elxf.mongodb.net/?retryWrites=true&w=majority&appName=Testcookies"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
# quizzes_collection = db["quizzes"]
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

quiz_thread_manager = QuizThreadManager(max_workers=4)

def load_quizzes(category):
    file_path = os.path.join('quizzes', f'{category}.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        logger.error(f"Quiz file for category '{category}' not found.")
        return []


def get_daily_quiz_limit(chat_type):
    """
    Set daily quiz limit based on chat type.
    :param chat_type: Type of chat ('private', 'group', or 'supergroup').
    :return: Daily quiz limit.
    """
    if chat_type == 'private':
        return 50  # Daily limit for private chats
    else:
        return 100 # Daily limit for groups/supergroups
def send_quiz_logic(context: CallbackContext, chat_id: str):
    """
    Core logic for sending a quiz to the specified chat.
    """
    try:
        chat_data = load_chat_data(chat_id)
        if not chat_data:
            logger.error(f"No chat data found for chat_id: {chat_id}")
            return

        category = chat_data.get('category')
        if not category:
            logger.error(f"No category set for chat_id: {chat_id}")
            return

        questions = load_quizzes(category)
        if not questions:
            logger.error(f"No questions loaded for category: {category}")
            return

        # Get the chat type and daily quiz limit
        try:
            chat = context.bot.get_chat(chat_id)
            chat_type = chat.type
        except Exception as e:
            logger.error(f"Failed to get chat type: {e}")
            return

        logger.info(f"Sending quiz to Chat ID: {chat_id} | Chat Type: {chat_type} | Category: {category}")

        today = datetime.now().date().isoformat()
        quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
        
        # Initialize quizzes_sent if not exists
        if not quizzes_sent:
            quizzes_sent_collection.insert_one({
                "chat_id": chat_id,
                "date": today,
                "count": 0
            })
            quizzes_sent = {"count": 0}

        daily_limit = get_daily_quiz_limit(chat_type)
        
        # Check daily limit
        if quizzes_sent["count"] >= daily_limit:
            message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})
            if not message_status or not message_status.get("limit_reached"):
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Daily quiz limit ({daily_limit}) reached for {chat_type}. Quizzes will resume tomorrow."
                )
                message_status_collection.update_one(
                    {"chat_id": chat_id, "date": today},
                    {"$set": {"limit_reached": True}},
                    upsert=True
                )
            return

        # Get used questions
        used_questions_doc = used_quizzesss_collection.find_one({"chat_id": chat_id})
        used_question_ids = used_questions_doc["used_questions"] if used_questions_doc else []

        # Filter available questions
        available_questions = [q for q in questions if q not in used_question_ids]
        
        # Reset if all questions used
        if not available_questions:
            used_quizzesss_collection.update_one(
                {"chat_id": chat_id},
                {"$set": {"used_questions": []}},
                upsert=True
            )
            available_questions = questions
            context.bot.send_message(
                chat_id=chat_id,
                text="All questions have been used. Starting fresh with all questions."
            )

        # Select and send question
        question = random.choice(available_questions)
        
        message = context.bot.send_poll(
            chat_id=chat_id,
            question=question['question'],
            options=question['options'],
            type='quiz',
            correct_option_id=question['correct_option_id'],
            is_anonymous=False
        )

        # Update used questions
        used_quizzesss_collection.update_one(
            {"chat_id": chat_id},
            {"$push": {"used_questions": question}},
            upsert=True
        )

        # Update quiz count
        quizzes_sent_collection.update_one(
            {"chat_id": chat_id, "date": today},
            {"$inc": {"count": 1}}
        )

        # Store poll data
        context.bot_data[message.poll.id] = {
            'chat_id': chat_id,
            'correct_option_id': question['correct_option_id']
        }

        logger.info(f"Successfully sent quiz to chat {chat_id}")
        return True

    except Exception as e:
        logger.error(f"Error in send_quiz_logic for chat {chat_id}: {e}")
        return False


@retry_on_failure
def send_quiz(context: CallbackContext):
    """
    Send a quiz to the chat using the thread pool.
    """
    chat_id = context.job.context['chat_id']
    chat_data = load_chat_data(chat_id)
    category = chat_data.get('category')
    
    # Schedule the quiz using thread manager
    quiz_thread_manager.schedule_quiz(
        chat_id=chat_id,
        context=context,
        category=category
    )



# @retry_on_failure
# def send_quiz_immediately(context: CallbackContext, chat_id: str):
#     """
#     Send a quiz immediately to the specified chat.
#     """
#     send_quiz_logic(context, chat_id)


@retry_on_failure
def send_quiz_immediately(context: CallbackContext, chat_id: str):
    """
    Send a quiz immediately to the specified chat using the thread pool.
    """
    chat_data = load_chat_data(chat_id)
    category = chat_data.get('category')
    
    # Schedule immediate quiz with higher priority
    quiz_thread_manager.schedule_quiz(
        chat_id=chat_id,
        context=context,
        category=category,
        priority=0  # Higher priority for immediate sending
    )


def handle_poll_answer(update: Update, context: CallbackContext):
    """Handle user answers to quiz questions"""
    poll_answer = update.poll_answer
    user_id = str(poll_answer.user.id)
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None

    poll_id = poll_answer.poll_id
    poll_data = context.bot_data.get(poll_id)

    if not poll_data:
        return

    correct_option_id = poll_data['correct_option_id']
    is_correct = selected_option == correct_option_id

    # Update user statistics
    update_user_stats(user_id, is_correct)

