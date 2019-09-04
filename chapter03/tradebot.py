from flask import Flask, request
import alpaca_trade_api as tradeapi
import requests
import asyncio
import json
import os
import multiprocessing


# Constants used throughout the script (names are self-explanatory)
WRONG_NUM_ARGS = "ERROR: Incorrect amount of args.  Action did not complete."
BAD_ARGS = "ERROR: Request error.  Action did not complete."
KEY_ID = ""  # Your API Key ID
SECRET_KEY = ""  # Your Secret Key
SLACK_TOKEN = ""  # Slack OAuth Access Token
CHANNEL = ""

config = {
    "key_id": os.environ.get("KEY_ID", KEY_ID),
    "secret_key": os.environ.get("SECRET_KEY", SECRET_KEY),
    "base_url": os.environ.get("BASE_URL", "https://paper-api.alpaca.markets"),
    "slack_token": os.environ.get("SLACK_TOKEN", SLACK_TOKEN),
    "channel": os.environ.get("CHANNEL", CHANNEL)
}

# Set up environment
conn = tradeapi.StreamConn(
    key_id=config.get('key_id'),
    secret_key=config.get('secret_key'),
    base_url=config.get('base_url'),
)
api = tradeapi.REST(
    key_id=config.get('key_id'),
    secret_key=config.get('secret_key'),
    base_url=config.get('base_url'),
)

# Initialize the Flask object which will be used to handle HTTP requests
# from Slack
app = Flask(__name__)

 
# Initialize the dictionary of streams that we are listening to; None
# denotes not listening
streams = {
    "trade_updates": None,
}


def reply_private(request, text):
    requests.post(
        url=request.form.get("response_url"),
        data=json.dumps({"text": text}),
        headers={"Content-type": "application/json"},
    )

# Streaming handlers

# Subscribe to streaming channel(s).  Must contain one or more arguments
# representing streams you want to connect to.


@app.route("/subscribe_streaming", methods=["POST"])
def stream_data_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 1 and args[0].strip() == "":
        return BAD_ARGS
    try:
        connected = 0
        for stream in args:
            # If the specified stream exists in the dictionary and it hasn't
            # been initialized, subscribe and listen to it.
            if streams[stream] is None:
                streams[stream] = multiprocessing.Process(
                    target=runThread, args=(stream,))
                streams[stream].start()
                connected += 1
        if len(args) == connected:
            text = f"Subscription{('','s')[connected > 1]} to {(' ').join(args)} sent."
            response = requests.post(
                url="https://slack.com/api/chat.postMessage",
                data={
                    "token": config["slack_token"],
                    "channel": request.form.get("channel_name"),
                    "text": text})
            return ""
        else:
            return f"{len(args) - connected} subscription(s) failed."
    except Exception as e:
        return f'ERROR: {str(e)}'

# Unsubsribe to streaming channel(s).  Must contain one or more arguments
# representing streams you want to disconnect to.


@app.route("/unsubscribe_streaming", methods=["POST"])
def unsubscribe_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 1 and args[0].strip() == "":
        return BAD_ARGS
    try:
        disconnected = 0
        for stream in args:
            # If the specified stream exists in the dictionary and it has been
            # initialized, stop listening.
            if streams[stream] is not None:
                streams[stream].terminate()
                streams[stream] = None
                disconnected += 1
        if len(args) == disconnected:
            text = f"Unsubscription{('', 's')[disconnected > 1]} to {(' ').join(args)} sent."
            response = requests.post(
                url="https://slack.com/api/chat.postMessage",
                data={
                    "token": config["slack_token"],
                    "channel": request.form.get("channel_name"),
                    "text": text})
            return ""
        else:
            return f"{len(args) - disconnected} unsubscription(s) failed."
    except Exception as e:
        return f'ERROR: {str(e)}'

# Stream listeners


@conn.on(r'trade_updates')
async def trade_updates_handler(conn, chan, data):
    if data.event == "new":
        return ""
    elif data.event == "fill" or data.event == "partial_fill":
        text = f'*Event*: {data.event}, {data.order["type"]} order of | {data.order["side"]} {data.order["qty"]} {data.order["symbol"]} {data.order["time_in_force"]} | {data.event} at {data.price}'
    else:
        text = f'*Event*: {data.event}, {data.order["type"]} order of | {data.order["side"]} {data.order["qty"]} {data.order["symbol"]} {data.order["time_in_force"]} {data.event}'
    response = requests.post(url="https://slack.com/api/chat.postMessage", data={
        "token": config["slack_token"],
        "channel": config["channel"],
        "text": text
    })
    return ""

# Helper function to listen to a stream


def runThread(stream):
    conn.run([stream])

# Order/Account handlers

