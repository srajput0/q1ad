import logging
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data
import random
import json
import os

logger = logging.getLogger(__name__)

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

    if not questions:
        context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        return

    question = random.choice([q for q in questions if q not in used_questions])
    used_questions.append(question)

    context.bot.send_poll(
        chat_id=chat_id,
        question=question['question'],
        options=question['options'],
        type='quiz',
        correct_option_id=question['correct_option_id']
    )

def handle_poll_answer(update: Update, context: CallbackContext):
    # Handle poll answers if needed
    pass

def show_leaderboard(update: Update, context: CallbackContext):
    # Show the leaderboard if needed
    pass
