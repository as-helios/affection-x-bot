import datetime
import json
import logging
import os
import re
import time
from json import JSONDecodeError

import tweepy
from dotenv import load_dotenv
from telethon.tl.functions.channels import GetMessagesRequest

load_dotenv()


def get_name_from_user(user):
    if user.username:
        name = "@{}".format(user.username)
    else:
        name = []
        if user.first_name:
            name.append(user.first_name)
        if user.last_name:
            name.append(user.last_name)
        name = ' '.join(name)
    return name if name else 'ser'


def validate_x_url(url):
    _url = url.split("//")
    if not _url[1].startswith("x.com/") and not _url[1].startswith("twitter.com/"):
        return False
    match = re.search(r"\.com/([a-zA-Z0-9_]+)/status/(.*)", url)
    return match.group(1), match.group(2)


def load_x_v1_api():
    x_api_v1 = tweepy.OAuth1UserHandler(
        os.getenv('X_CONSUMER_KEY'),
        os.getenv('X_CONSUMER_SECRET'),
        os.getenv('X_ACCESS_TOKEN'),
        os.getenv('X_ACCESS_SECRET')
    )
    return tweepy.API(x_api_v1)


def load_x_v2_api():
    try:
        access_token = json.load(open("{}/creds.json".format(os.getenv('DATA_FOLDER')), "r"))
    except (JSONDecodeError, FileNotFoundError):
        raise Exception("Invalid X credentials")
    else:
        fields = ["token_type", "access_token", "scope", "refresh_token", "expires_in", "expires_at"]
        if [f for f in fields if f in access_token] != fields:
            raise Exception("Invalid X credentials")
        else:
            refresh_x_oauth2_token()
    client = tweepy.Client(access_token=os.getenv('X_ACCESS_TOKEN'), access_token_secret=os.getenv('X_ACCESS_SECRET'), consumer_key=os.getenv('X_CONSUMER_KEY'), consumer_secret=os.getenv('X_CONSUMER_SECRET'))
    return client


def load_x_v2_api_oauth2_handler():
    return tweepy.OAuth2UserHandler(
        client_id=os.getenv('X_CLIENT_ID'),
        client_secret=os.getenv('X_CLIENT_SECRET'),
        redirect_uri="https://localhost/",
        scope=["tweet.read", "tweet.write", "users.read", "offline.access"]
    )


async def create_tweet(content, media_ids=None):
    client = load_x_v2_api()
    post = client.create_tweet(text=content, media_ids=media_ids if media_ids else None)
    if post.data:
        open("{}/created.txt".format(os.getenv('DATA_FOLDER')), "a+").write("{}\n".format(post.data['id']))
    return post.data


async def delete_tweet(post_id):
    deleted_ids_file = "{}/deleted.txt".format(os.getenv('DATA_FOLDER'))
    try:
        with open(deleted_ids_file, 'r') as f:
            for line in f.readlines():
                if post_id == line.strip():
                    return False
    except FileNotFoundError:
        open(deleted_ids_file, "w").write('')
    client = load_x_v2_api()
    result = client.delete_tweet(post_id)
    if result.data['deleted'] is True:
        open(deleted_ids_file, "a").write("{}\n".format(post_id))
    return result


