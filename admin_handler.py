import logging
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
from chat_data_handler import load_chat_data, get_served_chats, get_served_users
from telegram.error import TimedOut, NetworkError, RetryAfter, BadRequest, Unauthorized
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any
import time
from collections import deque

logger = logging.getLogger(__name__)

ADMIN_ID = 5050578106  # Your admin ID

class BroadcastManager:
    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.message_queue = deque()
        self.batch_size = 100
        self.rate_limit = 30  # messages per second
        self.last_sent = time.time()
        self.stats = {
            'total_sent': 0,
            'failed_attempts': 0,
            'retry_success': 0
        }
        
    async def broadcast_to_all(self, bot, text_content: str, content_type: str, 
                             file_id: str = None, reply_markup: Any = None) -> Dict[str, int]:
        chats = list(get_served_chats())
        users = list(get_served_users())
        sent_counts = {'chats': 0, 'users': 0, 'failed': 0}
        
        # Split into batches
        chat_batches = [chats[i:i + self.batch_size] for i in range(0, len(chats), self.batch_size)]
        user_batches = [users[i:i + self.batch_size] for i in range(0, len(users), self.batch_size)]
        
        async def process_batch(items: List[Dict], is_chat: bool):
            for item in items:
                target_id = item['chat_id' if is_chat else 'user_id']
                
                # Rate limiting
                current_time = time.time()
                if current_time - self.last_sent < 1/self.rate_limit:
                    await asyncio.sleep(1/self.rate_limit - (current_time - self.last_sent))
                
                try:
                    if content_type == 'photo':
                        await bot.send_photo(
                            chat_id=target_id,
                            photo=file_id,
                            caption=text_content,
                            reply_markup=reply_markup
                        )
                    else:
                        await bot.send_message(
                            chat_id=target_id,
                            text=text_content,
                            reply_markup=reply_markup
                        )
                    
                    if is_chat:
                        sent_counts['chats'] += 1
                    else:
                        sent_counts['users'] += 1
                    
                    self.stats['total_sent'] += 1
                    self.last_sent = time.time()
                    
                except Exception as e:
                    sent_counts['failed'] += 1
                    self.stats['failed_attempts'] += 1
                    logger.error(f"Error broadcasting to {'chat' if is_chat else 'user'} {target_id}: {e}")
                    continue
                
                # Memory cleanup after each batch
                if (sent_counts['chats'] + sent_counts['users']) % self.batch_size == 0:
                    import gc
                    gc.collect()
        
        # Process chat batches
        for batch in chat_batches:
            await process_batch(batch, True)
            await asyncio.sleep(1)  # Prevent overloading
            
        # Process user batches
        for batch in user_batches:
            await process_batch(batch, False)
            await asyncio.sleep(1)  # Prevent overloading
            
        return sent_counts

    def get_stats(self) -> Dict[str, int]:
        """Get broadcast statistics"""
        return {
            'total_sent': self.stats['total_sent'],
            'failed_attempts': self.stats['failed_attempts'],
            'retry_success': self.stats['retry_success'],
            'queue_size': len(self.message_queue)
        }

# Initialize the broadcast manager
broadcast_manager = BroadcastManager(max_workers=8)

def broadcast(update: Update, context: CallbackContext):
    """Handle broadcast command with status updates"""
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    # Send initial status message
    status_message = update.message.reply_text(
        "🚀 Starting broadcast...\n"
        "Please wait while the messages are being sent."
    )
    
    try:
        # Get content from message
        if update.message.reply_to_message:
            if update.message.reply_to_message.photo:
                content_type = 'photo'
                file_id = update.message.reply_to_message.photo[-1].file_id
                text_content = update.message.reply_to_message.caption or ''
            else:
                content_type = 'text'
                text_content = update.message.reply_to_message.text
        else:
            message = ' '.join(context.args)
            if not message:
                status_message.edit_text(
                    "❌ Usage:\n"
                    "1. Reply to a message with /broadcast\n"
                    "2. Or use: /broadcast <your message>"
                )
                return
            content_type = 'text'
            text_content = message

        reply_markup = (update.message.reply_to_message.reply_markup 
                       if hasattr(update.message.reply_to_message, 'reply_markup') 
                       else None)

        # Update status message
        status_message.edit_text(
            "📤 Broadcasting in progress...\n"
            "This may take a while for large numbers of users."
        )

        # Run broadcast asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            broadcast_manager.broadcast_to_all(
                context.bot,
                text_content,
                content_type,
                file_id if content_type == 'photo' else None,
                reply_markup
            )
        )
        
        # Get final statistics
        stats = broadcast_manager.get_stats()
        
        # Update status message with results
        status_message.edit_text(
            "✅ *Broadcast Completed*\n\n"
            f"📊 *Results:*\n"
            f"└ Sent to chats: {results['chats']}\n"
            f"└ Sent to users: {results['users']}\n"
            f"└ Failed: {results['failed']}\n\n"
            f"📈 *Total Statistics:*\n"
            f"└ Total messages sent: {stats['total_sent']}\n"
            f"└ Total failed attempts: {stats['failed_attempts']}\n"
            f"└ Successful retries: {stats['retry_success']}",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        status_message.edit_text(
            f"❌ *Broadcast Failed*\n\n"
            f"Error: {str(e)}",
            parse_mode='Markdown'
        )

def broadcast_stats(update: Update, context: CallbackContext):
    """Show broadcast statistics"""
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("⚠️ This command is only available for administrators.")
        return

    try:
        stats = broadcast_manager.get_stats()
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        stats_message = (
            "📨 *Broadcast System Statistics*\n"
            f"🕒 Time (UTC): {current_time}\n\n"
            "*Performance Metrics:*\n"
            f"├ Total Messages Sent: {stats['total_sent']}\n"
            f"├ Failed Attempts: {stats['failed_attempts']}\n"
            f"├ Retry Successes: {stats['retry_success']}\n"
            f"└ Current Queue Size: {stats['queue_size']}"
        )

        update.message.reply_text(
            stats_message,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Error getting broadcast stats: {e}")
        update.message.reply_text(
            "❌ Error fetching statistics. Please try again later."
        )
