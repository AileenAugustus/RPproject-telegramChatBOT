import logging
import aiohttp
import json
import asyncio
import random
from datetime import datetime, timedelta
import pytz
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, JobQueue
from config import API_KEY, TELEGRAM_BOT_TOKEN, YOUR_SITE_URL, YOUR_APP_NAME, ALLOWED_USER_IDS
from personalities import personalities

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Store current personality choice for each user
user_personalities = {}
# Store chat history for each user
chat_histories = {}
# Store last activity time for each user
last_activity = {}
# Store timezone for each user
user_timezones = {}
# Store memories for each user
user_memories = {}
# Store scheduler task status for each user
scheduler_tasks = {}
# Store message IDs for each user
message_ids = {}
# Store reminders for each user
user_reminders = {}
# Store daily reminders for each user
user_daily_reminders = {}

# Get the latest personality choice
def get_latest_personality(chat_id):
    return user_personalities.get(chat_id, "DefaultPersonality")

# Decorator function to check user ID
def allowed_users_only(func):
    async def wrapper(update: Update, context: CallbackContext):
        user_id = update.message.from_user.id
        if user_id in ALLOWED_USER_IDS:
            return await func(update, context)
        else:
            await update.message.reply_text("You do not have permission to use this bot.")
    return wrapper

# /start command handler
@allowed_users_only
async def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    await update.message.reply_text(
        'Welcome to the chatbot!\n'
        'You can use the following commands to choose a personality:\n'
        '/use DefaultPersonality - Switch to ChatGPT4o\n'
        '/use <personality name> - Switch to a specified personality\n'
        '/clear - Clear the current chat history\n'
        'Send a message to start chatting!\n'
        'You can also set your timezone, for example /time Asia/Shanghai\n'
        'Use /retry to resend the last message\n'
    )
    last_activity[chat_id] = datetime.now()

    # Check if there is an ongoing scheduler task, if so, cancel it
    if chat_id in scheduler_tasks:
        scheduler_tasks[chat_id].cancel()
        logger.info(f"Cancelled existing greeting scheduler task for chat_id: {chat_id}")

    # Start a new scheduler task
    logger.info(f"Starting new greeting scheduler task for chat_id: {chat_id}")
    task = context.application.create_task(greeting_scheduler(chat_id, context))
    scheduler_tasks[chat_id] = task
    logger.info(f"Created greeting_scheduler task for chat_id: {chat_id}")