async def find_text_and_download_media(bot, message):
    os.makedirs(media_folder := "{}/media".format(os.getenv('DATA_FOLDER')), exist_ok=True)
    text = message.message
    media_path, media_size = None, None
    media_channel_id = message.peer_id.channel_id
    # create a download progress file
    os.makedirs(progress_folder := "{}/progress".format(os.getenv('DATA_FOLDER')), exist_ok=True)
    media_progress_file = "{}/{}-{}.json".format(progress_folder, media_channel_id, message.id)
    progress_data = {"last_update": time.time(), "percent": 0, "file_path": media_path, "cancelled": False, "id": None}
    open(media_progress_file, "w").write(json.dumps(progress_data))

    media = []
    # get any other messages
    try:
        result = await bot(GetMessagesRequest(id=list(range(message.id, message.id + int(os.getenv('X_MAX_MEDIA')))), channel=message.chat_id))
        for m in result.messages:
            if m.date != message.date:
                break
            media.append(m.media)
    except Exception as e:
        logging.error(e)
    else:
        if len(media) == 0:
            return text, media

    # setup the message to notify user media is downloading
    progress_message = await message.reply("Downloading from TG... 0%")
    progress_data['id'] = progress_message.id
    open(media_progress_file, "w").write(json.dumps(progress_data))

    # download all media
    media_paths = []
    for m in media:
        # everything else
        if hasattr(m, 'document'):
            try:
                # check video length
                if m.document.attributes[0].duration > 140:
                    raise Exception("Video is too long")
            except (AttributeError, IndexError):
                pass
            mime_type = m.document.mime_type.split('/')
            media_id = m.document.id
            media_path = "{}/{}.{}".format(media_folder, media_id, mime_type[1])
            media_size = m.document.size
        # compressed pictures
        elif hasattr(m, 'photo'):
            media_id = m.photo.id
            media_path = "{}/{}.{}".format(media_folder, media_id, 'jpg')
            if hasattr(m.photo, 'size'):
                media_size = m.photo.size
            else:
                media_size = m.photo.sizes[-1].sizes[-1]
        # check filesize
        if media_size > 536870912:
            raise Exception("File is too big")
        if media_path:
            # get local media size, this deletes any incomplete downloads
            if os.path.exists(media_path):
                _media_size = os.path.getsize(media_path)
            else:
                _media_size = 0
            # check if sizes match
            if media_size > _media_size:
                # deleting existing file
                if os.path.exists(media_path):
                    os.remove(media_path)

                # callback to update the download progress
                async def progress_callback(current, total):
                    progress = json.loads(open(media_progress_file, "r").read())
                    percent = round(current / total, 2)
                    if progress['cancelled'] is True:
                        await bot.edit_message(progress_message, "Downloading from TG... cancelled!!")
                        raise Exception('Cancelled')
                    if float(progress['last_update']) + 3 < time.time():
                        try:
                            await bot.edit_message(progress_message, "Downloading from TG... {}%".format(round(percent * 100, 1)))
                        except Exception as e:
                            logging.error(e)
                        else:
                            progress['last_update'] = time.time()
                            progress['percent'] = percent
                            open(media_progress_file, "w").write(json.dumps(progress))

                # download a new copy of the media
                await bot.download_media(m, media_path, progress_callback=progress_callback)
                # show it's completed
                await bot.edit_message(progress_message, "Downloading from TG... 100%")
                open(media_progress_file, "w").write(json.dumps(progress_data))

            # store path to file in array
            if os.path.exists(media_path):
                media_paths.append(media_path)

    return text, media_paths


async def upload_media(filenames):
    uploaded = []
    api = load_x_v1_api()
    for f in filenames:
        media = api.media_upload(f)
        if hasattr(media, 'image') or media.processing_info['state'] == 'succeeded':
            uploaded.append(media.media_id)
    return uploaded


def refresh_x_oauth2_token():
    try:
        access_token = json.load(open("{}/creds.json".format(os.getenv('DATA_FOLDER')), "r"))
    except JSONDecodeError:
        logging.debug("Failed to refresh access token")
        return False
    else:
        if access_token["expires_at"] - 900 < time.time():
            x_api_v2 = load_x_v2_api_oauth2_handler()
            access_token = x_api_v2.refresh_token("https://api.twitter.com/2/oauth2/token", refresh_token=access_token["refresh_token"])
            open("{}/creds.json".format(os.getenv('DATA_FOLDER')), "w").write(json.dumps(access_token, indent=4))
            logging.debug("Refreshed access token")
        else:
            logging.debug("Access token is still valid")
        return access_token


def delete_old_media():
    days = int(os.getenv('DELETE_OLD_MEDIA_IN_DAYS'))
    os.makedirs("{}/media".format(os.getenv('DATA_FOLDER')), exist_ok=True)
    for file in os.listdir("{}/media".format(os.getenv('DATA_FOLDER'))):
        file_path = os.path.join("{}/media".format(os.getenv('DATA_FOLDER'), file))
        if os.path.isfile(file_path):
            mod_time = os.path.getmtime(file_path)
            if (datetime.datetime.now() - datetime.datetime.fromtimestamp(mod_time)).days > days:
                os.remove(file_path)
                logging.debug("Deleted old media ({} days): {}".format(days, file))
