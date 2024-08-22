# affection-x-bot

Creates posts on X from messages on Telegram. Supports images and video but limited to 512mb and 140 seconds. 

## Getting Started

- Clone the repo
- Open the `app` folder
- Rename `sample.env` to `.env`
- Set your Telegram Admin ID. This is an integer value representing your main account.
- Enter your Telegram bot token from [@botfather](https://t.me/botfather)
- Enter your Telegram App ID and App Hash from [my.telegram.org](https://my.telegram.org)
- Enter your X username and access/consumer/client credentials from the [Developer Portal](https://developer.twitter.com/en/portal/dashboard)

### Bare Metal

- Type `pip install -r requirements.txt` to install dependencies
- Follow the instructions below to authenticate with X
- Run by typing `python main.py`

### Docker

- Run by typing `docker compose up -d` in the repo's root folder
- Enter the docker container by typing `docker exec -it affection-x-bot bash`
- Follow the instructions below to authenticate with X
- Press CTRL+D to exit the container

### X
You will need both v1 and v2 API credentials from the [Developer Portal](https://developer.twitter.com/en/portal/dashboard)

- Run `python login-to-x.py` to authorize your X account with the bot
- Copy the the URL and authorize your X account using a browser
- It will redirect you to a localhost URL. Copy/paste that URL back into the auth script and press enter. It will save your X credentials to the data folder

### Telegram
This bot only works for supergroups (public). You will need a bot token from [@botfather](https://t.me/botfather) + a custom app created using [my.telegram.org](https://my.telegram.org)

- Add the bot to your supergroup as admin