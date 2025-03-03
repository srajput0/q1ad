# Aarush Telegram Quiz Bot

A Telegram bot that conducts quizzes in group and private chats. It keeps track of leaderboard scores and allows for broadcasting messages.

## Folder Structure

```
project
├── config
│   ├── chat_ids.json
│   └── leaderboard.json
├── functions
│   ├── bot_logging.py
│   ├── chat_data_handler.py
│   ├── leaderboard_handler.py
│   ├── quiz_handler.py
│   └── admin_handler.py
├── start
│   └── bot.py
└── README.md
```

## Setup

1. Create a virtual environment and activate it:
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

2. Install the required packages:
    ```bash
    pip install python-telegram-bot==13.7
    ```

3. Replace the `TOKEN` and `ADMIN_ID` in `bot.py` with your actual bot token and Telegram user ID.

4. Run the bot:
    ```bash
    python start/bot.py
    ```

## Usage

- `/start` - Welcome message and instructions
- `/sendgroup` - Start a quiz in a group chat
- `/prequiz` - Start a quiz in a private chat
- `/stopquiz` - Stop the running quiz
- `/setinterval <seconds>` - Set the interval between quizzes
- `/leaderboard` - Show the leaderboard
- `/broadcast <message>` - Send a broadcast message (admin only)
