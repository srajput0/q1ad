import logging
import asyncio
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data, get_served_chats, get_served_users
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID
IS_BROADCASTING = False

def broadcast_message(update: Update, context: CallbackContext):
    global IS_BROADCASTING

    if not update.message.reply_to_message and len(update.message.text.split()) < 2:
        update.message.reply_text("Please provide a message to broadcast or reply to a text/photo message.")
        return

    IS_BROADCASTING = True
    update.message.reply_text("Broadcasting started!")

    if update.message.reply_to_message:
        # Extract data from the replied message
        if update.message.reply_to_message.photo:
            content_type = 'photo'
            file_id = update.message.reply_to_message.photo[-1].file_id
            text_content = update.message.reply_to_message.caption
        else:
            content_type = 'text'
            text_content = update.message.reply_to_message.text
        
        reply_markup = update.message.reply_to_message.reply_markup if hasattr(update.message.reply_to_message, 'reply_markup') else None
        
        broadcast_to_all(context.bot, text_content, content_type, file_id, reply_markup, update.message)
    else:
        # Extract data from the command message
        command_args = update.message.text.split(None, 1)[1]
        broadcast_to_all(context.bot, command_args, 'text', None, None, update.message)

    IS_BROADCASTING = False

def broadcast_to_all(bot, text_content, content_type, file_id, reply_markup, message):
    # Broadcasting to chats
    sent_chats = 0
    chats = [int(chat["chat_id"]) for chat in get_served_chats()]
    for chat_id in chats:
        try:
            if content_type == 'photo':
                bot.send_photo(chat_id=chat_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
            else:
                sent_message = bot.send_message(chat_id=chat_id, text=text_content, reply_markup=reply_markup)
                if "-pin" in message.text:
                    try:
                        sent_message.pin(disable_notification=True)
                    except:
                        continue
                elif "-pinloud" in message.text:
                    try:
                        sent_message.pin(disable_notification=False)
                    except:
                        continue
            sent_chats += 1
        except (TimedOut, NetworkError, RetryAfter, BadRequest):
            continue
    message.reply_text(f"Broadcast to chats completed! Sent to {sent_chats} chats.")

    # Broadcasting to users
    sent_users = 0
    users = [int(user["user_id"]) for user in get_served_users()]
    for user_id in users:
        try:
            if content_type == 'photo':
                bot.send_photo(chat_id=user_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
            else:
                bot.send_message(chat_id=user_id, text=text_content, reply_markup=reply_markup)
            sent_users += 1
        except (TimedOut, NetworkError, RetryAfter, BadRequest):
            continue
    message.reply_text(f"Broadcast to users completed! Sent to {sent_users} users.")
