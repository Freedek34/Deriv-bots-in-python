import websocket
import json
import threading
import asyncio
import os
import numpy as np
from deriv_api import DerivAPI, APIError

# Constants
APP_ID = '1089'  # Replace with your actual app_id
URL = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
api_token = os.getenv('DERIV_TOKEN', '')

if not api_token:
    sys.exit("DERIV_TOKEN environment variable is not set")

# Configuration
BET_AMOUNT = 100
MAX_BET_AMOUNT = 10000  # Set a maximum limit for the Martingale strategy
TOTAL_ROUNDS = 100
TAKE_PROFIT = 5000
STOP_LOSS = 50000
INITIAL_HISTORY_SIZE = 10
MAX_HISTORY_SIZE = 20
MIN_HISTORY_SIZE = 5
INITIAL_EVEN_THRESHOLD = 0.10
INITIAL_ODD_THRESHOLD = 0.10
ADAPTIVE_THRESHOLD_BASE = 0.05
MAX_ADJUSTMENT_FACTOR = 0.10
MIN_THRESHOLD = 0.05
MAX_THRESHOLD = 0.30
PERFORMANCE_WINDOW = 10  # Number of rounds to track recent performance

# Initialize the historical data array and performance metrics
tick_data = []
performance_history = []
total_wins = 0
total_losses = 0
total_pnl = 0
current_history_size = INITIAL_HISTORY_SIZE
current_bet_amount = BET_AMOUNT  # Start with the base bet amount

def update_data(tick):
    global tick_data
    if len(tick_data) >= current_history_size:
        tick_data.pop(0)  # Maintain history size
    tick_data.append(int(tick))

def calculate_volatility():
    if len(tick_data) < 2:
        return 0
    return np.std(np.diff(tick_data))  # Standard deviation of tick differences

def normalize_counts():
    global tick_data
    if len(tick_data) < current_history_size:
        return 0, 0  # Not enough data to predict

    # Count even and odd occurrences
    even_count = np.sum(np.array(tick_data) % 2 == 0)
    odd_count = np.sum(np.array(tick_data) % 2 != 0)
    
    total_count = even_count + odd_count
    even_prob = even_count / total_count if total_count > 0 else 0
    odd_prob = odd_count / total_count if total_count > 0 else 0
    
    return even_prob, odd_prob

def predict_even_odd():
    even_prob, odd_prob = normalize_counts()
    
    if even_prob > odd_prob:
        return 'even', even_prob
    elif odd_prob > even_prob:
        return 'odd', odd_prob
    else:
        return None, 0  # No clear prediction

def adjust_history_size():
    global current_history_size
    volatility = calculate_volatility()
    
    # Increase history size if volatility is low, decrease if high
    if volatility < 0.1:
        current_history_size = min(current_history_size + 1, MAX_HISTORY_SIZE)
    elif volatility > 0.3:
        current_history_size = max(current_history_size - 1, MIN_HISTORY_SIZE)

def update_probability_thresholds():
    global INITIAL_EVEN_THRESHOLD
    global INITIAL_ODD_THRESHOLD
    global performance_history
    
    if len(performance_history) < PERFORMANCE_WINDOW:
        return
    
    recent_performance = performance_history[-PERFORMANCE_WINDOW:]
    
    # Calculate recent win/loss ratio
    recent_wins = sum(1 for result in recent_performance if result == "Win")
    recent_losses = sum(1 for result in recent_performance if result == "Loss")
    
    if recent_losses > 0:
        win_loss_ratio = recent_wins / recent_losses
    else:
        win_loss_ratio = float('inf')
    
    # Adjust thresholds based on recent performance
    adjustment_factor = min(MAX_ADJUSTMENT_FACTOR, ADAPTIVE_THRESHOLD_BASE * win_loss_ratio)
    
    if win_loss_ratio > 1:
        # Increase thresholds if the win/loss ratio is favorable
        INITIAL_EVEN_THRESHOLD = min(INITIAL_EVEN_THRESHOLD + adjustment_factor, MAX_THRESHOLD)
        INITIAL_ODD_THRESHOLD = min(INITIAL_ODD_THRESHOLD + adjustment_factor, MAX_THRESHOLD)
    else:
        # Decrease thresholds if the win/loss ratio is unfavorable
        INITIAL_EVEN_THRESHOLD = max(INITIAL_EVEN_THRESHOLD - adjustment_factor, MIN_THRESHOLD)
        INITIAL_ODD_THRESHOLD = max(INITIAL_ODD_THRESHOLD - adjustment_factor, MIN_THRESHOLD)

