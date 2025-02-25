import json
import random
from telegram import Poll
from bot_logging import logger

QUIZZES_FILE = 'quizzes/quizzes.json'

# Load quizzes
def load_quizzes():
    if os.path.exists(QUIZZES_FILE):
        with open(QUIZZES_FILE, 'r') as file:
            try:
                quizzes = json.load(file)
                random.shuffle(quizzes)
                return quizzes
            except json.JSONDecodeError:
                return []
    return []

quizzes = load_quizzes()

def send_quiz(context):
    job = context.job
    chat_id = job.context["chat_id"]
    used_questions = job.context["used_questions"]

    available_quizzes = [q for q in quizzes if q not in used_questions]
    if not available_quizzes:
        job.schedule_removal()
        return
    
    quiz = random.choice(available_quizzes)
    used_questions.append(quiz)

    try:
        context.bot.send_poll(
            chat_id=chat_id,
            question=quiz["question"],
            options=quiz["options"],
            type=Poll.QUIZ,
            correct_option_id=quiz["options"].index(quiz["answer"]),
            is_anonymous=False
        )
    except Exception as e:
        logger.error(f"Failed to send quiz to {chat_id}: {e}")

def handle_poll_answer(update, context):
    from functions.leaderboard_handler import load_leaderboard, save_leaderboard
    poll_answer = update.poll_answer
    user_id = str(poll_answer.user.id)
    selected_option = poll_answer.option_ids[0] if poll_answer.option_ids else None
    leaderboard = load_leaderboard()

    for quiz in quizzes:
        correct_option = quiz["options"].index(quiz["answer"])
        if selected_option == correct_option:
            leaderboard[user_id] = leaderboard.get(user_id, 0) + 1
            save_leaderboard(leaderboard)
            return

def show_leaderboard(update, context):
    from functions.leaderboard_handler import load_leaderboard
    leaderboard = load_leaderboard()

    if not leaderboard:
        update.message.reply_text("🏆 No scores yet! Start playing to appear on the leaderboard.")
        return

    sorted_scores = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    message = "🏆 *Quiz Leaderboard* 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for rank, (user_id, score) in enumerate(sorted_scores[:10], start=1):
        try:
            user = context.bot.get_chat(int(user_id))
            username = f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}"
        except Exception:
            username = f"User {user_id}"

        rank_display = medals[rank - 1] if rank <= 3 else f"#{rank}"
        message += f"{rank_display} *{username}* - {score} points\n"

    update.message.reply_text(message, parse_mode="Markdown")
