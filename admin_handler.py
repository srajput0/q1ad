

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

class BroadcastManager:
    def __init__(self, max_workers: int = 8):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.message_queue = deque()
        self.batch_size = 100
        self.rate_limit = 30  # messages per second
        self.last_sent = time.time()
        
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
                        
                    self.last_sent = time.time()
                    
                except Exception as e:
                    sent_counts['failed'] += 1
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

broadcast_manager = BroadcastManager()

def broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    status_message = update.message.reply_text("Starting broadcast...")
    
    try:
        # Get content
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
                update.message.reply_text("Usage: /broadcast <message>")
                return
            content_type = 'text'
            text_content = message

        reply_markup = (update.message.reply_to_message.reply_markup 
                       if hasattr(update.message.reply_to_message, 'reply_markup') 
                       else None)

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
        
        status_message.edit_text(
            f"Broadcast completed!\n"
            f"✅ Sent to {results['chats']} chats\n"
            f"👤 Sent to {results['users']} users\n"
            f"❌ Failed: {results['failed']}"
        )
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        status_message.edit_text(f"Broadcast failed: {str(e)}")



# logger = logging.getLogger(__name__)

# ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

# def broadcast(update: Update, context: CallbackContext):
#     if update.effective_user.id != ADMIN_ID:
#         update.message.reply_text("You are not authorized to use this command.")
#         return

#     # Determine if the message is a photo or text
#     if update.message.reply_to_message:
#         if update.message.reply_to_message.photo:
#             content_type = 'photo'
#             file_id = update.message.reply_to_message.photo[-1].file_id
#             text_content = update.message.reply_to_message.caption
#         else:
#             content_type = 'text'
#             text_content = update.message.reply_to_message.text
#     else:
#         message = ' '.join(context.args)
#         if not message:
#             update.message.reply_text("Usage: /broadcast <message>")
#             return
#         content_type = 'text'
#         text_content = message

#     reply_markup = update.message.reply_to_message.reply_markup if hasattr(update.message.reply_to_message, 'reply_markup') else None

#     sent_chats, sent_users = broadcast_to_all(context.bot, text_content, content_type, file_id if content_type == 'photo' else None, reply_markup, update.message)
#     update.message.reply_text(f"Broadcast completed! Sent to {sent_chats} chats and {sent_users} users.")

# def broadcast_to_all(bot, text_content, content_type, file_id, reply_markup, message):
#     sent_chats = 0
#     sent_users = 0

#     for chat in get_served_chats():
#         chat_id = chat["chat_id"]
#         try:
#             if content_type == 'photo':
#                 sent_message = bot.send_photo(chat_id=chat_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
#             else:
#                 sent_message = bot.send_message(chat_id=chat_id, text=text_content, reply_markup=reply_markup)
            
#             if "-pin" in message.text:
#                 try:
#                     sent_message.pin(disable_notification=True)
#                 except Exception as e:
#                     logger.warning(f"Failed to pin message in chat {chat_id}: {e}")
#                     continue
#             elif "-pinloud" in message.text:
#                 try:
#                     sent_message.pin(disable_notification=False)
#                 except Exception as e:
#                     logger.warning(f"Failed to pin message with notification in chat {chat_id}: {e}")
#                     continue
#             sent_chats += 1
#         except (TimedOut, NetworkError, RetryAfter, BadRequest, Unauthorized) as e:
#             logger.error(f"Error broadcasting to chat {chat_id}: {e}")
#             continue

#     # Broadcasting to users
#     for user in get_served_users():
#         user_id = user["user_id"]
#         try:
#             if content_type == 'photo':
#                 bot.send_photo(chat_id=user_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
#             else:
#                 bot.send_message(chat_id=user_id, text=text_content, reply_markup=reply_markup)
#             sent_users += 1
#         except (TimedOut, NetworkError, RetryAfter, BadRequest, Unauthorized) as e:
#             logger.error(f"Error broadcasting to user {user_id}: {e}")
#             continue

#     return sent_chats, sent_users
