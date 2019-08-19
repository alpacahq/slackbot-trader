from flask import Flask, request
import alpaca_trade_api as tradeapi
import requests
import multiprocessing
import asyncio
import json

### Note: Slack commands automatically provide a whitespace for ensuing arguments.  Checks
#   that look like: len(args) == 1 and args[0].strip() == "" are checking if the user input 0 args,
#   which would be received as 1 string argument containing " ".

# Constants used throughout the script (names are self-explanatory)
WRONG_NUM_ARGS = "ERROR: Incorrect amount of args.  Action did not complete."
BAD_ARGS = "ERROR: Request error.  Action did not complete."
SLACK_TOKEN = "SLACK_TOKEN_HERE"
KEY_ID = "KEY_ID_HERE"
SECRET_KEY = "SECRET_KEY_HERE"
CHANNEL = "CHANNEL_TO_POST_TO_HERE"

# Set up environment 
conn = tradeapi.StreamConn(KEY_ID,SECRET_KEY,base_url="https://paper-api.alpaca.markets")
api = tradeapi.REST(KEY_ID,SECRET_KEY,base_url="https://paper-api.alpaca.markets",api_version='v2')

# Initialize the Flask object which will be used to handle HTTP requests from Slack
app = Flask(__name__)

# Initialize the dictionary of streams that we are listening to; None denotes not listening
streams = {
  "account_updates": None,
  "trade_updates": None,
}
# Streaming handlers

# Subscribe to streaming channel(s).  Must contain one or more arguments representing streams you want to connect to.
@app.route("/subscribe_streaming",methods=["POST"])
def stream_data_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return BAD_ARGS
  try:
    connected = 0
    for stream in args:
      # If the specified stream exists in the dictionary and it hasn't been initialized, subscribe and listen to it.
      if(streams[stream] == None):
        streams[stream] = multiprocessing.Process(target=runThread, args=(stream,))
        streams[stream].start()
        connected += 1
    if(len(args) == connected):
      text = f"Subscription{('','s')[connected > 1]} to {(' ').join(args)} sent."
      response = requests.post(url="https://slack.com/api/chat.postMessage",data={
        "token": SLACK_TOKEN,
        "channel": request.form.get("channel_name"),
        "text": text
      })
      return ""
    else:
      return f"{len(args) - connected} subscription(s) failed."
  except Exception as e:
    return f'ERROR: {str(e)}'

# Unsubsribe to streaming channel(s).  Must contain one or more arguments representing streams you want to disconnect to.
@app.route("/unsubscribe_streaming",methods=["POST"])
def unsubscribe_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return BAD_ARGS
  try:
    disconnected = 0
    for stream in args:
      # If the specified stream exists in the dictionary and it has been initialized, stop listening.
      if(streams[stream] != None):
        streams[stream].terminate()
        streams[stream] = None
        disconnected += 1
    if(len(args) == disconnected):
      text = f"Unsubscription{('', 's')[disconnected > 1]} to {(' ').join(args)} sent."
      response = requests.post(url="https://slack.com/api/chat.postMessage",data={
        "token": SLACK_TOKEN,
        "channel": request.form.get("channel_name"),
        "text": text
      })
      return ""
    else:
      return f"{len(args) - disconnected} unsubscription(s) failed."
  except Exception as e:
    return f'ERROR: {str(e)}'

@conn.on(r'trade_updates')
async def trade_updates_handler(conn, chan, data):
  if(data.event == "new"):
    return ""
  elif(data.event == "fill" or data.event == "partial_fill"):
    text = f'Event: {data.event}, {data.order["type"]} order of | {data.order["side"]} {data.order["qty"]} {data.order["symbol"]} | {data.event} at {data.price}'
  else:
    text = f'Event: {data.event}, {data.order["type"]} order of | {data.order["side"]} {data.order["qty"]} {data.order["symbol"]} {data.event}'
  response = requests.post(url="https://slack.com/api/chat.postMessage",data={
    "token": SLACK_TOKEN,
    "channel": CHANNEL,
    "text": text
  }) 
  return ""
@conn.on(r'account_updates')
async def account_updates_handler(conn, chan, data):
  text = f'Account updated.  Account balance is currently: {data.cash} {data.currency}'
  response = requests.post(url="https://slack.com/api/chat.postMessage",data={
    "token": SLACK_TOKEN,
    "channel": CHANNEL,
    "text": text
  })
  return ""