def on_message(ws, message):
    data = json.loads(message)
    if 'error' in data:
        print('Error:', data['error']['message'])
        ws.close()
    elif data['msg_type'] == 'history':
        ticks = data['history']['prices']
        for tick in ticks:
            update_data(tick)
    elif data['msg_type'] == 'tick':
        tick = data['tick']['quote']
        update_data(tick)

def on_error(ws, error):
    print("WebSocket error:", error)

def on_close(ws):
    print("WebSocket connection closed")

def on_open(ws):
    def run(*args):
        TICKS_REQUEST = {
            "ticks_history": "R_100",
            "adjust_start_time": 1,
            "count": INITIAL_HISTORY_SIZE,
            "end": "latest",
            "start": 1,
            "style": "ticks",
            "subscribe": 1
        }
        ws.send(json.dumps(TICKS_REQUEST))
        
    threading.Thread(target=run).start()

def subscribe_ticks():
    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(URL,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.on_open = on_open
    ws.run_forever()

async def sample_calls():
    global total_wins, total_losses, total_pnl, performance_history, current_bet_amount

    api = DerivAPI(app_id=APP_ID)
    
    await api.authorize(api_token)
    balance = await api.balance()
    initial_balance = balance['balance']['balance']
    current_balance = initial_balance
    
    round_num = 1
    
    while round_num <= TOTAL_ROUNDS:
        await asyncio.sleep(1)  # Adjust this as needed

        update_probability_thresholds()
        adjust_history_size()

        predicted, probability = predict_even_odd()
        
        if predicted is None:
            print(f"Round {round_num}: Skipping trade due to insufficient data")
            round_num += 1
            continue
        
        # Set the appropriate threshold based on the prediction
        if predicted == 'even':
            threshold = INITIAL_EVEN_THRESHOLD
            contract_type = "DIGITEVEN"
        else:
            threshold = INITIAL_ODD_THRESHOLD
            contract_type = "DIGITODD"
        
        if probability < threshold:
            print(f"Round {round_num}: Skipping trade due to low confidence")
            round_num += 1
            continue
        
        print(f"Round {round_num}: Placing {contract_type} trade with bet amount: {current_bet_amount}")

        trade_placed = False
        
        try:
            proposal = await api.proposal({
                "proposal": 1,
                "amount": current_bet_amount,
                "barrier": "0",  # Barrier not needed for even/odd
                "basis": "payout",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": 1,
                "duration_unit": "t",
                "symbol": "R_100"
            })
            proposal_id = proposal.get('proposal', {}).get('id')
            if not proposal_id:
                print("Failed to get proposal")
                round_num += 1
                continue
        except APIError as e:
            print(f"Failed to get proposal: {e}")
            round_num += 1
            continue
        
        try:
            buy_response = await api.buy({"buy": proposal_id, "price": current_bet_amount})
            contract_id = buy_response.get('buy', {}).get('contract_id')
            if not contract_id:
                print("Failed to get contract ID")
                round_num += 1
                continue
            trade_placed = True
        except APIError as e:
            print(f"Failed to buy: {e}")
            round_num += 1
            continue

        if trade_placed:
            try:
                profit_table = await api.profit_table({"profit_table": 1, "limit": 1})
                if profit_table and 'profit_table' in profit_table:
                    last_trade = profit_table['profit_table']['transactions'][0]
                    sell_price = last_trade['sell_price']
                    
                    if sell_price == 0:
                        total_losses += 1
                        total_pnl -= current_bet_amount
                        performance_history.append("Loss")
                        print(f"Round {round_num}: Loss. Sell price: {sell_price}. Current balance: {current_balance}.")
                        current_bet_amount = min(current_bet_amount * 2, MAX_BET_AMOUNT)
                    else:
                        total_wins += 1
                        total_pnl += (sell_price - current_bet_amount)
                        performance_history.append("Win")
                        print(f"Round {round_num}: Win! Sell price: {sell_price}. Current balance: {current_balance}.")
                        current_bet_amount = BET_AMOUNT  # Reset to base bet amount
            except APIError as e:
                print(f"Failed to fetch profit table: {e}")
        
        # Update balance and round counter
        current_balance = initial_balance + total_pnl
        print(f"PnL: {total_pnl}, Wins: {total_wins}, Losses: {total_losses}")

        # Check for stop loss or take profit conditions
        if total_pnl >= TAKE_PROFIT:
            print("Take profit reached. Stopping bot.")
            break
        elif total_pnl <= -STOP_LOSS:
            print("Stop loss reached. Stopping bot.")
            break
        
        round_num += 1
    
    await api.logout()

if __name__ == "__main__":
    tick_thread = threading.Thread(target=subscribe_ticks)
    tick_thread.start()
    
    asyncio.run(sample_calls())
