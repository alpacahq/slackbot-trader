from flask import Flask, request
import alpaca_trade_api as tradeapi
import requests
import asyncio
import json
import os


# Constants used throughout the script (names are self-explanatory)
WRONG_NUM_ARGS = "ERROR: Incorrect amount of args.  Action did not complete."
BAD_ARGS = "ERROR: Request error.  Action did not complete."
KEY_ID = ""  # Your API Key ID
SECRET_KEY = ""  # Your Secret Key
SLACK_TOKEN = ""  # Slack OAuth Access Token

config = {
    "key_id": os.environ.get("KEY_ID", KEY_ID),
    "secret_key": os.environ.get("SECRET_KEY", SECRET_KEY),
    "base_url": os.environ.get("BASE_URL", "https://paper-api.alpaca.markets"),
    "slack_token": os.environ.get("SLACK_TOKEN", SLACK_TOKEN),
}

api = tradeapi.REST(
    key_id=config.get('key_id'),
    secret_key=config.get('secret_key'),
    base_url=config.get('base_url'),
)

# Initialize the Flask object which will be used to handle HTTP requests
# from Slack
app = Flask(__name__)


def reply_private(request, text):
    requests.post(
        url=request.form.get("response_url"),
        data=json.dumps({"text": text}),
        headers={"Content-type": "application/json"},
    )


@app.route("/order", methods=["POST"])
def order_handler():
    '''Execute an order.  Must contain 5 arguments: type, symbol,
       quantity, side, time in force
    '''
    args = request.form.get("text").split(" ")
    if len(args) == 0:
        return WRONG_NUM_ARGS

    async def sub_order(api, request, args):
        order_type = args[0].lower()
        if order_type == "market":
            if len(args) < 5:
                reply_private(request, WRONG_NUM_ARGS)
                return
            try:
                side = args[1]
                qty = args[2]
                symbol = args[3].upper()
                tif = args[4].lower()
                order = api.submit_order(symbol,
                                         side=side,
                                         type=order_type,
                                         qty=qty,
                                         time_in_force=tif)
                price = api.get_barset(symbol, 'minute', 1)[symbol][0].c
                text = (f'Market order of | {side} {qty} {symbol} {tif} |, '
                        f'current equity price at {price}.  '
                        f'Order id = {order.id}.')
                requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_id"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        else:
            reply_private(request, BAD_ARGS)
    asyncio.run(sub_order(api, request, args))
    return ""


# Run on local port 3000
if __name__ == "__main__":
    app.run(port=3000)
