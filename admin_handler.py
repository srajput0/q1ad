import logging
import asyncio
from chat_data_handler import load_chat_data, get_served_chats, get_served_users
from pyrogram.errors import FloodWait

logger = logging.getLogger(__name__)

ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID
IS_BROADCASTING = False

async def broadcast_message_async(client, message):
    global IS_BROADCASTING

    if "-wfchat" in message.text or "-wfuser" in message.text:
        if not message.reply_to_message or not (message.reply_to_message.photo or message.reply_to_message.text):
            return await message.reply_text("Please reply to a text or image message for broadcasting.")

        # Extract data from the replied message
        if message.reply_to_message.photo:
            content_type = 'photo'
            file_id = message.reply_to_message.photo.file_id
        else:
            content_type = 'text'
            text_content = message.reply_to_message.text
            
        caption = message.reply_to_message.caption
        reply_markup = message.reply_to_message.reply_markup if hasattr(message.reply_to_message, 'reply_markup') else None

        IS_BROADCASTING = True
        await message.reply_text("Broadcasting started!")

        if "-wfchat" in message.text or "-wfuser" in message.text:
            # Broadcasting to chats
            sent_chats = 0
            chats = [int(chat["chat_id"]) for chat in await get_served_chats()]
            for i in chats:
                try:
                    if content_type == 'photo':
                        await client.send_photo(chat_id=i, photo=file_id, caption=caption, reply_markup=reply_markup)
                    else:
                        await client.send_message(chat_id=i, text=text_content, reply_markup=reply_markup)
                    sent_chats += 1
                    await asyncio.sleep(0.2)
                except FloodWait as fw:
                    await asyncio.sleep(fw.x)
                except:
                    continue
            await message.reply_text(f"Broadcast to chats completed! Sent to {sent_chats} chats.")

        if "-wfuser" in message.text:
            # Broadcasting to users
            sent_users = 0
            users = [int(user["user_id"]) for user in await get_served_users()]
            for i in users:
                try:
                    if content_type == 'photo':
                        await client.send_photo(chat_id=i, photo=file_id, caption=caption, reply_markup=reply_markup)
                    else:
                        await client.send_message(chat_id=i, text=text_content, reply_markup=reply_markup)
                    sent_users += 1
                    await asyncio.sleep(0.2)
                except FloodWait as fw:
                    await asyncio.sleep(fw.x)
                except:
                    continue
            await message.reply_text(f"Broadcast to users completed! Sent to {sent_users} users.")

        IS_BROADCASTING = False
        return

    
    if message.reply_to_message:
        x = message.reply_to_message.id
        y = message.chat.id
        reply_markup = message.reply_to_message.reply_markup if message.reply_to_message.reply_markup else None
        content = None
    else:
        if len(message.command) < 2:
            return await message.reply_text("Please provide a message to broadcast.")
        query = message.text.split(None, 1)[1]
        if "-pin" in query:
            query = query.replace("-pin", "")
        if "-nobot" in query:
            query = query.replace("-nobot", "")
        if "-pinloud" in query:
            query = query.replace("-pinloud", "")
        if "-user" in query:
            query = query.replace("-user", "")
        if query == "":
            return await message.reply_text("Please provide a message to broadcast.")

    IS_BROADCASTING = True
    await message.reply_text("Broadcasting started!")

    if "-nobot" not in message.text:
        sent = 0
        pin = 0
        chats = []
        schats = await get_served_chats()
        for chat in schats:
            chats.append(int(chat["chat_id"]))
        for i in chats:
            try:
                m = (
                    await client.copy_message(chat_id=i, from_chat_id=y, message_id=x, reply_markup=reply_markup)
                    if message.reply_to_message
                    else await client.send_message(i, text=query)
                )
                if "-pin" in message.text:
                    try:
                        await m.pin(disable_notification=True)
                        pin += 1
                    except:
                        continue
                elif "-pinloud" in message.text:
                    try:
                        await m.pin(disable_notification=False)
                        pin += 1
                    except:
                        continue
                sent += 1
                await asyncio.sleep(0.2)
            except FloodWait as fw:
                flood_time = int(fw.value)
                if flood_time > 200:
                    continue
                await asyncio.sleep(flood_time)
            except:
                continue
        try:
            await message.reply_text(f"Broadcast to chats completed! Sent to {sent} chats and pinned {pin} messages.")
        except:
            pass

    if "-user" in message.text:
        susr = 0
        served_users = []
        susers = await get_served_users()
        for user in susers:
            served_users.append(int(user["user_id"]))
        for i in served_users:
            try:
                m = (
                    await client.copy_message(chat_id=i, from_chat_id=y, message_id=x, reply_markup=reply_markup)
                    if message.reply_to_message
                    else await client.send_message(i, text=query)
                )
                susr += 1
                await asyncio.sleep(0.2)
            except FloodWait as fw:
                flood_time = int(fw.value)
                if flood_time > 200:
                    continue
                await asyncio.sleep(flood_time)
            except:
                pass
        try:
            await message.reply_text(f"Broadcast to users completed! Sent to {susr} users.")
        except:
            pass

    IS_BROADCASTING = False

def broadcast_message(update: Update, context: CallbackContext):
    asyncio.run(broadcast_message_async(context.bot, update.message))
