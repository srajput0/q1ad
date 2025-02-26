import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackContext, PollAnswerHandler
)
from chat_data_handler import load_chat_data, save_chat_data
from quiz_handler import send_quiz, handle_poll_answer, show_leaderboard
from admin_handler import broadcast

# Enable logging
from bot_logging import logger

TOKEN = "5554891157:AAFG4gZzQ26-ynwQVEnyv1NlZ9Dx0Sx42Hg"
ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

async def start_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data()

    if chat_id in chat_data and chat_data[chat_id].get("active", False):
        await update.message.reply_text("A quiz is already running in this chat!")
        return

    interval = chat_data.get(chat_id, {}).get("interval", 30)
    chat_data[chat_id] = {"active": True, "interval": interval}
    save_chat_data(chat_data)

    await update.message.reply_text(f"Quiz started! Interval: {interval} seconds.")
    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

async def sendgroup(update: Update, context: CallbackContext):
    if update.effective_chat.type in ["group", "supergroup"]:
        await start_quiz(update, context)
    else:
        await update.message.reply_text("This command can only be used in a group chat.")

async def prequiz(update: Update, context: CallbackContext):
    if update.effective_chat.type == "private":
        await start_quiz(update, context)
    else:
        await update.message.reply_text("This command can only be used in a private chat.")

async def stop_quiz(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data()

    if chat_id in chat_data:
        del chat_data[chat_id]
        save_chat_data(chat_data)

        jobs = context.job_queue.jobs()
        for job in jobs:
            if job.context and job.context["chat_id"] == chat_id:
                job.schedule_removal()

        await update.message.reply_text("Quiz stopped successfully.")
    else:
        await update.message.reply_text("No active quiz to stop.")

async def set_interval(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /setinterval <seconds>")
        return
    
    interval = int(context.args[0])
    if interval < 10:
        await update.message.reply_text("Interval must be at least 10 seconds.")
        return

    chat_data = load_chat_data()
    if chat_id not in chat_data:
        await update.message.reply_text("No active quiz. Interval saved for future quizzes.")
        chat_data[chat_id] = {"active": False, "interval": interval}
        save_chat_data(chat_data)
        return

    chat_data[chat_id]["interval"] = interval
    save_chat_data(chat_data)

    jobs = context.job_queue.jobs()
    for job in jobs:
        if job.context and job.context["chat_id"] == chat_id:
            job.schedule_removal()

    await update.message.reply_text(f"Quiz interval updated to {interval} seconds. Restarting quiz...")
    context.job_queue.run_repeating(send_quiz, interval=interval, first=0, context={"chat_id": chat_id, "used_questions": []})

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Welcome! Use /sendgroup to start a quiz in a group or /prequiz to start a quiz personally.")

def main():
    # Create the Application object
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sendgroup", sendgroup))
    application.add_handler(CommandHandler("prequiz", prequiz))
    application.add_handler(CommandHandler("stopquiz", stop_quiz))
    application.add_handler(CommandHandler("setinterval", set_interval))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(CommandHandler("leaderboard", show_leaderboard))
    application.add_handler(CommandHandler("broadcast", broadcast))

    # Start polling and handle messages
    application.run_polling()

if __name__ == '__main__':
    main()
