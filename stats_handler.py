from datetime import datetime
import pytz
from typing import Dict, Any, Tuple, Optional
from pymongo import MongoClient, DESCENDING
import logging
from telegram import Update, Poll, PollAnswer, Bot
from telegram.ext import CallbackContext
from telegram.error import TelegramError

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StatsManager:
    def __init__(self, mongodb_uri: str):
        """Initialize StatsManager with MongoDB connection"""
        self.client = MongoClient(mongodb_uri)
        self.db = self.client['telegram_bot']
        self.user_stats = self.db['user_stats']
        self.quiz_attempts = self.db['quiz_attempts']
        self.quiz_data = self.db['quiz_data']
        
        # Points configuration
        self.CORRECT_POINTS = 2  # 2 points for correct answer
        self.INCORRECT_POINTS = 0  # 0 points for incorrect answer
        
        # Create indexes
        self._create_indexes()

    def _create_indexes(self):
        """Create MongoDB indexes for better performance"""
        try:
            self.user_stats.create_index([("user_id", DESCENDING)])
            self.quiz_attempts.create_index([("user_id", DESCENDING)])
            self.quiz_attempts.create_index([("timestamp", DESCENDING)])
            self.quiz_data.create_index([("poll_id", DESCENDING)])
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

    def handle_poll_answer(self, update: Update, context: CallbackContext) -> None:
        """Handle poll answers with quiz data verification"""
        try:
            answer = update.poll_answer
            if not answer or not answer.option_ids:
                return

            user_id = str(answer.user.id)
            poll_id = answer.poll_id
            selected_option = answer.option_ids[0]

            # Get quiz data
            quiz_data = self.quiz_data.find_one({"poll_id": poll_id})
            if not quiz_data:
                logger.warning(f"No quiz data found for poll {poll_id}")
                return

            # Get user data for username
            chat_member = None
            try:
                chat_id = quiz_data.get('chat_id')
                if chat_id:
                    chat_member = context.bot.get_chat_member(chat_id, user_id)
            except TelegramError:
                pass

            username = (
                chat_member.user.username if chat_member 
                else f"user_{user_id}"
            )

            # Check answer correctness
            correct_option = quiz_data.get('correct_option')
            is_correct = selected_option == correct_option

            # Record attempt and update stats
            points = self.CORRECT_POINTS if is_correct else self.INCORRECT_POINTS
            self.record_quiz_attempt(user_id, is_correct, poll_id, points, username)

            # Send feedback message
            try:
                current_time = datetime.now(pytz.UTC)
                stats = self.get_user_stats(user_id)
                
                feedback_message = (
                    f"📝 Answer by @{username}\n"
                    f"{'✅ Correct! (+2 points)' if is_correct else '❌ Wrong! (0 points)'}\n"
                    f"Current Score: {stats['score_points']} points\n"
                    f"Rank: #{stats['rank']}\n"
                    f"Time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

                if chat_id := quiz_data.get('chat_id'):
                    context.bot.send_message(
                        chat_id=chat_id,
                        text=feedback_message,
                        reply_to_message_id=quiz_data.get('message_id')
                    )
            except Exception as e:
                logger.error(f"Error sending feedback: {e}")

        except Exception as e:
            logger.error(f"Error in handle_poll_answer: {e}")

    def record_quiz_attempt(self, user_id: str, is_correct: bool, quiz_id: str, 
                          points: int, username: str) -> None:
        """Record quiz attempt with points system"""
        try:
            current_time = datetime.now(pytz.UTC)
            
            # Record the attempt
            self.quiz_attempts.insert_one({
                "user_id": user_id,
                "quiz_id": quiz_id,
                "is_correct": is_correct,
                "points": points,
                "timestamp": current_time
            })
            
            # Update user statistics
            update_query = {
                "$inc": {
                    "total_attempts": 1,
                    "correct_answers": 1 if is_correct else 0,
                    "incorrect_answers": 0 if is_correct else 1,
                    "score_points": points
                },
                "$set": {
                    "last_attempt": current_time,
                    "username": username
                },
                "$setOnInsert": {
                    "first_attempt": current_time
                }
            }
            
            self.user_stats.update_one(
                {"user_id": user_id},
                update_query,
                upsert=True
            )
            
            logger.info(
                f"Recorded quiz attempt for {username} (ID: {user_id}): "
                f"{'Correct (+2 points)' if is_correct else 'Wrong (0 points)'}"
            )
            
        except Exception as e:
            logger.error(f"Error recording quiz attempt: {e}")

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
        try:
            stats = self.user_stats.find_one({"user_id": user_id}) or {}
            total_users = self.user_stats.count_documents({})
            
            # Calculate rank
            rank = self.user_stats.count_documents({
                "score_points": {"$gt": stats.get("score_points", 0)}
            }) + 1
            
            # Calculate percentile
            users_below = self.user_stats.count_documents({
                "score_points": {"$lt": stats.get("score_points", 0)}
            })
            percentile = (users_below / total_users * 100) if total_users > 0 else 0
            
            return {
                "score_points": stats.get("score_points", 0),
                "rank": rank,
                "percentile": round(percentile, 2),
                "total_attempts": stats.get("total_attempts", 0),
                "correct_answers": stats.get("correct_answers", 0),
                "incorrect_answers": stats.get("incorrect_answers", 0),
                "accuracy": round(
                    (stats.get("correct_answers", 0) / stats.get("total_attempts", 1)) * 100 
                    if stats.get("total_attempts", 0) > 0 else 0,
                    2
                ),
                "first_attempt": stats.get("first_attempt", datetime.now(pytz.UTC)),
                "last_attempt": stats.get("last_attempt", datetime.now(pytz.UTC)),
                "username": stats.get("username", f"user_{user_id}")
            }
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}

    def get_recent_attempts(self, user_id: str, limit: int = 5) -> list:
        """Get user's recent quiz attempts"""
        try:
            recent = self.quiz_attempts.find(
                {"user_id": user_id}
            ).sort("timestamp", DESCENDING).limit(limit)
            
            return [{
                "quiz_id": attempt["quiz_id"],
                "is_correct": attempt["is_correct"],
                "points": attempt["points"],
                "timestamp": attempt["timestamp"]
            } for attempt in recent]
        except Exception as e:
            logger.error(f"Error getting recent attempts: {e}")
            return []

    def format_stats_message(self, user_id: str, username: str) -> str:
        """Format user statistics into a readable message"""
        stats = self.get_user_stats(user_id)
        recent = self.get_recent_attempts(user_id)
        
        # Determine rank emoji
        percentile = stats["percentile"]
        if percentile >= 90: rank_emoji = "🏆"
        elif percentile >= 70: rank_emoji = "🌟"
        elif percentile >= 50: rank_emoji = "⭐"
        else: rank_emoji = "🎯"
        
        message = (
            f"📊 *Statistics for {username}* {rank_emoji}\n\n"
            f"*Score Points:* {stats['score_points']} 📈\n"
            f"*Global Rank:* #{stats['rank']} 🌍\n"
            f"*Percentile:* {stats['percentile']}% 📊\n\n"
            f"*Quiz Performance*\n"
            f"Total Attempted: {stats['total_attempts']} ✍️\n"
            f"Correct Answers: {stats['correct_answers']} ✅\n"
            f"Incorrect Answers: {stats['incorrect_answers']} ❌\n"
            f"Accuracy: {stats['accuracy']}% 🎯\n\n"
            f"*Recent Activity*\n"
        )
        
        if recent:
            for i, attempt in enumerate(recent, 1):
                status = "✅ +2" if attempt["is_correct"] else "❌ 0"
                time = attempt["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
                message += f"{i}. Quiz {attempt['quiz_id']}: {status} ({time})\n"
        else:
            message += "No recent activity\n"
        
        message += (
            f"\n_First Quiz: {stats['first_attempt'].strftime('%Y-%m-% d %H:%M:%S')}_\n"
            f"_Last Quiz: {stats['last_attempt'].strftime('%Y-%m-% d %H:%M:%S')}_"
        )
        
        return message

def get_stats_command(update: Update, context: CallbackContext):
    """Handler for /stats command"""
    try:
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or update.effective_user.first_name
        
        # Send initial "calculating" message
        message = update.message.reply_text(
            "📊 Calculating your statistics...",
            parse_mode='Markdown'
        )
        
        # Get stats manager instance
        stats_manager = context.bot_data.get('stats_manager')
        if not stats_manager:
            stats_manager = StatsManager(context.bot_data.get('MONGO_URI'))
            context.bot_data['stats_manager'] = stats_manager
        
        # Get and send formatted stats
        stats_message = stats_manager.format_stats_message(user_id, username)
        message.edit_text(
            stats_message,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in get_stats_command: {e}")
        update.message.reply_text(
            "❌ Sorry, there was an error getting your statistics. Please try again later."
        )
