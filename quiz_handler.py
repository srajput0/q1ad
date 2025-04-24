import logging
from telegram import Update
# from telegram.ext import CallbackContext
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, Filters, ConversationHandler
from chat_data_handler import load_chat_data, save_chat_data
from leaderboard_handler import add_score, get_top_scores
import random
import json
import os
from pymongo import MongoClient
from datetime import datetime, timedelta
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = "mongodb+srv://asrushfig:2003@cluster0.6vdid.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client["telegram_bot"]
quizzes_sent_collection = db["quizzes_sent"]
used_quizzes_collection = db["used_quizzes"]
message_status_collection = db["message_status"]

MAX_QUIZZES_PER_SESSION = 2

(EDIT_QUESTION, EDIT_OPTIONS, EDIT_CORRECT_OPTION) = range(3)

# Fetch admins from the database or hardcode for now
QUIZ_CORRECTION_ADMINS = [5050578106]  # Replace with actual admin IDs

# Function to check if a user is a Quiz Correction Admin
def is_quiz_correction_admin(user_id):
    return user_id in QUIZ_CORRECTION_ADMINS

# Start the edit quiz process
def edit_quiz(update: Update, context: CallbackContext):
    if update.effective_user.id not in QUIZ_CORRECTION_ADMINS:
        update.message.reply_text("You are not authorized to edit quizzes.")
        return ConversationHandler.END

    # Ensure the command is used as a reply to a quiz question
    if not update.message.reply_to_message or not update.message.reply_to_message.poll:
        update.message.reply_text("Please reply to the quiz you want to edit with the /editquiz command.")
        return ConversationHandler.END

    # Save the quiz details into the context for editing
    poll = update.message.reply_to_message.poll
    context.user_data['quiz'] = {
        'question': poll.question,
        'options': poll.options,
        'correct_option_id': poll.correct_option_id
    }

    update.message.reply_text(
        f"Editing Quiz:\n\n"
        f"Question: {poll.question}\n"
        f"Options: {', '.join([option.text for option in poll.options])}\n"
        f"Correct Option: {poll.correct_option_id + 1}\n\n"
        "Send the corrected question text or send /skip to keep the current question."
    )
    return EDIT_QUESTION

# Edit the question text
def edit_question(update: Update, context: CallbackContext):
    context.user_data['quiz']['question'] = update.message.text
    update.message.reply_text(
        f"New Question: {update.message.text}\n\n"
        "Now send the corrected options separated by commas (e.g., Option 1, Option 2, Option 3, Option 4)."
    )
    return EDIT_OPTIONS

# Skip editing the question text
def skip_question(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Keeping the current question text.\n\n"
        "Now send the corrected options separated by commas (e.g., Option 1, Option 2, Option 3, Option 4)."
    )
    return EDIT_OPTIONS

# Edit the options
def edit_options(update: Update, context: CallbackContext):
    options = update.message.text.split(',')
    if len(options) < 2:
        update.message.reply_text("A quiz must have at least 2 options. Please send the corrected options.")
        return EDIT_OPTIONS

    context.user_data['quiz']['options'] = [option.strip() for option in options]
    update.message.reply_text(
        f"New Options: {', '.join(context.user_data['quiz']['options'])}\n\n"
        "Now send the correct option number (e.g., 1 for the first option, 2 for the second, etc.)."
    )
    return EDIT_CORRECT_OPTION

# Edit the correct option
def edit_correct_option(update: Update, context: CallbackContext):
    try:
        correct_option_id = int(update.message.text) - 1
        if correct_option_id < 0 or correct_option_id >= len(context.user_data['quiz']['options']):
            raise ValueError
    except ValueError:
        update.message.reply_text("Invalid option number. Please send the correct option number again.")
        return EDIT_CORRECT_OPTION

    context.user_data['quiz']['correct_option_id'] = correct_option_id
    save_corrected_quiz(context.user_data['quiz'])
    update.message.reply_text("Quiz has been successfully updated.")
    return ConversationHandler.END

