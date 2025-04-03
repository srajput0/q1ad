import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.error import TelegramError
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext, PollAnswerHandler
)
from chat_data_handler import load_chat_data, save_chat_data, add_served_chat, add_served_user, get_active_quizzes
from quiz_handler import send_quiz, send_quiz_immediately,  handle_poll_answer, repeat_all_quizzes
from admin_handler import broadcast
from leaderboard_handler import get_user_score, get_top_scores
from datetime import datetime
from pymongo import MongoClient
import threading
import time
# Enable logging
from bot_logging import logger

TOKEN = "7922102581:AAF33bRlw2uBdTcoZvSfVI-ReXni_-Ubbig"
ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

# MongoDB connection
MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]

# Define the daily quiz limit
DAILY_QUIZ_LIMIT = 100

def start_command(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    # Register the chat and user for broadcasting
    add_served_chat(chat_id)
    add_served_user(user_id)

    # Inline buttons for main menu
    keyboard = [
        [
            InlineKeyboardButton("Add in Your Group", url=f"https://t.me/ipopcorn3bot?startgroup=true"),   
        ],
        [InlineKeyboardButton("Start PYQ Quizzes", callback_data='start_quiz')],
        [
            InlineKeyboardButton("📊 Leaderboard", callback_data='show_leaderboard'),
            InlineKeyboardButton("📈 My Score", callback_data='show_stats')
        ],
        [InlineKeyboardButton("Commands", callback_data='show_commands')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send welcome message with main menu buttons
    update.message.reply_text(
        "Welcome to the Quiz Bot! This is a Quiz Bot made by *Pinnacle Publication.*\nThis can ask two Exams PYQ's.\n\n*•SSC*\n*•RRB*\n\nChoose the option for proceed further :",
        reply_markup=reply_markup, parse_mode="Markdown"
    )

def is_user_admin(update: Update, user_id: int):
    chat_member = update.effective_chat.get_member(user_id)
    return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.CREATOR]

def button(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    query = update.callback_query
    query.answer()
    chat_id = str(query.message.chat.id)
    chat_data = load_chat_data(chat_id)

    if query.data == 'start_quiz':
        # Inline buttons for language selection
        keyboard = [
            [
                InlineKeyboardButton("Hindi", callback_data='language_hindi'),
                InlineKeyboardButton("English", callback_data='language_english')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Please select your language:", reply_markup=reply_markup)

    elif query.data.startswith('language_'):
        language = query.data.split('_')[1]
        chat_data['language'] = language
        save_chat_data(chat_id, chat_data)

        # Inline buttons for category selection based on the chosen language
        if language == 'hindi':
            keyboard = [
                [
                    InlineKeyboardButton("SSC", callback_data='category_SSCHi'),
                    InlineKeyboardButton("RRB", callback_data='category_RRBHi')
                ],
                [InlineKeyboardButton("Back", callback_data='back_to_languages')]
            ]
        elif language == 'english':
            keyboard = [
                [
                    InlineKeyboardButton("SSC", callback_data='category_SSCEn'),
                    InlineKeyboardButton("RRB", callback_data='category_RRBEn')
                ],
                [InlineKeyboardButton("Back", callback_data='back_to_languages')]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=f"Language selected: {language.upper()}\nPlease select your category:",
                                reply_markup=reply_markup)

    elif query.data.startswith('category_'):
        category = query.data.split('_')[1]
        chat_data['category'] = category
        save_chat_data(chat_id, chat_data)

        # Directly start the quiz with interval selection
        keyboard = [
            [
                InlineKeyboardButton("30 sec", callback_data='interval_30'),
                InlineKeyboardButton("1 min", callback_data='interval_60'),
                InlineKeyboardButton("5 min", callback_data='interval_300')
            ],
            [
                InlineKeyboardButton("10 min", callback_data='interval_600'),
                InlineKeyboardButton("30 min", callback_data='interval_1800'),
                InlineKeyboardButton("60 min", callback_data='interval_3600')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=f"Category selected: {category.upper()}\nPlease select the interval for quizzes:\n/setinterval - Set the interval for quizzes - \n[Ex. /setinterval 20] for set Custom Interval",
                                reply_markup=reply_markup, parse_mode="Markdown")

    elif query.data == 'back_to_languages':
        # Inline buttons for language selection
        keyboard = [
            [
                InlineKeyboardButton("Hindi", callback_data='language_hindi'),
                InlineKeyboardButton("English", callback_data='language_english')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Please select your language:", reply_markup=reply_markup)

    elif query.data == 'back_to_categories':
        language = chat_data.get('language', 'english')
        if language == 'hindi':
            keyboard = [
                [
                    InlineKeyboardButton("SSC", callback_data='category_SSCHi'),
                    InlineKeyboardButton("RRB", callback_data='category_RRBHi')
                ],
                [InlineKeyboardButton("Back", callback_data='back_to_languages')]
            ]
        elif language == 'english':
            keyboard = [
                [
                    InlineKeyboardButton("SSC", callback_data='category_SSCEn'),
                    InlineKeyboardButton("RRB", callback_data='category_RRBEn')
                ],
                [InlineKeyboardButton("Back", callback_data='back_to_languages')]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Please select your category:", reply_markup=reply_markup)

    elif query.data.startswith('interval_'):
        # Check if the user is an admin in group chats
        if update.effective_chat.type in ['group', 'supergroup'] and not is_user_admin(update, update.effective_user.id):
            query.edit_message_text(text="You need to be an admin to set the interval in group chats.")
            return

        interval = int(query.data.split('_')[1])
        chat_data = load_chat_data(chat_id)
        chat_data["interval"] = interval
        save_chat_data(chat_id, chat_data)
        
        if chat_data.get("active", False):
            query.edit_message_text(f"Quiz interval updated to {interval} seconds. Applying new interval immediately.")
            jobs = context.job_queue.jobs()
            for job in jobs:
                if job.context and job.context["chat_id"] == chat_id:
                    job.schedule_removal()
                    
        # Send the first quiz immediately and then schedule subsequent quizzes
        send_quiz_immediately(context, chat_id)
        context.job_queue.run_repeating(send_quiz, interval=interval, first=interval, context={"chat_id": chat_id, "used_questions": chat_data.get("used_questions", [])})
        query.edit_message_text(f"Quiz interval updated to {interval} seconds. Starting quiz.")
        start_quiz(update, context)

    elif query.data == 'show_leaderboard':
        chat_id = update.effective_chat.id
        # Send initial loading message
        loading_message = context.bot.send_message(chat_id=chat_id, text="Leaderboard is loading...")

        # Send loading updates in a separate thread
        def send_loading_messages(message_id):
            for i in range(2, 4):
                time.sleep(1)  # Wait for 1 second before sending the next message
                context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"Leaderboard is loading...{i}")

        loading_thread = threading.Thread(target=send_loading_messages, args=(loading_message.message_id,))
        loading_thread.start()

        # Fetch and display the leaderboard
        top_scores = get_top_scores(20)
        loading_thread.join()  # Wait for the loading messages to finish

        if not top_scores:
            context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
            update.effective_message.reply_text("🏆 No scores yet! Start playing to appear on the leaderboard.")
            return

        # Delete the loading message
        context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)

        # Prepare and send the leaderboard message
        message = "🏆 *Quiz Leaderboard* 🏆\n\n"
        medals = ["🥇", "🥈", "🥉"]

        for rank, (user_id, score) in enumerate(top_scores, start=1):
            try:
                user = context.bot.get_chat(int(user_id))
                username = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}"
            except Exception:
                username = f"User {user_id}"

            rank_display = medals[rank - 1] if rank <= 3 else f"{rank}."
            message += f"{rank_display}  *{username}* - {score} Points\n\n"

        update.effective_message.reply_text(message, parse_mode="Markdown")

    elif query.data == 'show_stats':
        user_id = str(update.effective_user.id)
        score = get_user_score(user_id)
        update.effective_message.reply_text(f"Your current score is: {score} points.")
        
    elif query.data == 'show_commands':
        commands_description = """
        /start - Start the bot and show the main menu
        /setinterval - Set the interval for quizzes
        /stopquiz - Stop the current quiz
        /pause - Pause the current quiz
        /resume - Resume a paused quiz
        /leaderboard - Show the leaderboard
        /stats - Show your current stats
        """
        # Inline button to go back to the main menu
        keyboard = [
            [InlineKeyboardButton("Back", callback_data='back_to_main_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=f"Available Commands:\n{commands_description}", reply_markup=reply_markup)

    elif query.data == 'back_to_main_menu':
        # Inline buttons for main menu
        keyboard = [
            [InlineKeyboardButton("Start Quiz", callback_data='start_quiz')],
            [
                InlineKeyboardButton("Leaderboard", callback_data='show_leaderboard'),
                InlineKeyboardButton("My Score", callback_data='show_stats')
            ],
            [InlineKeyboardButton("Commands", callback_data='show_commands')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Welcome to the Quiz Bot! Please choose an option:", reply_markup=reply_markup)

def set_interval(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)

    if not context.args or not context.args[0].isdigit():
        update.message.reply_text("Usage: /setinterval <seconds>")
        return
    
    interval = int(context.args[0])
    if interval < 10:
        update.message.reply_text("Interval must be at least 10 seconds.")
        return

    chat_data = load_chat_data(chat_id)
    chat_data["interval"] = interval
    save_chat_data(chat_id, chat_data)

    # If quiz is already running, update the interval immediately
    if chat_data.get("active", False):
        update.message.reply_text(f"Quiz interval updated to {interval} seconds. Applying new interval immediately.")
        jobs = context.job_queue.jobs()
        for job in jobs:
            if job.context and job.context["chat_id"] == chat_id:
                job.schedule_removal()
        # Send the first quiz immediately and then schedule subsequent quizzes
        send_quiz_immediately(context, chat_id)
        context.job_queue.run_repeating(send_quiz, interval=interval, first=interval, context={"chat_id": chat_id, "used_questions": chat_data.get("used_questions", [])})
    else:
        update.message.reply_text(f"Quiz interval updated to {interval} seconds.")
        start_quiz(update, context)

def start_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent and quizzes_sent.get("count", 0) >= DAILY_QUIZ_LIMIT:
        update.message.reply_text("You have reached your daily limit. The next quiz will be sent tomorrow.")
        return

    if chat_data.get("active", False):
        update.message.reply_text("A quiz is already running in this chat!")
        return

    interval = chat_data.get("interval", 30)  # Default interval to 30 seconds if not set
    chat_data["active"] = True
    save_chat_data(chat_id, chat_data)

    update.message.reply_text(f"Quiz started! Interval: {interval} seconds.")

    # Send the first quiz immediately
    try:
        send_quiz_immediately(context, chat_id)
    except TelegramError as e:
        logger.error(f"Failed to send quiz: {e}")
        update.message.reply_text("Failed to send quiz. Please check the chat ID and permissions.")
        return

    # Increment the count of quizzes sent today
    if not quizzes_sent:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    else:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})

    # Schedule subsequent quizzes at the specified interval
    context.job_queue.run_repeating(send_quiz, interval=interval, first=interval, context={"chat_id": chat_id, "used_questions": []})

def stop_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)

    if chat_data:
        chat_data["active"] = False
        save_chat_data(chat_id, chat_data)

        jobs = context.job_queue.jobs()
        for job in jobs:
            if job.context and job.context["chat_id"] == chat_id:
                job.schedule_removal()

        update.message.reply_text("Quiz stopped successfully.")
    else:
        update.message.reply_text("No active quiz to stop.")

def pause_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)

    if not chat_data.get("active", False):
        update.message.reply_text("No active quiz to pause.")
        return

    chat_data["paused"] = True
    save_chat_data(chat_id, chat_data)

    jobs = context.job_queue.jobs()
    for job in jobs:
        if job.context and job.context["chat_id"] == chat_id:
            job.schedule_removal()

    update.message.reply_text("Quiz paused successfully.")

def resume_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)

    if not chat_data.get("paused", False):
        update.message.reply_text("No paused quiz to resume.")
        return

    chat_data["paused"] = False
    save_chat_data(chat_id, chat_data)

    interval = chat_data.get("interval", 30)
    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

    update.message.reply_text("Quiz resumed successfully.")

def restart_active_quizzes(context: CallbackContext):
    active_quizzes = get_active_quizzes()
    for quiz in active_quizzes:
        chat_id = quiz["chat_id"]
        interval = quiz["data"].get("interval", 30)
        used_questions = quiz["data"].get("used_questions", [])
        context.job_queue.run_repeating(send_quiz, interval=interval, first=interval, context={"chat_id": chat_id, "used_questions": used_questions})

def check_stats(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    score = get_user_score(user_id)
    update.message.reply_text(f"Your current score is: {score} points.")

def show_leaderboard(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id

    # Send initial loading message
    loading_message = context.bot.send_message(chat_id=chat_id, text="Leaderboard is loading...")

    # Send loading updates in a separate thread
    def send_loading_messages(message_id):
        for i in range(2, 4):
            time.sleep(1)  # Wait for 1 second before sending the next message
            context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"Leaderboard is loading...{i}")

    loading_thread = threading.Thread(target=send_loading_messages, args=(loading_message.message_id,))
    loading_thread.start()

    # Fetch and display the leaderboard
    top_scores = get_top_scores(20)
    loading_thread.join()  # Wait for the loading messages to finish

    if not top_scores:
        context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
        update.message.reply_text("🏆 No scores yet! Start playing to appear on the leaderboard.")
        return

    # Delete the loading message
    context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)

    # Prepare and send the leaderboard message
    message = "🏆 *Quiz Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for rank, (user_id, score) in enumerate(top_scores, start=1):
        try:
            user = context.bot.get_chat(int(user_id))
            username = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}"
        except Exception:
            username = f"User {user_id}"

        rank_display = medals[rank - 1] if rank <= 3 else f"{rank}."
        message += f"{rank_display}  *{username}* - {score} Points\n\n"

    update.message.reply_text(message, parse_mode="Markdown")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("setinterval", set_interval))
    dp.add_handler(CommandHandler("stopquiz", stop_quiz))
    dp.add_handler(CommandHandler("pause", pause_quiz))
    dp.add_handler(CommandHandler("resume", resume_quiz))
    dp.add_handler(CommandHandler("repetall", repeat_all_quizzes))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(PollAnswerHandler(handle_poll_answer))
    dp.add_handler(CommandHandler("leaderboard", show_leaderboard))
    dp.add_handler(CommandHandler("broadcast", broadcast))
    dp.add_handler(CommandHandler("stats", check_stats))


    
    updater.start_polling()
    updater.job_queue.run_once(restart_active_quizzes, 0)

    updater.idle()

if __name__ == '__main__':
    main()
