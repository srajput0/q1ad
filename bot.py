import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, CallbackContext, PollAnswerHandler
)
from chat_data_handler import load_chat_data, save_chat_data, add_served_chat, add_served_user, get_active_quizzes
from quiz_handler import send_quiz, handle_poll_answer, show_leaderboard
from admin_handler import broadcast

# Enable logging
from bot_logging import logger

TOKEN = "5554891157:AAFG4gZzQ26-ynwQVEnyv1NlZ9Dx0Sx42Hg"
ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

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
        query.edit_message_text(text=f"Category selected: {category.upper()}\nUse /sendgroup to start a quiz in a group or /prequiz to start a quiz personally.")

def start_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)

    if chat_data.get("active", False):
        update.message.reply_text("A quiz is already running in this chat!")
        return

    interval = chat_data.get("interval", 30)
    chat_data = {"active": True, "interval": interval, "category": chat_data.get("category", "general")}
    save_chat_data(chat_id, chat_data)

    update.message.reply_text(f"Quiz started! Interval: {interval} seconds.")
    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

def sendgroup(update: Update, context: CallbackContext):
    if update.effective_chat.type in ["group", "supergroup"]:
        start_quiz(update, context)
    else:
        update.message.reply_text("This command can only be used in a group chat.")

def prequiz(update: Update, context: CallbackContext):
    if update.effective_chat.type == "private":
        start_quiz(update, context)
    else:
        update.message.reply_text("This command can only be used in a private chat.")

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

    jobs = context.job_queue.jobs()
    for job in jobs:
        if job.context and job.context["chat_id"] == chat_id:
            job.schedule_removal()

    update.message.reply_text(f"Quiz interval updated to {interval} seconds. Restarting quiz...")
    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

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
        context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("sendgroup", sendgroup))
    dp.add_handler(CommandHandler("prequiz", prequiz))
    dp.add_handler(CommandHandler("stopquiz", stop_quiz))
    dp.add_handler(CommandHandler("setinterval", set_interval))
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
