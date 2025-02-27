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
MONGO_URI = "MONGO_URI", "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzes_collection = db["used_quizzes"]
message_status_collection = db["message_status"]

def load_quizzes(category):
    file_path = os.path.join('quizzes', f'{category}.json')
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            questions = json.load(f)
            # Ensure each question has a unique ID
            for idx, question in enumerate(questions):
                if 'id' not in question:
                    question['id'] = f"{category}_{idx}"
            return questions
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
    elif quizzes_sent["count"] < 20:
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

    available_questions = [q for q in questions if q['id'] not in used_question_ids]
    if not available_questions:
        if message_status is None or not message_status.get("no_new_questions", False):
            context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
            if message_status is None:
                message_status_collection.insert_one({"chat_id": chat_id, "date": today, "no_new_questions": True})
            else:
                message_status_collection.update_one({"chat_id": chat_id, "date": today}, {"$set": {"no_new_questions": True}})
        return

    question = random.choice(available_questions)
    used_questions.append(question['id'])
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question['id']}})
    else:
        used_quizzes_collection.insert_one({"chat_id": chat_id, "used_questions": [question['id']]})

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
