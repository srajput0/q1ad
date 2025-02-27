import logging
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data, save_chat_data
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
        correct_option_id=question['correct_option_id'],
        is_anonymous=False
    )

def handle_poll_answer(update: Update, context: CallbackContext):
    answer = update.poll_answer
    user_id = answer.user.id
    poll_id = answer.poll_id
    selected_option_id = answer.option_ids[0]
    
    # Retrieve the poll data
    poll_data = context.bot_data.get(poll_id)
    
    if not poll_data:
        return
    
    correct_option_id = poll_data['correct_option_id']
    chat_id = poll_data['chat_id']
    chat_data = load_chat_data(chat_id)
    
    if 'scores' not in chat_data:
        chat_data['scores'] = {}
    
    if user_id not in chat_data['scores']:
        chat_data['scores'][user_id] = 0
    
    # Update the score
    if selected_option_id == correct_option_id:
        chat_data['scores'][user_id] += 1
    
    save_chat_data(chat_id, chat_data)

def show_leaderboard(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)
    
    if 'scores' not in chat_data or not chat_data['scores']:
        update.message.reply_text("No scores available.")
        return
    
    scores = chat_data['scores']
    leaderboard = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "Leaderboard:\n\n"
    for user_id, score in leaderboard:
        user = context.bot.get_chat_member(chat_id, user_id).user
        leaderboard_text += f"{user.first_name} {user.last_name or ''}: {score}\n"
    
    update.message.reply_text(leaderboard_text)
