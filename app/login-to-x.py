import json
import os
from dotenv import load_dotenv

from custom import load_x_v2_api_oauth2_handler


def gen_x_oauth2_token():
    x_api_v2 = load_x_v2_api_oauth2_handler()
    url = x_api_v2.get_authorization_url()
    print("Authorization URL: {}".format(url))
    response_url = input("Enter response URL: ")
    access_token = x_api_v2.fetch_token(response_url)
    open("{}/creds.json".format(os.getenv('DATA_FOLDER')), "w").write(json.dumps(access_token, indent=4))
    print("Generated new access token")


load_dotenv('./app/.env')
gen_x_oauth2_token()