# Execute an order.  Must contain 5, 6, or 7 arguments: type, symbol,
# quantity, side, time in force, limit price (optional), and stop price
# (optional).
@app.route("/order", methods=["POST"])
def order_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 0 :
        return WRONG_NUM_ARGS

    async def sub_order(api, request, args):
        if args[0].lower() == "market":
            if len(args) != 5:
                reply_private(request, WRONG_NUM_ARGS)
                return
            try:
                args[3] = args[3].upper()
                order = api.submit_order(
                    args[3],
                    args[2],
                    args[1],
                    args[0].lower(),
                    args[4])
                price = api.get_barset(args[3], 'minute', 1)[args[3]][0].c
                text = f'Market order of | {args[1]} {args[2]} {args[3]} {args[4]} |, current equity price at {price}.  Order id = {order.id}.'
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        elif args[0].lower() == "limit":
            if len(args) != 6:
                reply_private(request, WRONG_NUM_ARGS)
                return
            try:
                args[3] = args[3].upper()
                order = api.submit_order(
                    args[3],
                    args[2],
                    args[1],
                    args[0].lower(),
                    args[4],
                    limit_price=args[5])
                text = f'Limit order of | {args[1]} {args[2]} {args[3]} {args[4]} at limit price {args[5]} | submitted.  Order id = {order.id}.'
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        elif args[0].lower() == "stop":
            if len(args) != 6:
                return WRONG_NUM_ARGS
            try:
                args[3] = args[3].upper()
                order = api.submit_order(
                    args[3],
                    args[2],
                    args[1],
                    args[0].lower(),
                    args[4],
                    stop_price=args[5])
                text = f'Stop order of | {args[1]} {args[2]} {args[3]} {args[4]} at stop price {args[5]} | submitted.  Order id = {order.id}.'
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        elif args[0].lower() == "stop_limit":
            if len(args) != 7:
                reply_private(request, WRONG_NUM_ARGS)
                return
            try:
                args[3] = args[3].upper()
                order = api.submit_order(
                    args[3],
                    args[2],
                    args[1],
                    args[0].lower(),
                    args[4],
                    limit_price=args[5],
                    stop_price=args[6])
                text = f'Stop-Limit order of | {args[1]} {args[2]} {args[3]} {args[4]} at stop price {args[6]} and limit price {args[5]} | submitted.  Order id = {order.id}.'
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        else:
            return BAD_ARGS
    asyncio.run(sub_order(api, request, args))
    return ""

# Lists certain things.  Must contain 1 argument: orders, positions, or
# streams.


@app.route("/list", methods=["POST"])
def list_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 0:
        return WRONG_NUM_ARGS
    if args[0] == "positions":
        try:
            positions = api.list_positions()
            if len(positions) == 0:
                return "No positions."
            positions = map(
                lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Entry price: {x.avg_entry_price}, Current price: {x.current_price}'),
                positions)
            return "Listing positions...\n" + '\n'.join(positions)
        except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
    elif args[0] == "orders" :
        try:
            orders = api.list_orders(status="open")
            if len(orders) == 0:
                return "No orders."
            orders = map(
                lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Type: {x.type}, Time in Force: {x.time_in_force}, Amount Filled: {x.filled_qty}{(f", Stop Price = {x.stop_price}","")[x.stop_price == None]}{(f", Limit Price = {x.limit_price}","")[x.limit_price == None]}, Order id = {x.id}'),
                orders)
            return "Listing orders...\n" + '\n'.join(orders)
        except Exception as e:
            reply_private(request, f"ERROR: {str(e)}")
    elif args[0] == "streams":
        text = "Listing active streams...\n"
        try:
            for stream in streams:
                if streams[stream] is not None:
                    text += (stream + "\n")
            if text == "Listing active streams...\n":
                return "No active streams."
            return text
        except Exception as e:
            reply_private(request, f"ERROR: {str(e)}")
    else:
        return BAD_ARGS

# Clears positions or orders.  Must contain 1 argument: positions or orders


@app.route("/clear", methods=["POST"])
def clear_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 0:
        return WRONG_NUM_ARGS
    if args[0] == "positions":
        async def sub_clear_positions(api, request):
            try:
                positions = api.list_positions()
                positions = map(lambda x: [x.symbol, x.qty, x.side], positions)
                for position in positions:
                    api.submit_order(position[0], abs(
                        int(position[1])), "sell" if position[2] == "long" else "buy", "market", "day")
                text = "Position clearing orders sent."
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        asyncio.run(sub_clear_positions(api, request))
        return ""
    elif args[0] == "orders":
        async def sub_clear_orders(api, request):
            try:
                orders = api.list_orders()
                orders = map(lambda x: x.id, orders)
                for order in orders:
                    api.cancel_order(order)
                text = "Order cancels sent."
                response = requests.post(
                    url="https://slack.com/api/chat.postMessage",
                    data={
                        "token": config["slack_token"],
                        "channel": request.form.get("channel_name"),
                        "text": text})
            except Exception as e:
                reply_private(request, f"ERROR: {str(e)}")
        asyncio.run(sub_clear_orders(api, request))
        return ""
    else:
        return BAD_ARGS

