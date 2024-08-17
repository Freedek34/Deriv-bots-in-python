import json
import time
import websocket
import random
import threading

# Replace with your actual demo account API token
API_TOKEN = ''
API_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"

# Initialize variables
initial_balance = 0  # This will be set to the current balance of the demo account
balance = initial_balance
bet_amount = 100
initial_bet_amount = bet_amount
max_bet = 10000  # Maximum bet limit
martingale_multiplier = 1.5
take_profit = 5000
stop_loss = 5000

# Payouts
payout_under_5 = 1.43
payout_over_4 = 1.43

# Tracking variables
wins = 0
losses = 0
total_bets = 0
stop_requested = False

def on_open(ws):
    print("Connection opened. Authorizing...")
    ws.send(json.dumps({"authorize": API_TOKEN}))

def on_message(ws, message):
    global balance, bet_amount, wins, losses, total_bets, stop_requested

    response = json.loads(message)

    if 'error' in response:
        print("Error:", response['error']['message'])
        ws.close()
        return

    if 'authorize' in response:
        # After authorization, request account balance
        ws.send(json.dumps({"balance": 1}))

    elif 'balance' in response:
        # Set the initial balance
        global initial_balance
        initial_balance = float(response['balance']['balance'])
        balance = initial_balance
        print(f"Initial Balance: {balance}")

        # Start trading loop
        trading_thread = threading.Thread(target=trade, args=(ws,))
        trading_thread.start()

        # Wait for the trading to stop
        trading_thread.join()
        summarize_results()

def trade(ws):
    global balance, bet_amount, wins, losses, total_bets, stop_requested

    while not stop_requested and balance - initial_balance < take_profit and initial_balance - balance < stop_loss:
        # Generate the next number
        next_number = random.randint(0, 9)
        
        # Make a prediction
        prediction = predict_trade_type(next_number)

        if prediction == "none":
            continue

        # Get last digit (for digit-based contract)
        last_digit = next_number % 10

        # Place the trade
        place_trade(ws, prediction, last_digit)

        # Simulate the result (this should be replaced with actual API result checking)
        payout = calculate_payout(prediction, next_number)

        if payout > 0:
            # Bot wins
            balance += bet_amount * payout
            wins += 1
            bet_amount = initial_bet_amount  # Reset bet after win
        else:
            # Bot loses
            balance -= bet_amount
            losses += 1
            bet_amount = min(bet_amount * martingale_multiplier, max_bet)

        total_bets += 1

        print(f"Round {total_bets}: Prediction: {prediction}, Number: {next_number}, Balance: {balance}, Bet: {bet_amount}")

        # Short delay before next trade
        time.sleep(2)

    # Stop trading if requested
    if stop_requested:
        print("Stop operation requested.")
        ws.close()

def place_trade(ws, prediction, last_digit):
    # Correct contract type and parameters for digit-based trades
    contract_type = "DIGITOVER" if prediction == "over_4" else "DIGITUNDER"

    # Send a trade request
    ws.send(json.dumps({
        "buy": 1,
        "parameters": {
            "contract_type": contract_type,
            "symbol": "R_100",  # Example symbol for Deriv
            "duration": 1,
            "duration_unit": "m",
            "amount": bet_amount,
            "basis": "stake",
            "currency": "USD",
            "last_digit": last_digit
        }
    }))

def predict_trade_type(number):
    if number > 4:
        return "over_4"
    elif number < 5:
        return "under_5"
    else:
        return "none"

def calculate_payout(prediction, actual):
    if prediction == "under_5" and actual < 5:
        return payout_under_5
    elif prediction == "over_4" and actual > 4:
        return payout_over_4
    else:
        return 0

def summarize_results():
    global balance, wins, losses, total_bets

    win_ratio = (wins / total_bets) * 100 if total_bets > 0 else 0
    loss_ratio = (losses / total_bets) * 100 if total_bets > 0 else 0

    print(f"\nFinal Balance: ${balance}")
    print(f"Total Wins: {wins}")
    print(f"Total Losses: {losses}")
    print(f"Total Bets: {total_bets}")
    print(f"Win Ratio: {win_ratio:.2f}%")
    print(f"Loss Ratio: {loss_ratio:.2f}%")

def on_error(ws, error):
    print("Error:", error)

def on_close(ws, *args):
    print("Connection closed.")

if __name__ == "__main__":
    ws = websocket.WebSocketApp(API_URL,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)
    ws.run_forever()
