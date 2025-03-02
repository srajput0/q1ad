import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext, PollAnswerHandler
)
from chat_data_handler import load_chat_data, save_chat_data, add_served_chat, add_served_user, get_active_quizzes
from quiz_handler import send_quiz, send_quiz_immediately, handle_poll_answer, show_leaderboard
from admin_handler import broadcast
from datetime import datetime
from pymongo import MongoClient  # Import MongoClient
from telegram.error import BadRequest

# Enable logging
from bot_logging import logger

TOKEN = "5554891157:AAFG4gZzQ26-ynwQVEnyv1NlZ9Dx0Sx42Hg"
ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

# MongoDB connection
MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]

def start_command(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    # Register the chat and user for broadcasting
    add_served_chat(chat_id)
    add_served_user(user_id)

    # Inline buttons for category selection
    keyboard = [
        [InlineKeyboardButton("SSC", callback_data='category_ssc')],
        [InlineKeyboardButton("UPSC", callback_data='category_upsc')],
        [InlineKeyboardButton("BPSC", callback_data='category_bpsc')],
        [InlineKeyboardButton("RRB", callback_data='category_rrb')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send welcome message with category selection buttons
    update.message.reply_text(
        "Welcome to the Quiz Bot! Please select your category:",
        reply_markup=reply_markup
    )

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    chat_id = str(query.message.chat.id)
    chat_data = load_chat_data(chat_id)

    if query.data.startswith('category_'):
        category = query.data.split('_')[1]
        chat_data['category'] = category
        save_chat_data(chat_id, chat_data)

        # Inline buttons for selecting sendgroup or prequiz
        keyboard = [
            [InlineKeyboardButton("Send Group", callback_data='sendgroup')],
            [InlineKeyboardButton("Prequiz", callback_data='prequiz')],
            [InlineKeyboardButton("Back", callback_data='back_to_categories')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text=f"Category selected: {category.upper()}\nPlease select an option:",
                                reply_markup=reply_markup)
    elif query.data == 'back_to_categories':
        # Inline buttons for category selection
        keyboard = [
            [InlineKeyboardButton("SSC", callback_data='category_ssc')],
            [InlineKeyboardButton("UPSC", callback_data='category_upsc')],
            [InlineKeyboardButton("BPSC", callback_data='category_bpsc')],
            [InlineKeyboardButton("RRB", callback_data='category_rrb')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Welcome to the Quiz Bot! Please select your category:",
                                reply_markup=reply_markup)
    elif query.data in ['sendgroup', 'prequiz']:
        # Send the set interval command
        if query.data == 'sendgroup' and update.effective_chat.type not in ['group', 'supergroup']:
            query.edit_message_text(text="The Send Group option is only available in group and supergroup chats.")
            return
        elif query.data == 'prequiz' and update.effective_chat.type != 'private':
            query.edit_message_text(text="The Prequiz option is only available in private chats.")
            return

        # Save the selected option in chat data
        chat_data['selected_option'] = query.data
        save_chat_data(chat_id, chat_data)

        # Inline buttons for interval selection
        keyboard = [
            [InlineKeyboardButton("30 sec", callback_data='interval_30')],
            [InlineKeyboardButton("1 min", callback_data='interval_60')],
            [InlineKeyboardButton("5 min", callback_data='interval_300')],
            [InlineKeyboardButton("20 min", callback_data='interval_1200')],
            [InlineKeyboardButton("30 min", callback_data='interval_1800')],
            [InlineKeyboardButton("60 min", callback_data='interval_3600')],
            [InlineKeyboardButton("Back", callback_data='back_to_categories')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Please select the interval for the quiz:", reply_markup=reply_markup)
    elif query.data.startswith('interval_'):
        interval = int(query.data.split('_')[1])
        chat_data["interval"] = interval
        save_chat_data(chat_id, chat_data)
        try:
            context.bot.send_message(chat_id=chat_id, text=f"The quiz will start immediately and then follow an interval of {interval} seconds. Please wait...")
            start_quiz_from_button(query, context)
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")

def start_quiz_from_button(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id if update.effective_chat else update.message.chat.id)
    chat_data = load_chat_data(chat_id)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent and quizzes_sent.get("count", 0) >= 10:
        try:
            context.bot.send_message(chat_id=chat_id, text="You have reached your daily limit. The next quiz will be sent tomorrow.")
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")
        return

    interval = chat_data.get("interval")
    if not interval:
        try:
            context.bot.send_message(chat_id=chat_id, text="Please set an interval first using /setinterval <seconds> or selecting from the provided options.")
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")
        return
    
    chat_data["active"] = True
    save_chat_data(chat_id, chat_data)

    # Send the first quiz immediately
    send_quiz_immediately(context, chat_id)

    # Schedule subsequent quizzes at the specified interval
    context.job_queue.run_repeating(send_quiz, interval=interval, first=interval, context={"chat_id": chat_id, "used_questions": []})

def send_quiz_immediately(context: CallbackContext, chat_id: str):
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 10:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    else:
        try:
            context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")
        return

    if not questions:
        try:
            context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")
        return

    used_question_ids = chat_data.get("used_questions", [])
    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        try:
            context.bot.send_message(chat_id=chat_id, text="No more new questions available.")
        except BadRequest as e:
            logger.error(f"Failed to send message: {e}")
        return

    question = random.choice(available_questions)
    used_question_ids.append(question)
    chat_data["used_questions"] = used_question_ids
    save_chat_data(chat_id, chat_data)

    try:
        message = context.bot.send_poll(
            chat_id=chat_id,
            question=question['question'],
            options=question['options'],
            type='quiz',
            correct_option_id=question['correct_option_id'],
            is_anonymous=False
        )
    except BadRequest as e:
        logger.error(f"Failed to send poll: {e}")
        return

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

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

    if quizzes_sent and quizzes_sent.get("count", 0) >= 10:
        update.message.reply_text("You have reached your daily limit. The next quiz will be sent tomorrow.")
        return

    if chat_data.get("active", False):
        update.message.reply_text("A quiz is already running in this chat!")
        return

    interval = chat_data.get("interval")
    if not interval:
        update.message.reply_text("Please set an interval first using /setinterval <seconds> or selecting from the provided options.")
        return

    chat_data["active"] = True
    save_chat_data(chat_id, chat_data)

    update.message.reply_text(f"Quiz started! Interval: {interval} seconds.")

    # Send the first quiz immediately
    send_quiz_immediately(context, chat_id)

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

    interval = chat_data.get("interval")
    if not interval:
        update.message.reply_text("Please set an interval first using /setinterval <seconds> or selecting from the provided options.")
        return

    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

    update.message.reply_text("Quiz resumed successfully.")

def restart_active_quizzes(context: CallbackContext):
    active_quizzes = get_active_quizzes()
    for quiz in active_quizzes:
        chat_id = quiz["chat_id"]
        interval = quiz["data"].get("interval")
        if not interval:
            continue
        context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": quiz["data"].get("used_questions", [])})

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("setinterval", set_interval))
    dp.add_handler(CommandHandler("stopquiz", stop_quiz))
    dp.add_handler(CommandHandler("pause", pause_quiz))
    dp.add_handler(CommandHandler("resume", resume_quiz))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(PollAnswerHandler(handle_poll_answer))
    dp.add_handler(CommandHandler("leaderboard", show_leaderboard))
    dp.add_handler(CommandHandler("broadcast", broadcast))
    
    updater.start_polling()
    updater.job_queue.run_once(restart_active_quizzes, 0)

    updater.idle()

if __name__ == '__main__':
    main()