# Save the corrected quiz back to the database
def save_corrected_quiz(quiz):
    category = "general"  # Assume a default category, or fetch from context if available
    file_path = os.path.join('quizzes', f'{category}.json')

    # Load the existing quizzes from file
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            questions = json.load(f)
    else:
        questions = []

    # Find the quiz to update
    for q in questions:
        if q['question'] == quiz['question']:
            q.update(quiz)
            break
    else:
        # If not found, add as a new quiz
        questions.append(quiz)

    # Save the updated quizzes back to file
    with open(file_path, 'w') as f:
        json.dump(questions, f, indent=4)

# Cancel the edit process
def cancel_edit(update: Update, context: CallbackContext):
    update.message.reply_text("Quiz editing has been cancelled.")
    return ConversationHandler.END

# Conversation handler for editing quizzes
edit_quiz_handler = ConversationHandler(
    entry_points=[CommandHandler('editquiz', edit_quiz)],
    states={
        EDIT_QUESTION: [
            MessageHandler(Filters.text & ~Filters.command, edit_question),
            CommandHandler('skip', skip_question)
        ],
        EDIT_OPTIONS: [MessageHandler(Filters.text & ~Filters.command, edit_options)],
        EDIT_CORRECT_OPTION: [MessageHandler(Filters.text & ~Filters.command, edit_correct_option)]
    },
    fallbacks=[CommandHandler('cancel', cancel_edit)]
)

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

    chat_type = context.job.context.get('chat_type', 'private')
    if chat_type != 'private':
        logger.info(f"Quiz feature is skipped for non-private chats: {chat_type}")
        return

    if chat_data.get('quiz_count', 0) >= MAX_QUIZZES_PER_SESSION:
        # Send a message to ask if the user wants to continue
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data='continue_quiz'),
                InlineKeyboardButton("No", callback_data='stop_quiz')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=chat_id,
            text="You have completed 20 quizzes. Do you want to continue?",
            reply_markup=reply_markup
        )
        return

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})
    message_status = message_status_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 100:
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

    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        # Reset used questions if no new questions are available
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$set": {"used_questions": []}})
        used_question_ids = []
        available_questions = questions
        context.bot.send_message(chat_id=chat_id, text="All quizzes have been used. Restarting with all available quizzes.")

    question = random.choice(available_questions)
    used_questions.append(question)
    if used_question_ids:
        used_quizzes_collection.update_one({"chat_id": chat_id}, {"$push": {"used_questions": question}})
    else:
        used_quizzes_collection.insert_one({"chat_id": chat_id, "used_questions": [question]})

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
        logger.error(f"Failed to send quiz to chat {chat_id}: {e}")
        context.bot.send_message(chat_id=chat_id, text="Failed to send quiz. Please check the chat ID and permissions.")
        return

    context.bot_data[message.poll.id] = {
        'chat_id': chat_id,
        'correct_option_id': question['correct_option_id']
    }

def send_quiz_immediately(context: CallbackContext, chat_id: str):
    chat_data = load_chat_data(chat_id)

    category = chat_data.get('category', 'general')  # Default category if not set
    questions = load_quizzes(category)

    today = datetime.now().date().isoformat()  # Convert date to string
    quizzes_sent = quizzes_sent_collection.find_one({"chat_id": chat_id, "date": today})

    if quizzes_sent is None:
        quizzes_sent_collection.insert_one({"chat_id": chat_id, "date": today, "count": 1})
    elif quizzes_sent["count"] < 100:
        quizzes_sent_collection.update_one({"chat_id": chat_id, "date": today}, {"$inc": {"count": 1}})
    else:
        context.bot.send_message(chat_id=chat_id, text="Daily quiz limit reached. The next quiz will be sent tomorrow.")
        return

    if not questions:
        context.bot.send_message(chat_id=chat_id, text="No questions available for this category.")
        return

    used_question_ids = chat_data.get("used_questions", [])
    available_questions = [q for q in questions if q not in used_question_ids]
    if not available_questions:
        # Reset used questions if no new questions are available
        chat_data["used_questions"] = []
        save_chat_data(chat_id, chat_data)
        available_questions = questions
        context.bot.send_message(chat_id=chat_id, text="All quizzes have been used. Restarting with all available quizzes.")

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



def repeat_all_quizzes(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    chat_data = load_chat_data(chat_id)
    
    # Clear the used_questions list to repeat all quizzes
    chat_data["used_questions"] = []
    save_chat_data(chat_id, chat_data)
    
    update.message.reply_text("All quizzes have been reset and can be repeated.")