# Cancels order by id.  Must take one argument: order_id


@app.route("/cancel_order", methods=["POST"])
def cancel_order_handler():
    args = request.form.get("text").split(" ")
    if len(args) != 1:
        return WRONG_NUM_ARGS
    try:
        api.cancel_order(args[0])
        text = f'Order canceled.  Order id = {args[0]}'
        return text
    except Exception as e:
        return f"ERROR: {str(e)}"

# Cancels most recent order.  Takes no arguments.


@app.route("/cancel_recent_order", methods=["POST"])
def cancel_recent_order_handler():
    args = request.form.get("text").split(" ")
    if len(args) != 0 and not (len(args) == 1 and args[0].strip() == ""):
        return WRONG_NUM_ARGS
    try:
        orders = api.list_orders(status="open", limit=1)
        if len(orders) == 0:
            return "No orders to cancel."
        api.cancel_order(orders[0].id)
        text = f'Most recent order cancelled.  Order id = {orders[0].id}'
        return text
    except Exception as e:
        return f"ERROR: {str(e)}"

# Gets basic account info.  Takes no arguments.


@app.route("/account_info", methods=["POST"])
def account_info_handler():
    args = request.form.get("text").split(" ")
    if len(args) != 0 and not (len(args) == 1 and args[0].strip() == ""):
        return WRONG_NUM_ARGS
    try:
        account = api.get_account()
        text = f'Account info...\nBuying power = {account.buying_power}\nEquity = {account.equity}\nPortfolio value = {account.portfolio_value}\nShorting enabled? = {account.shorting_enabled}'
        return text
    except Exception as e:
        return f"ERROR: {str(e)}"

# Gets Polygon price specified stock symbols.  Must include one or more
# arguments representing stock symbols. Must have live account to access.


@app.route("/get_price_polygon", methods=["POST"])
def get_price_polygon_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 1 and args[0].strip() == "":
        return WRONG_NUM_ARGS

    async def sub_get_price_polygon(api, request, args):
        try:
            text = "Listing prices..."
            args = map(lambda x: x.upper(), args)
            for symbol in args:
                quote = api.polygon.last_quote(symbol)
                text += f'\n{symbol}: Bid price = {quote.bidprice}, Ask price = {quote.askprice}'
            reply_private(request, text)
        except Exception as e:
            reply_private(request, f"ERROR: {str(e)}")
    asyncio.run(sub_get_price_polygon(api, request, args))
    return ""

# Gets price specified stock symbols.  Must include one or more arguments
# representing stock symbols.


@app.route("/get_price", methods=["POST"])
def get_price_handler():
    args = request.form.get("text").split(" ")
    if len(args) == 1 and args[0].strip() == "":
        return WRONG_NUM_ARGS

    async def sub_get_price(api, request, args):
        try:
            text = "Listing prices..."
            args = map(lambda x: x.upper(), args)
            bars = api.get_barset(args, "minute", 1)
            for bar in bars:
                text += f'\n{bar}: Price = {bars[bar][0].c}, Time = {bars[bar][0].t}'
            reply_private(request, text)
        except Exception as e:
            reply_private(request, f"ERROR: {str(e)}")
    asyncio.run(sub_get_price(api, request, args))
    return ""

# Provides a verbose description of each tradebot command


@app.route("/help_tradebot", methods=["POST"])
def help_tradebot_handler():
    args = request.form.get("text").split(" ")
    if len(args) != 0 and not (len(args) == 1 and args[0].strip() == ""):
        return WRONG_NUM_ARGS
    try:
        text = "Commands, arguments, and descriptions: \n\
            */order*: Executes order of specified type, limit/stop price as needed, <type> <side> <qty> <symbol> <time_in_force> <(optional) limit_price> <(optional) stop_price> \n\
            */list*: Lists things, <'positions'/'orders'/'streams'> \n\
            */clear*: Clears things, <'positions'/'orders'> \n\
            */subscribe_streaming*: Subscribe to streaming channels, <[channels]> \n\
            */unsubscribe_streaming*: Unsubscribe from streaming channels, <[channels]> \n\
            */account_info*: Gets basic account info, *no args* \n\
            */get_price*: Gets the price(s) of the given symbol(s), <[symbol(s)]> \n\
            */get_price_polygon*: Polygon pricing data of given symbol(s), live accounts only, <[symbol(s)]> \n\
            */help_tradebot*: Provides a descripion of each command, *no args* \n\
            */cancel_order*: Cancels order by order id, <order_id> \n\
            */cancel_recent_order*: Cancels most recent order, *no_args*"
        return text
    except Exception as e:
        return f'ERROR: {str(e)}'

# Run on local port 3000


if __name__ == "__main__":
    app.run(port=3000)