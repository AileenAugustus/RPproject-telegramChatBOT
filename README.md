# Roleplay Project

Welcome to the Roleplay Project repository! This bot allows users to interact with various personalities, set time zones, manage chat histories, and more. It also features a greeting scheduler to keep conversations lively.


## Features

- **Dynamic Personalities**: Choose different personalities to enhance the chat experience.
- **Memory Management**: The bot can remember previous interactions and use this information to provide relevant responses.
- **Timezone Settings**: Set your timezone to receive timely greetings and messages.
- **Retry Mechanism**: Retry the last response if needed.
- **Proactive Greetings**: The bot generates and sends greeting messages based on user activity and timezone.
- **Scheduled Reminders**: Users can set reminders and times, and the bot will remind them at the specified times.

## Commands

### Start the bot
```
/start
```
Start the bot.

### Set timezone
```
/time <timezone>
```
Set your timezone (e.g., `Asia/Shanghai`). This needs to be sent each time the bot is restarted. The proactive greeting function and the reminder function require the timezone to be set. Without it, the former will have time discrepancies, and the latter will not start.

### Use a specific personality
```
/use <personality>
```
Switch to a specified personality for a more engaging conversation experience.

### Retry the last response
```
/retry
```
Retry the last response from the bot.

### Clear chat history
```
/clear
```
Clear the current chat history.

### List and manage memories (Use this function carefully as it consumes a lot of API resources)
```
/list
```
List all stored memories.

```
/list <number>
```
Delete a memory.

```
/list <number> <memory content>
```
Add or update/overwrite a memory.

### Reminders
```
/clock <time> <event>
```
Set a one-time reminder with the specified time and event.

```
/clockeveryday <time> <event>
```
Set a daily reminder with the specified time and event.

```
/clocklist
```
View the list of reminders.

```
/clockclear <number>
```
Delete a one-time reminder.

```
/clockclearevery <number>
```
Delete a daily reminder.

---

Hope these updates help you better manage and use the bot! If you have any further modification requests, please let me know.

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AileenAugustus/RPproject-AtelegramChatBOT.git
   cd RPproject-AtelegramChatBOT
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuration**
   Find the `config.py` file in the root directory and fill in the necessary details:
   ```python
   API_KEY = 'your_openai_api_key'
   TELEGRAM_BOT_TOKEN = 'your_telegram_bot_token'
   ALLOWED_USER_IDS = []  # Replace with allowed user IDs
   YOUR_SITE_URL = 'your_site_url'  # Optional
   YOUR_APP_NAME = 'your_app_name'  # Optional
   ```
   Find the `personalities.py` file in the root directory with the following content:
   ```python
   personalities = {
       "DefaultPersonality": {
           "api_url": "https://openrouter.ai/api/v1/chat/completions",
           "prompt": "You are chatgpt.",
           "temperature": 0.6,
           "model": "openai/gpt-4o"
       },
       "CustomPersonalityName": {
           "api_url": "https://openrouter.ai/api/v1/chat/completions",
           "prompt": "Custom personality prompt",
           "temperature": 1,
           "model": "openai/gpt-4o"
       },
   }
   ```

4. **Run the bot**
   ```bash
   python3 bot.py
   ```

## Contribution

Contributions are welcome! Please feel free to submit pull requests or open issues to discuss improvements or bugs.

## License

This project is licensed under the MIT License.

---

Thank you for using this bot! Enjoy the enhanced chat experience.
