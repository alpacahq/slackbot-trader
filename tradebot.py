from slackeventsapi import SlackEventAdapter
from flask import Flask, request, make_response
import alpaca_trade_api as tradeapi
import os
import threading
import asyncio
import requests
import multiprocessing

conn = tradeapi.StreamConn('API_KEY_ID_HERE','API_SECRET_KEY_HERE')
api = tradeapi.REST('API_KEY_ID_HERE','API_SECRET_KEY_HERE',api_version='v2')
app = Flask(__name__)
wrong_num_args = "ERROR: Incorrect amount of args.  Action did not complete."
bad_args = "ERROR: Request error.  Action did not complete."
slack_token = "SLACK_TOKEN_HERE"
streams = {
  "account_updates": None,
  "trade_updates": None,
}


@app.route("/set_api_keys",methods=["POST"])
def set_api_keys_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 2):
    return wrong_num_args
  try:
    global api, conn
    api = tradeapi.REST(args[0],args[1],api_version='v2')
    conn = tradeapi.StreamConn(args[0],args[1])
    text = f'API keys set as follows:\nAPCA_API_KEY_ID={args[0]}\nAPCA_API_SECRET_KEY={args[1]}'
    response = requests.post(url="https://slack.com/api/chat.postMessage",data={
      "token": slack_token,
      "channel": request.form.get("channel_name"),
      "text": text
    })
    return ""
  except Exception as e:
    return f'ERROR: + {str(e)}'

# Streaming handlers

@app.route("/subscribe_streaming",methods=["POST"])
def stream_data_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return bad_args
  try:
    connected = 0
    for stream in args:
      if(streams[stream] == None):
        streams[stream] = multiprocessing.Process(target=runThread, args=(stream,))
        streams[stream].start()
        connected += 1
    if(len(args) == connected):
      return "Subscription" + ("","s")[connected > 1] + " successful."
    else:
      return f"{len(args) - connected} subscription(s) failed."
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/unsubscribe_streaming",methods=["POST"])
def unsubscribe_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return bad_args
  try:
    disconnected = 0
    for stream in args:
      if(streams[stream] != None):
        streams[stream].terminate()
        streams[stream] = None
        disconnected += 1
    if(len(args) == disconnected):
      return "Unsubscription" + ("", "s")[disconnected > 1] + " successful."
    else:
      return f"{len(args) - disconnected} unsubscription(s) failed."
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/list_streams",methods=["POST"])
def list_streams_handler():
  text = "Listing active streams...\n"
  try:
    for stream in streams:
      if(streams[stream] != None):
        text += (stream + "\n")
    if(text == "Listing active streams...\n"):
      return "No active streams."
    return text
  except Exception as e:
    return f'ERROR: + {str(e)}'

@conn.on(r'trade_updates')
async def trade_updates_handler(conn, channel, data):
  text = f'Event: {data.event}, Symbol: {data.order["symbol"]}, Qty: {data.order["qty"]}, Side: {data.order["side"]}, Type: {data.order["type"]}'
  return text

@conn.on(r'account_updates')
async def account_updates_handler(conn, channel, data):
  text = f'Account updated.  Account balance is currently: {data.cash} {data.currency}'
  return text

def runThread(stream):
  conn.run([stream])

# Order/Account handlers

@app.route("/market_order",methods=["POST"])
def market_order_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 4):
    return wrong_num_args
  try:
    order = api.submit_order(args[0],args[1],args[2],"market",args[3])
    text = f'Market order of | {args[1]} {args[0]} {args[2]} | completed.  Order id = {order.id}.'
    response = requests.post(url="https://slack.com/api/chat.postMessage",data={
      "token": slack_token,
      "channel": request.form.get("channel_name"),
      "text": text
    })
    return ""
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/limit_order",methods=["POST"])
def limit_order_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 5):
    return wrong_num_args
  try:
    order = api.submit_order(args[0],args[1],args[2],"limit",args[3],limit_price=args[4])
    text = f'Limit order of | {args[1]} {args[0]} {args[2]} | submitted.  Order id = {order.id}.'
    response = requests.post(url="https://slack.com/api/chat.postMessage",data={
      "token": slack_token,
      "channel": request.form.get("channel_name"),
      "text": text
    })
    return ""
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/list_positions",methods=["POST"])
def positions_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 1 and args[0].strip() != ""):
    return wrong_num_args
  try:
    positions = api.list_positions()
    if(len(positions) == 0):
      return "No positions."
    positions = map(lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Entry price: {x.avg_entry_price}, Current price: {x.current_price}'),positions)
    return "Listing positions...\n" + '\n'.join(positions)
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/list_open_orders",methods=["POST"])
def open_orders_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 1 and args[0].strip() != ""):
    return wrong_num_args
  try:
    orders = api.list_orders(status="open")
    if(len(orders) == 0):
      return "No orders."
    orders = map(lambda x: (f'Symbol: {x.symbol}, Qty: {x.qty}, Side: {x.side}, Type: {x.type}, Amount filled: {x.filled_qty}'),orders)
    return "Listing orders...\n" + '\n'.join(orders)
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/clear_positions",methods=["POST"])
def clear_positions_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 1 and args[0].strip() != ""):
    return wrong_num_args
  try:
    positions = api.list_positions()
    positions = map(lambda x: [x.symbol,x.qty,x.side],positions)
    for position in positions:
      api.submit_order(position[0],abs(int(position[1])),"sell" if position[2] == "long" else "buy","market","day")
    text = "Positions cleared."
    response = requests.post(url="https://slack.com/api/chat.postMessage",data={
      "token": slack_token,
      "channel": request.form.get("channel_name"),
      "text": text
    })
    return ""
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/clear_orders",methods=["POST"])
def clear_orders_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 1 and args[0].strip() != ""):
    return wrong_num_args
  try:
    orders = api.list_orders()
    orders = map(lambda x: x.id,orders)
    for order in orders:
      api.cancel_order(order)
    text = "Orders cleared."
    response = requests.post(url="https://slack.com/api/chat.postMessage",data={
      "token": slack_token,
      "channel": request.form.get("channel_name"),
      "text": text
    })
    return ""
  except Exception as e:
    return f'ERROR: + {str(e)}'

@app.route("/account_info",methods=["POST"])
def account_info_handler():
  args = request.form.get("text").split(" ")
  if(len(args) != 1 and args[0].strip() != ""):
    return wrong_num_args
  try:
    account = api.get_account()
    text = f'Account info...\nBuying power = {account.buying_power}\nEquity = {account.equity}\nPortfolio value = {account.portfolio_value}\nShorting enabled? = {account.shorting_enabled}'
    return text
  except Exception as e:
    return f"ERROR: {str(e)}"

@app.route("/get_price",methods=["POST"])
def get_price_handler():
  args = request.form.get("text").split(" ")
  if(len(args) == 1 and args[0].strip() == ""):
    return wrong_num_args
  try:
    text = "Listing prices..."
    for symbol in args:
      quote = api.polygon.last_quote(symbol)
      text += f'\n{symbol}: Bid price = {quote.bidprice}, Ask price = {quote.askprice}'
    return text
  except Exception as e:
    return f'ERROR: {str(e)}'

# slack_events_adapter = SlackEventAdapter(os.environ.get("SLACK_SIGNING_SECRET"), "/slack/events", app)

if __name__ == "__main__":
  app.run(port=3000)