# /use command handler
@allowed_users_only
async def use_personality(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Usage: /use <personality name>')
        return

    personality_choice = args[0]
    if personality_choice in personalities:
        user_personalities[chat_id] = personality_choice
        await update.message.reply_text(f'Switched to {personality_choice} personality.')
        logger.info(f"User {chat_id} switched to personality {personality_choice}")
    else:
        await update.message.reply_text('Specified personality not found.')
        logger.warning(f"User {chat_id} attempted to switch to unknown personality {personality_choice}")

# /time command handler
@allowed_users_only
async def set_time(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Usage: /time <timezone name>')
        return

    timezone = args[0]
    try:
        # Attempt to set timezone in user_timezones dictionary
        pytz.timezone(timezone)
        user_timezones[chat_id] = timezone
        await update.message.reply_text(f'Timezone set to {timezone}')
        logger.info(f"User {chat_id} set timezone to {timezone}")
    except pytz.UnknownTimeZoneError:
        await update.message.reply_text('Invalid timezone name. Please use a valid timezone name, such as Asia/Shanghai')
        logger.warning(f"User {chat_id} attempted to set unknown timezone {timezone}")

# /clear command handler
@allowed_users_only
async def clear_history(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    chat_histories[chat_id] = []
    await update.message.reply_text('Cleared current chat history.')
    logger.info(f"Cleared chat history for chat_id: {chat_id}")

# /list command handler
@allowed_users_only
async def list_memories(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args

    if not args:
        memories = user_memories.get(chat_id, [])
        if not memories:
            await update.message.reply_text('No memories stored.')
        else:
            memories_text = "\n".join([f"{i + 1}. {memory}" for i, memory in enumerate(memories)])
            await update.message.reply_text(f"Memories:\n{memories_text}")
    else:
        try:
            index = int(args[0]) - 1
            new_memory = " ".join(args[1:])
            if new_memory:
                if chat_id not in user_memories:
                    user_memories[chat_id] = []
                if 0 <= index < len(user_memories[chat_id]):
                    user_memories[chat_id][index] = new_memory
                elif index == len(user_memories[chat_id]):
                    user_memories[chat_id].append(new_memory)
                else:
                    await update.message.reply_text('Invalid memory index.')
                    return
                await update.message.reply_text('Memory updated.')
            else:
                if chat_id in user_memories and 0 <= index < len(user_memories[chat_id]):
                    del user_memories[chat_id][index]
                    await update.message.reply_text('Memory deleted.')
                else:
                    await update.message.reply_text('Invalid memory index.')
        except (ValueError, IndexError):
            await update.message.reply_text('Usage: /list <memory index> <new memory text>')

# /retry command handler
@allowed_users_only
async def retry_last_response(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id

    try:
        # Ensure there is at least one bot response in the chat history
        if chat_id in chat_histories and len(chat_histories[chat_id]) > 1:
            # Find the index of the last bot response
            last_bot_response_index = None
            for i in range(len(chat_histories[chat_id]) - 1, -1, -1):
                if chat_histories[chat_id][i].startswith("Bot:"):
                    last_bot_response_index = i
                    break

            if last_bot_response_index is not None:
                # Get the user's original message
                last_user_message_index = last_bot_response_index - 1
                if last_user_message_index >= 0 and chat_histories[chat_id][last_user_message_index].startswith("User:"):
                    last_user_message = chat_histories[chat_id][last_user_message_index].split("User:", 1)[-1].strip()

                    # Remove the last bot response from the chat history
                    last_bot_response = chat_histories[chat_id].pop(last_bot_response_index)

                    logger.info(f"Removed last bot response from chat history for chat_id {chat_id}: {last_bot_response}")

                    # Delete the last bot message from Telegram
                    if chat_id in message_ids and message_ids[chat_id]:
                        last_message_id = message_ids[chat_id].pop()
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=last_message_id)
                            logger.info(f"Deleted message ID: {last_message_id} for chat_id {chat_id}")
                        except Exception as delete_err:
                            logger.error(f"Failed to delete message: {delete_err}")

                    # Check memory relevance and re-request API response
                    await process_message(chat_id, last_user_message, update.message, context)

                else:
                    await context.bot.send_message(chat_id=chat_id, text="No corresponding user message found.")
            else:
                await context.bot.send_message(chat_id=chat_id, text="No bot response found in chat history to retry.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="No chat history found to retry.")

    except Exception as main_err:
        logger.error(f"Main error occurred while processing message: {main_err}")
        await context.bot.send_message(chat_id=chat_id, text="A main error occurred while processing the message. Please try again later.")

# /clock command handler
@allowed_users_only
async def set_clock(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Usage: /clock <time(HH:MM)> <event>')
        return

    time_str = args[0]
    event = " ".join(args[1:])

    try:
        reminder_time = datetime.strptime(time_str, "%H:%M").time()
        if chat_id not in user_reminders:
            user_reminders[chat_id] = []
        user_reminders[chat_id].append((reminder_time, event))
        await update.message.reply_text(f'Reminder set at {time_str} to remind: {event}')
        logger.info(f"User {chat_id} set a reminder at {time_str} for: {event}")
    except ValueError:
        await update.message.reply_text('Invalid time format. Please use HH:MM format.')
        logger.warning(f"User {chat_id} attempted to set invalid time {time_str}")

# /clocklist command handler
@allowed_users_only
async def list_clocks(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    reminders = user_reminders.get(chat_id, [])
    if not reminders:
        await update.message.reply_text('No reminders set.')
    else:
        reminders_text = "\n".join([f"{i + 1}. {time.strftime('%H:%M')} - {event}" for i, (time, event) in enumerate(reminders)])
        await update.message.reply_text(f"Reminder list:\n{reminders_text}")

    daily_reminders = user_daily_reminders.get(chat_id, [])
    if daily_reminders:
        daily_reminders_text = "\n".join([f"{i + 1}. {time.strftime('%H:%M')} - {event}" for i, (time, event) in enumerate(daily_reminders)])
        await update.message.reply_text(f"Daily reminder list:\n{daily_reminders_text}")

# /clockeveryday command handler
@allowed_users_only
async def set_daily_clock(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('Usage: /clockeveryday <time(HH:MM)> <event>')
        return

    time_str = args[0]
    event = " ".join(args[1:])

    try:
        reminder_time = datetime.strptime(time_str, "%H:%M").time()
        if chat_id not in user_daily_reminders:
            user_daily_reminders[chat_id] = []
        user_daily_reminders[chat_id].append((reminder_time, event))
        await update.message.reply_text(f'Daily reminder set at {time_str} to remind: {event}')
        logger.info(f"User {chat_id} set a daily reminder at {time_str} for: {event}")
    except ValueError:
        await update.message.reply_text('Invalid time format. Please use HH:MM format.')
        logger.warning(f"User {chat_id} attempted to set invalid time {time_str}")

# /clockclear command handler
@allowed_users_only
async def clear_clock(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Usage: /clockclear <reminder index>')
        return

    try:
        index = int(args[0]) - 1
        if chat_id in user_reminders and 0 <= index < len(user_reminders[chat_id]):
            del user_reminders[chat_id][index]
            await update.message.reply_text('Reminder deleted.')
        else:
            await update.message.reply_text('Invalid reminder index or the index does not correspond to a one-time reminder.')
    except (ValueError, IndexError):
        await update.message.reply_text('Invalid reminder index.')

# /clockclearevery command handler
@allowed_users_only
async def clear_daily_clock(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    args = context.args
    if len(args) != 1:
        await update.message.reply_text('Usage: /clockclearevery <reminder index>')
        return

    try:
        index = int(args[0]) - 1
        if chat_id in user_daily_reminders and 0 <= index < len(user_daily_reminders[chat_id]):
            del user_daily_reminders[chat_id][index]
            await update.message.reply_text('Daily reminder deleted.')
        else:
            await update.message.reply_text('Invalid reminder index.')
    except (ValueError, IndexError):
        await update.message.reply_text('Invalid reminder index.')

# Message handler
@allowed_users_only
async def handle_message(update: Update, context: CallbackContext) -> None:
    chat_id = update.message.chat_id
    message = update.message.text

    logger.info(f"Received message from {chat_id}: {message}")

    # Initialize chat history (if not already present)
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    # Add new message to chat history
    chat_histories[chat_id].append(f"User: {message}")

    # Retain only the last 30 messages
    if len(chat_histories[chat_id]) > 30:
        chat_histories[chat_id].pop(0)

    # Update last activity time
    last_activity[chat_id] = datetime.now()

    # Cancel current scheduler task
    if chat_id in scheduler_tasks:
        scheduler_tasks[chat_id].cancel()
        logger.info(f"Cancelled existing greeting scheduler task for chat_id: {chat_id}")

    # Start a new scheduler task
    logger.info(f"Starting new greeting scheduler task for chat_id: {chat_id}")
    task = context.application.create_task(greeting_scheduler(chat_id, context))
    scheduler_tasks[chat_id] = task
    logger.info(f"Created greeting_scheduler task for chat_id: {chat_id}")

    await process_message(chat_id, message, update.message, context)

# Function to process message, including memory checks
async def process_message(chat_id, message, telegram_message, context):
    # Get current personality choice
    current_personality = get_latest_personality(chat_id)

    # If current personality is undefined, use default personality
    if current_personality not in personalities:
        current_personality = "DefaultPersonality"

    try:
        personality = personalities[current_personality]
    except KeyError:
        await telegram_message.reply_text(f"Personality not found: {current_personality}")
        logger.error(f"Personality not found {current_personality} for chat_id: {chat_id}")
        return

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": YOUR_SITE_URL,  # Optional
        "X-Title": YOUR_APP_NAME  # Optional
    }

    # Prepare memory check payload (if there are memories)
    memories = user_memories.get(chat_id, [])
    if memories:
        memory_check_payload = {
            "model": personality['model'],
            "messages": [{"role": "user", "content": msg} for msg in chat_histories[chat_id]] + [{"role": "user", "content": f"Memory: {memory}"} for memory in memories] + [{"role": "user", "content": "Please determine the relevance between the user's message and the memories. If relevant, reply '1', if not, reply '2'."}],
            "temperature": personality['temperature']
        }

        logger.debug(f"Sending memory check payload to API for chat_id {chat_id}: {json.dumps(memory_check_payload, ensure_ascii=False)}")

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(personality['api_url'], headers=headers, json=memory_check_payload) as memory_check_response:
                    memory_check_response.raise_for_status()
                    memory_check_result = await memory_check_response.json()
                    logger.debug(f"API response for memory check for chat_id {chat_id}: {memory_check_result}")

                    memory_check_result = memory_check_result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            except aiohttp.ClientResponseError as http_err:
                logger.error(f"HTTP error occurred: {http_err}")
                memory_check_result = "2"
            except aiohttp.ClientError as req_err:
                logger.error(f"Request error occurred: {req_err}")
                memory_check_result = "2"
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decode error: {json_err}")
                memory_check_result = "2"
            except Exception as err:
                logger.error(f"Error occurred: {err}")
                memory_check_result = "2"

        # If memory check result contains "1", include memories in the final payload
        if "1" in memory_check_result:
            final_payload = {
                "model": personality['model'],
                "messages": [{"role": "system", "content": personality['prompt']}] + [{"role": "user", "content": msg} for msg in chat_histories[chat_id]] + [{"role": "user", "content": "Each memory is separate, do not confuse them. Use only one relevant memory per response."}] + [{"role": "user", "content": f"Memory: {memory}"} for memory in memories],
                "temperature": personality['temperature']
            }
        else:
            final_payload = {
                "model": personality['model'],
                "messages": [{"role": "system", "content": personality['prompt']}] + [{"role": "user", "content": msg} for msg in chat_histories[chat_id]],
                "temperature": personality['temperature']
            }
    else:
        final_payload = {
            "model": personality['model'],
            "messages": [{"role": "system", "content": personality['prompt']}] + [{"role": "user", "content": msg} for msg in chat_histories[chat_id]],
            "temperature": personality['temperature']
        }

    logger.debug(f"Sending final payload to API for chat_id {chat_id}: {json.dumps(final_payload, ensure_ascii=False)}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(personality['api_url'], headers=headers, json=final_payload) as response:
                response.raise_for_status()  # Check if HTTP request was successful
                response_json = await response.json()
                logger.debug(f"API response for chat_id {chat_id}: {response_json}")

                reply = response_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
            reply = f"HTTP error occurred: {http_err}"
        except aiohttp.ClientError as req_err:
            logger.error(f"Request error occurred: {req_err}")
            reply = f"Request error occurred: {req_err}"
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON decode error: {json_err}")
            reply = f"JSON decode error: {json_err}"
        except Exception as err:
            logger.error(f"Error occurred: {err}")
            reply = f"Error occurred: {err}"

    # Remove unnecessary prefix (e.g., name)
    if "：" in reply:
        reply = reply.split("：", 1)[-1].strip()

    # Add API response to chat history
    chat_histories[chat_id].append(f"Bot: {reply}")

    logger.info(f"Replying to {chat_id}: {reply}")

    try:
        sent_message = await telegram_message.reply_text(reply)
        # Record message ID
        if chat_id not in message_ids:
            message_ids[chat_id] = []
        message_ids[chat_id].append(sent_message.message_id)
    except Exception as err:
        logger.error(f"Failed to send message: {err}")

# Reminder scheduler
async def reminder_scheduler(context: CallbackContext):
    while True:
        await asyncio.sleep(60)  # Check reminders every 60 seconds
        now = datetime.now(pytz.utc)

        for chat_id, reminders in list(user_reminders.items()):
            timezone = user_timezones.get(chat_id, 'UTC')
            current_time = now.astimezone(pytz.timezone(timezone)).time()

            reminders_to_remove = []
            for reminder_time, reminder_text in reminders:
                if reminder_time <= current_time < (datetime.combine(datetime.today(), reminder_time) + timedelta(minutes=1)).time():
                    await send_reminder(chat_id, reminder_text, context)
                    reminders_to_remove.append((reminder_time, reminder_text))

            for reminder in reminders_to_remove:
                user_reminders[chat_id].remove(reminder)

        for chat_id, reminders in list(user_daily_reminders.items()):
            timezone = user_timezones.get(chat_id, 'UTC')
            current_time = now.astimezone(pytz.timezone(timezone)).time()

            for reminder_time, reminder_text in reminders:
                if reminder_time <= current_time < (datetime.combine(datetime.today(), reminder_time) + timedelta(minutes=1)).time():
                    await send_reminder(chat_id, reminder_text, context)

# Function to send reminders
async def send_reminder(chat_id, reminder_text, context: CallbackContext):
    logger.info(f"Reminder time, sending reminder to chat_id {chat_id}: {reminder_text}")

    # Get current personality choice
    current_personality = get_latest_personality(chat_id)
    if current_personality not in personalities:
        current_personality = "DefaultPersonality"
    try:
        personality = personalities[current_personality]
    except KeyError:
        await context.bot.send_message(chat_id=chat_id, text=f"Personality not found: {current_personality}")
        return

    # Convert all personality parameters to string
    personality_details = "\n".join([f"{key}: {value}" for key, value in personality.items()])

    reminder_message = f"Please remind me to do the following: {reminder_text} Follow this prompt: {personality['prompt']} Send me a reply."

    messages = [{"role": "system", "content": personality['prompt']}, {"role": "user", "content": reminder_message}]
    payload = {
        "model": personality['model'],
        "messages": messages,
        "temperature": personality['temperature']
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": YOUR_SITE_URL,  # Optional
        "X-Title": YOUR_APP_NAME  # Optional
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(personality['api_url'], headers=headers, json=payload) as response:
                response.raise_for_status()
                response_json = await response.json()
                reply = response_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                if "：" in reply:
                    reply = reply.split("：", 1)[-1].strip()
                sent_message = await context.bot.send_message(chat_id=chat_id, text=reply)
                # Add reminder content and reply content to chat history
                if chat_id not in chat_histories:
                    chat_histories[chat_id] = []
                chat_histories[chat_id].append(f"Reminder: {reminder_text}")
                chat_histories[chat_id].append(f"Bot: {reply}")

                # Record message ID
                if chat_id not in message_ids:
                    message_ids[chat_id] = []
                message_ids[chat_id].append(sent_message.message_id)

                last_activity[chat_id] = datetime.now()  # Update last activity time
                logger.info(f"Sent reminder to chat_id {chat_id}: {reply}")
        except aiohttp.ClientResponseError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
        except aiohttp.ClientError as req_err:
            logger.error(f"Request error occurred: {req_err}")
        except json.JSONDecodeError as json_err:
            logger.error(f"JSON decode error: {json_err}")
        except Exception as err:
            logger.error(f"Error occurred: {err}, message content: {reminder_text}, chat_id: {chat_id}")

# Greeting scheduler
async def greeting_scheduler(chat_id, context: CallbackContext):
    logger.info(f"Starting greeting_scheduler for chat_id: {chat_id}")
    while True:
        await asyncio.sleep(600)  # Check for new messages every 3600 seconds
        logger.info(f"Checking last activity time for chat_id: {chat_id}")
        if chat_id in last_activity:
            delta = datetime.now() - last_activity[chat_id]
            logger.info(f"Time since last activity: {delta.total_seconds()} seconds")
            if delta.total_seconds() >= 3600:  # Last activity time is over 1 hour
                logger.info(f"chat_id {chat_id} has been inactive for over 1 hour.")
                wait_time = random.randint(3600, 14400)  # Random wait between 1 to 4 hours
                logger.info(f"Waiting {wait_time} seconds before sending greeting")
                await asyncio.sleep(wait_time)

                # Get user's timezone
                timezone = user_timezones.get(chat_id, 'UTC')
                local_time = datetime.now(pytz.timezone(timezone)).strftime("%Y-%m-%d %H:%M:%S")
                greeting_message = f"It is now {local_time}, please generate and reply with a greeting or share your daily life. Respond according to the given personality and role settings, here are some examples."

                # Generate greeting
                examples = [
                    "0:00-3:59: 'Ask if I'm still awake and describe how you miss me.'",
                    "4:00-5:59: 'Say good morning and mention you woke up early.'",
                    "6:00-8:59: 'Greet me in the morning.'",
                    "9:00-10:59: 'Greet me and ask about my plans for today.'",
                    "11:00-12:59: 'Ask if I've had lunch.'",
                    "13:00-16:59: 'Talk about your work and express how you miss me.'",
                    "17:00-19:59: 'Ask if I've had dinner.'",
                    "20:00-21:59: 'Describe your day or the beautiful evening and ask about my day.'",
                    "22:00-23:59: 'Say goodnight.'",
                    "Share daily life: 'Share your daily life or work.'"
                ]
                greeting_message += "\nRespond according to the rules of the examples, do not repeat the content of the examples, express it in your own way:\n" + "\n".join(examples)

                logger.info(f"Sending greeting message to chat_id {chat_id}: {greeting_message}")

                # Get current personality choice
                current_personality = get_latest_personality(chat_id)
                if current_personality not in personalities:
                    current_personality = "DefaultPersonality"
                try:
                    personality = personalities[current_personality]
                except KeyError:
                    await context.bot.send_message(chat_id=chat_id, text=f"Personality not found: {current_personality}")
                    continue

                messages = [{"role": "system", "content": personality['prompt']}, {"role": "user", "content": greeting_message}]
                payload = {
                    "model": personality['model'],
                    "messages": messages,
                    "temperature": personality['temperature']
                }
                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "HTTP-Referer": YOUR_SITE_URL,  # Optional
                    "X-Title": YOUR_APP_NAME  # Optional
                }

                logger.debug(f"Sending payload to API for chat_id {chat_id}: {json.dumps(payload, ensure_ascii=False)}")

                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.post(personality['api_url'], headers=headers, json=payload) as response:
                            response.raise_for_status()
                            response_json = await response.json()
                            logger.debug(f"API response for chat_id {chat_id}: {response_json}")

                            reply = response_json.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
                            if "：" in reply:
                                reply = reply.split("：", 1)[-1].strip()
                            await context.bot.send_message(chat_id=chat_id, text=reply)

                            # Add proactive greeting to chat history
                            chat_histories[chat_id].append(f"Bot: {reply}")
                            last_activity[chat_id] = datetime.now()  # Update last activity time
                            logger.info(f"Sent greeting to chat_id {chat_id}: {reply}")
                    except aiohttp.ClientResponseError as http_err:
                        logger.error(f"HTTP error occurred: {http_err}")
                    except aiohttp.ClientError as req_err:
                        logger.error(f"Request error occurred: {req_err}")
                    except json.JSONDecodeError as json_err:
                        logger.error(f"JSON decode error: {json_err}")
                    except Exception as err:
                        logger.error(f"Error occurred: {err}")

# Main function
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Set commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("use", "Choose a personality"),
        BotCommand("clear", "Clear the current chat history"),
        BotCommand("time", "Set timezone"),
        BotCommand("list", "List and manage memories"),
        BotCommand("retry", "Retry the last message"),
        BotCommand("clock", "Set a reminder"),
        BotCommand("clocklist", "View the reminder list"),
        BotCommand("clockeveryday", "Set a daily reminder"),
        BotCommand("clockclear", "Cancel a reminder"),
        BotCommand("clockclearevery", "Cancel a daily reminder")
    ]
    application.bot.set_my_commands(commands)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("use", use_personality))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(CommandHandler("time", set_time))
    application.add_handler(CommandHandler("list", list_memories))
    application.add_handler(CommandHandler("retry", retry_last_response))
    application.add_handler(CommandHandler("clock", set_clock))
    application.add_handler(CommandHandler("clocklist", list_clocks))
    application.add_handler(CommandHandler("clockeveryday", set_daily_clock))
    application.add_handler(CommandHandler("clockclear", clear_clock))
    application.add_handler(CommandHandler("clockclearevery", clear_daily_clock))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start reminder scheduler task
    job_queue = application.job_queue
    job_queue.run_repeating(reminder_scheduler, interval=60, first=10)

    application.run_polling()

if __name__ == '__main__':
    main()
