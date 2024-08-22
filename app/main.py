import sys

from apscheduler.schedulers.background import BackgroundScheduler
from telethon import TelegramClient
from telethon.sync import events
from telethon.tl.types import MessageReplyStoryHeader

from custom import *

log_file = '{}/app.log'.format(os.getenv('DATA_FOLDER'))
logging.basicConfig(
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
for package in (silence_packages := (
        'apscheduler',
        'telethon'
)):
    logging.getLogger(package).setLevel(logging.ERROR)
bot = TelegramClient('bot', int(os.getenv('TELEGRAM_APP_ID')), os.getenv('TELEGRAM_APP_HASH')).start(bot_token=os.getenv('TELEGRAM_BOT_TOKEN'))


@bot.on(events.NewMessage)
async def echo(event):
    user_input = event.text
    # skip if bot or no one sent a command
    if (event.sender and event.sender.bot) or not user_input:
        return
    user_input = user_input.split(" ")
    chat_id = event.chat_id
    channel_id = event.message.peer_id.channel_id

    # get reply from the message
    reply_to_message, reply_to_user = None, None
    reply_user_id, reply_user_name, reply_message_id, reply_top_id = None, None, None, None
    if event.is_reply:
        # skip if replied to a story
        if type(event.reply_to) is MessageReplyStoryHeader:
            return
        reply_to_message = await event.get_reply_message()
        reply_to_user = await reply_to_message.get_sender()
        reply_user_id = reply_to_user.id
        reply_user_name = get_name_from_user(reply_to_user)
        reply_message_id = reply_to_message.id
        if event.reply_to.reply_to_top_id:
            reply_message_id = event.reply_to.reply_to_top_id

    # get message
    message_id = event.message.id
    user = await event.message.get_sender()
    user_id = user.id
    user_name = get_name_from_user(user)

    # load perms file or create one
    permissions_file = "{}/permissions.json".format(os.getenv('DATA_FOLDER'))
    try:
        permissions = json.load(open(permissions_file))
    except (JSONDecodeError, FileNotFoundError):
        permissions = {"allowed": [], "disallowed": []}
        open(permissions_file, "w").write(json.dumps(permissions, indent=4))

    # check if user is allowed to tweet
    if user_id not in permissions["allowed"] \
            and str(user_id) != os.getenv('TELEGRAM_ADMIN_ID'):
        return

    # stage progress file to track the download process
    media_progress_file = "{}/progress/{}-{}.json".format(os.getenv('DATA_FOLDER'), channel_id, reply_message_id)

    # allow/disallow users from reposting to x
    if user_input[0] in ('/approve', '/disapprove',):
        # check if user is admin
        if str(user_id) != str(os.getenv('TELEGRAM_ADMIN_ID')):
            return
        # swap user id between lists
        match user_input[0]:
            case '/approve':
                # add user to allow list
                if reply_user_id not in permissions['allowed']:
                    permissions['allowed'].append(reply_user_id)
                # remove user from disallow list
                if reply_user_id in permissions['disallowed']:
                    permissions['disallowed'].remove(reply_user_id)
                await event.reply("Approved {}".format(reply_user_name))
            case '/disapprove':
                # add user to disallow list
                if reply_user_id not in permissions['disallowed']:
                    permissions['disallowed'].append(reply_user_id)
                # remove user from allow list
                if reply_user_id in permissions['allowed']:
                    permissions['allowed'].remove(reply_user_id)
                await event.reply("Disapproved {}".format(reply_user_name))
        # save users file
        open(permissions_file, "w").write(json.dumps(permissions, indent=4))

    # new tweet
    elif user_input[0] in ('/tweet',):
        # check if post is in progress
        if os.path.exists(media_progress_file):
            return await event.reply("This post is already in progress")

        # tweet replied to messages to x
        if reply_to_message:
            record_path = "{}/posts/forward_{}_{}.json".format(os.getenv('DATA_FOLDER'), chat_id, message_id)
            # check if already posted
            if os.path.exists(record_path):
                return await event.reply("Already posted")

        # tweet any text and replies with the url
        else:
            user_name = get_name_from_user(event.message.from_user)
            record_path = "{}/posts/tweet_{}_{}.json".format(os.getenv('DATA_FOLDER'), chat_id, message_id)

        # get text, switch to caption if media is attached
        try:
            text, media_path = await find_text_and_download_media(bot, reply_to_message or event.message)
        except Exception as e:
            if os.path.exists(media_progress_file):
                os.remove(media_progress_file)
            if "Cancelled" in str(e):
                logging.debug("Cancelled media download")
                return
            logging.error(e)
            if "File is too big" in str(e):
                return await event.reply("Error: file is too big for X")
            elif "Video is too long" in str(e):
                return await event.reply("Error: video is too long for X")
            else:
                return await event.reply("Error: unknown TG download error")
        else:
            logging.info("{} ({}) Downloaded file: {}".format(user_name, user_id, media_path))
            media_progress = json.loads(open(media_progress_file, "r").read())
            if media_progress['id']:
                await bot.edit_message(channel_id, media_progress['id'], "Uploading to X...")
            else:
                progress_message = await event.reply("Uploading to X...")
                media_progress['id'] = progress_message.id
                open(media_progress_file, "w").write(json.dumps(media_progress))

        text = text.replace(user_input[0], '').strip() if text else ''

        # check if tweet is empty
        if len(user_input) == 1 and not media_path and not text:
            return await event.reply("Not enough parameters")
        # upload media
        try:
            media_id = await upload_media(media_path) if media_path else None
        except Exception as e:
            logging.error(e)
            if "maxFileSizeExceeded" in str(e):
                return await event.reply("Error: max file size exceeded for X")
            else:
                return await event.reply("Error: unknown X upload error")
        else:
            if media_id:
                logging.info("{} ({}) Uploaded file: {}".format(user_name, user_id, media_path))
            elif media_id is False:
                logging.info("{} ({}) Failed to uploaded file: {}".format(user_name, user_id, media_path))
        finally:
            if os.path.exists(media_progress_file):
                media_progress = json.loads(open(media_progress_file, "r").read())
                await bot.delete_messages(channel_id, media_progress['id'])
                os.remove(media_progress_file)

        # send tweet
        try:
            post = await create_tweet(text, [media_id] if media_id else None)
        except Exception as e:
            logging.error(e)
            if "include either text or media" in str(e):
                return await event.reply("Error: no text or media")
            elif "duplicate content" in str(e):
                return await event.reply("Error: duplicate content")
            elif "Invalid X credentials" in str(e):
                return await event.reply("Error: not authenticated on X")
            else:
                return await event.reply("Error: unknown X posting error")
        # send the tweet url to telegram
        tweet_url = "https://x.com/{}/status/{}".format(os.getenv('X_USER'), post['id'])
        await event.reply(message := "Posted: {}".format(tweet_url))
        logging.info("{} ({}) {}".format(user_name, user_id, message))
        # form a record of this tweet
        record = {
            "chat_id": chat_id,
            "origin_message_id": reply_message_id,
            "origin_user_id": reply_user_id,
            "origin_user_name": reply_user_name,
            "user_id": user_id,
            "user_name": user_name,
            "text": text,
            "tweet_id": post['id'],
            "tweet_url": tweet_url
        }
        # save a record of this tweet
        os.makedirs("{}/posts".format(os.getenv('DATA_FOLDER')), exist_ok=True)
        open(record_path, "w").write(json.dumps(record, indent=4))

    # delete tweet
    elif user_input[0] in ('/untweet',):
        # nothing to delete
        if len(user_input) == 1 and not reply_to_message:
            return await event.reply("Not enough parameters")
        # get the tweet id from the message
        post_id = user_input[1] if len(user_input) > 1 else None
        # get text from the telegram replied to message
        text = " ".join(user_input[1:])
        if reply_to_message:
            text = reply_to_message.text
        if type(post_id) is not int:
            _, post_id = validate_x_url(text)
        # delete tweet
        try:
            result = await delete_tweet(post_id)
        except Exception as e:
            logging.error(e)
            if "Invalid X credentials" in str(e):
                return await event.reply("Error: not authenticated on X")
            else:
                return await event.reply("Error: unknown X error")
        else:
            # mark as deleted
            if not result:
                return await event.reply("Already deleted")
            # send the tweet url to telegram
            else:
                await event.reply(message := "Deleted: https://x.com/{}/status/{}".format(os.getenv('X_USER'), post_id))
                logging.info("{} ({}) {}".format(user_name, user_id, message))

    # cancel tweet if downloading is in progress
    elif user_input[0] in ('/cancel', '/stop',):
        # ignore if download progress file doesn't exist for this message
        if not os.path.exists(media_progress_file):
            return await event.reply("Nothing to cancel")
        try:
            # load download progress if there's one that matches
            media_progress = json.loads(open(media_progress_file, "r").read())
        except (JSONDecodeError, FileNotFoundError) as e:
            logging.error(e)
            return await event.reply("Error: failed to cancel")
        else:
            # set download progress file as cancelled
            media_progress['cancelled'] = True
            open(media_progress_file, "w").write(json.dumps(media_progress, indent=4))


if __name__ == '__main__':
    logging.info("-" * 50)
    logging.info("Affection TG X Bot")
    logging.info("-" * 50)
    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_x_oauth2_token, 'interval', minutes=1)
    scheduler.add_job(delete_old_media, 'interval', minutes=1)
    scheduler.start()
    bot.run_until_disconnected()
