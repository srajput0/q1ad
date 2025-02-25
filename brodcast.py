import logging
from chat_data_handler import load_chat_data

logger = logging.getLogger(__name__)

ADMIN_ID = 5050578106  # Replace with your actual Telegram user ID

def broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    message = ' '.join(context.args)
    if not message:
        update.message.reply_text("Usage: /broadcast <message>")
        return

    chat_data = load_chat_data()
    for chat_id in chat_data.keys():
        try:
            context.bot.send_message(chat_id=int(chat_id), text=message)
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")

    update.message.reply_text("Broadcast sent.")