# Helper function to listen to a stream
def runThread(stream):
  conn.run([stream])

# Order/Account handlers

# Execute an order.  Must contain 5, 6, or 7 arguments: type, symbol, quantity, side, time in force, limit price (optional), and stop price (optional).
@app.route("/order",methods=["POST"])
def order_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 0):
    return WRONG_NUM_ARGS
  async def sub_order(api,request,args):
    if(args[0].lower() == "market"):
      if(len(args) != 5):
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": WRONG_NUM_ARGS}), headers={"Content-type": "application/json"})
      try:
        args[3] = args[3].upper()
        order = api.submit_order(args[3],args[2],args[1],args[0],args[4])
        price = api.get_barset(args[3],'minute',1)[args[3]][0].c
        text = f'Market order of | {args[1]} {args[2]} {args[3]} | submitted, current equity price at {price}.  Order id = {order.id}.'
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
    elif(args[0].lower() == "limit"):
      if(len(args) != 6):
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": WRONG_NUM_ARGS}), headers={"Content-type": "application/json"})
      try:
        args[3] = args[3].upper()
        order = api.submit_order(args[3],args[2],args[1],args[0].lower(),args[4],limit_price=args[5])
        text = f'Limit order of | {args[1]} {args[2]} {args[3]} at limit price {args[5]} | submitted.  Order id = {order.id}.'
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
    elif(args[0].lower() == "stop"):
      if(len(args) != 6):
        return WRONG_NUM_ARGS
      try:
        args[3] = args[3].upper()
        order = api.submit_order(args[3],args[2],args[1],args[0].lower(),args[4],stop_price=args[5])
        text = f'Stop order of | {args[1]} {args[2]} {args[3]} at stop price {args[5]} | submitted.  Order id = {order.id}.'
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
    elif(args[0].lower() == "stop_limit"):
      if(len(args) != 7):
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": WRONG_NUM_ARGS}), headers={"Content-type": "application/json"})
      try:
        args[3] = args[3].upper()
        order = api.submit_order(args[3],args[2],args[1],args[0].lower(),args[4],limit_price=args[5],stop_price=args[6])
        text = f'Stop-Limit order of | {args[1]} {args[2]} {args[3]} at stop price {args[6]} and limit price {args[5]} | submitted.  Order id = {order.id}.'
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
    else:
      return BAD_ARGS
  asyncio.run(sub_order(api,request,args))
  return ""


# Lists certain things.  Must contain 1 argument: orders, positions, or streams.
@app.route("/list",methods=["POST"])
def list_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 0):
    return WRONG_NUM_ARGS
  if(args[0] == "positions"):
    try:
      positions = api.list_positions()
      if(len(positions) == 0):
        return "No positions."
      positions = map(lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Entry price: {x.avg_entry_price}, Current price: {x.current_price}'),positions)
      return "Listing positions...\n" + '\n'.join(positions)
    except Exception as e:
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
  elif(args[0] == "orders"):
    try:
      orders = api.list_orders(status="open")
      if(len(orders) == 0):
        return "No orders."
      orders = map(lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Type: {x.type}, Amount filled: {x.filled_qty}{(f", Stop Price = {x.stop_price}","")[x.stop_price == None]}{(f", Limit Price = {x.limit_price}","")[x.limit_price == None]}'),orders)
      return "Listing orders...\n" + '\n'.join(orders)
    except Exception as e:
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
  elif(args[0] == "streams"):
    text = "Listing active streams...\n"
    try:
      for stream in streams:
        if(streams[stream] != None):
          text += (stream + "\n")
      if(text == "Listing active streams...\n"):
        return "No active streams."
      return text
    except Exception as e:
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
  else:
    return BAD_ARGS

# Clears positions or orders.  Must contain 1 argument: positions or orders
@app.route("/clear",methods=["POST"])
def clear_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 0):
    return WRONG_NUM_ARGS
  if(args[0] == "positions"):
    async def sub_clear_positions(api,request):
      try:
        positions = api.list_positions()
        positions = map(lambda x: [x.symbol,x.qty,x.side],positions)
        for position in positions:
          api.submit_order(position[0],abs(int(position[1])),"sell" if position[2] == "long" else "buy","market","day")
        text = "Clearing orders"
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:        
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f'ERROR: {str(e)}'}), headers={"Content-type": "application/json"})
    asyncio.run(sub_clear_positions(api,request))
    return ""
  elif(args[0] == "orders"):
    async def sub_clear_orders(api,request):
      try:
        orders = api.list_orders()
        orders = map(lambda x: x.id,orders)
        for order in orders:
          api.cancel_order(order)
        text = "Orders cleared."
        response = requests.post(url="https://slack.com/api/chat.postMessage",data={
          "token": SLACK_TOKEN,
          "channel": request.form.get("channel_name"),
          "text": text
        })
      except Exception as e:
        response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f'ERROR: {str(e)}'}), headers={"Content-type": "application/json"})
    asyncio.run(sub_clear_orders(api,request))
    return ""
  else:
    return BAD_ARGS

