import logging
import asyncio
from telegram import Update
from telegram.ext import CallbackContext
from chat_data_handler import load_chat_data, get_served_chats, get_served_users
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID
IS_BROADCASTING = False

async def broadcast_message_async(client, message):
    global IS_BROADCASTING

    if not message.reply_to_message and len(message.text.split()) < 2:
        return await message.reply_text("Please provide a message to broadcast or reply to a text/photo message.")

    IS_BROADCASTING = True
    await message.reply_text("Broadcasting started!")

    if message.reply_to_message:
        # Extract data from the replied message
        if message.reply_to_message.photo:
            content_type = 'photo'
            file_id = message.reply_to_message.photo[-1].file_id
            text_content = message.reply_to_message.caption
        else:
            content_type = 'text'
            text_content = message.reply_to_message.text
        
        reply_markup = message.reply_to_message.reply_markup if hasattr(message.reply_to_message, 'reply_markup') else None
        
        await broadcast_to_all(client, text_content, content_type, file_id, reply_markup, message)
    else:
        # Extract data from the command message
        command_args = message.text.split(None, 1)[1]
        await broadcast_to_all(client, command_args, 'text', None, None, message)

    IS_BROADCASTING = False

async def broadcast_to_all(client, text_content, content_type, file_id, reply_markup, message):
    # Broadcasting to chats
    sent_chats = 0
    chats = [int(chat["chat_id"]) for chat in get_served_chats()]
    for chat_id in chats:
        try:
            if content_type == 'photo':
                await client.send_photo(chat_id=chat_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
            else:
                sent_message = await client.send_message(chat_id=chat_id, text=text_content, reply_markup=reply_markup)
                if "-pin" in message.text:
                    try:
                        await sent_message.pin(disable_notification=True)
                    except:
                        continue
                elif "-pinloud" in message.text:
                    try:
                        await sent_message.pin(disable_notification=False)
                    except:
                        continue
            sent_chats += 1
            await asyncio.sleep(0.2)
        except FloodWait as fw:
            await asyncio.sleep(fw.x)
        except:
            continue
    await message.reply_text(f"Broadcast to chats completed! Sent to {sent_chats} chats.")

    # Broadcasting to users
    sent_users = 0
    users = [int(user["user_id"]) for user in get_served_users()]
    for user_id in users:
        try:
            if content_type == 'photo':
                await client.send_photo(chat_id=user_id, photo=file_id, caption=text_content, reply_markup=reply_markup)
            else:
                await client.send_message(chat_id=user_id, text=text_content, reply_markup=reply_markup)
            sent_users += 1
            await asyncio.sleep(0.2)
        except FloodWait as fw:
            await asyncio.sleep(fw.x)
        except:
            continue
    await message.reply_text(f"Broadcast to users completed! Sent to {sent_users} users.")

def broadcast_message(update: Update, context: CallbackContext):
    asyncio.run(broadcast_message_async(context.bot, update.message))
