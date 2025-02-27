import logging
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data
from leaderboard_handler import add_score, get_top_scores
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

def show_leaderboard(update: Update, context: CallbackContext):
    top_scores = get_top_scores(10)

    if not top_scores:
        update.message.reply_text("🏆 No scores yet! Start playing to appear on the leaderboard.")
        return

    message = "🏆 *Quiz Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for rank, (user_id, score) in enumerate(top_scores, start=1):
        try:
            user = context.bot.get_chat(int(user_id))
            username = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}"
        except Exception:
            username = f"User {user_id}"

        rank_display = medals[rank - 1] if rank <= 3 else f"#{rank}"
        message += f"{rank_display} *{username}* - {score} points\n"

    update.message.reply_text(message, parse_mode="Markdown")