# Gets basic account info.  Takes no arguments.
@app.route("/account_info",methods=["POST"])
def account_info_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 0 and not (len(args) == 1 and args[0].strip() == "")):
    return WRONG_NUM_ARGS
  try:
    account = api.get_account()
    text = f'Account info...\nBuying power = {account.buying_power}\nEquity = {account.equity}\nPortfolio value = {account.portfolio_value}\nShorting enabled? = {account.shorting_enabled}'
    return text
  except Exception as e:
    return f"ERROR: {str(e)}"

# Gets Polygon price specified stock symbols.  Must include one or more arguments representing stock symbols. Must have live account to access
@app.route("/get_price_polygon",methods=["POST"])
def get_price_polygon_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return WRONG_NUM_ARGS
  async def sub_get_price_polygon(api,request):
    try:
      text = "Listing prices..."
      for symbol in args:
        quote = api.polygon.last_quote(symbol)
        text += f'\n{symbol}: Bid price = {quote.bidprice}, Ask price = {quote.askprice}'
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": text}), headers={"Content-type": "application/json"})
    except Exception as e:
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
  asyncio.run(sub_get_price_polygon(api,request))
  return ""

# Gets price specified stock symbols.  Must include one or more arguments representing stock symbols.
@app.route("/get_price",methods=["POST"])
def get_price_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return WRONG_NUM_ARGS
  async def sub_get_price(api,request):
    try:
      text = "Listing prices..."
      bars = api.get_barset(args,"minute",1)
      for bar in bars:
        text += f'\n{bar}: Price = {bars[bar][0].c}, Time = {bars[bar][0].t}'
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": text}), headers={"Content-type": "application/json"})
    except Exception as e:
      response = requests.post(url=request.form.get("response_url"), data=json.dumps({"text": f"ERROR: {str(e)}"}), headers={"Content-type": "application/json"})
  asyncio.run(sub_get_price(api,request))
  return ""

# Provides a verbose description of each tradebot command
@app.route("/help_tradebot",methods=["POST"])
def help_tradebot_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 0 and not (len(args) == 1 and args[0].strip() == "")):
    return WRONG_NUM_ARGS
  try:
    text = "Commands, arguments, and descriptions: \n\
      */order*: Execute order of specified type, limit/stop price as needed, <type> <side> <qty> <symbol> <time_in_force> <(optional) limit_price> <(optional) stop_price> \n\
      */list*: Lists things, <'positions'/'orders'/'streams'> \n\
      */clear*: Clears things, <'positions'/'orders'> \n\
      */set_api_keys*: Sets the API keys, must specify 'paper' or 'live' as 3rd argument, <KEY_ID> <SECRET_KEY> <'paper'/'live'> \n\
      */subscribe_streaming*: Subscribe to streaming channels, <[channels]> \n\
      */unsubscribe_streaming*: Unsubscribe from streaming channels, <[channels]> \n\
      */account_info*: Gets basic account info, no args \n\
      */get_price*: Gets the price(s) of the given symbol(s), <[symbol(s)]> \n\
      */get_price_polygon*: Polygon pricing data of given symbol(s), live accounts only, <[symbols]> \n\
      */help_tradebot*: Provides a descripion of each command, no args"
    return text
  except Exception as e:
    return f'ERROR: {str(e)}'

# Run on local port 3000
if __name__ == "__main__":
  app.run(port=3000)