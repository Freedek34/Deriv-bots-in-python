import sys
import asyncio
import os
import random
import numpy as np
from deriv_api import DerivAPI, APIError

# Configuration
app_id = 0000
api_token = os.getenv('DERIV_TOKEN', '')  # Fetch token from environment or use default

if not api_token:
    sys.exit("DERIV_TOKEN environment variable is not set")

BET_AMOUNT = 100
TOTAL_ROUNDS = 25  # Number of rounds to run
TAKE_PROFIT = 5000
STOP_LOSS = 5000

# Initialize digit counter and transition matrix
digit_counter = {i: 0 for i in range(10)}
matrix_size = 10
transition_matrix = np.zeros((matrix_size, matrix_size), dtype=int)
previous_digit = None

async def sample_calls():
    global previous_digit

    api = DerivAPI(app_id=app_id)
    
    try:
        # Authorize with the API token
        await api.authorize(api_token)
    except APIError as e:
        print(f"Authorization failed: {e}")
        return
    
    # Get initial balance
    try:
        balance = await api.balance()
        initial_balance = balance['balance']['balance']
        current_balance = initial_balance
    except APIError as e:
        print(f"Failed to retrieve balance: {e}")
        return
    
    total_pnl = 0
    
    for round_num in range(1, TOTAL_ROUNDS + 1):
        # Simulate fetching the last digit (replace with real API call if available)
        digit = random.randint(0, 9)  # Replace with actual digit retrieval logic
        
        # Update digit counter and transition matrix
        digit_counter[digit] += 1
        if previous_digit is not None:
            transition_matrix[previous_digit, digit] += 1
        previous_digit = digit
        
        print(f"Round {round_num}: Predicted digit is {digit}")
        print(f"Digit Counts: {digit_counter}")
        print(f"Transition Matrix:\n{transition_matrix}")

        # Predict the next digit
        if previous_digit is not None:
            next_digit_probabilities = transition_matrix[previous_digit]
            predicted_digit = np.argmax(next_digit_probabilities)
        else:
            predicted_digit = digit  # If no previous digit, use current digit

        # Determine contract type and barrier
        if predicted_digit > 5:
            contract_type = "DIGITOVER"
            barrier = 5
        elif predicted_digit < 4:
            contract_type = "DIGITUNDER"
            barrier = 4
        else:
            print(f"Round {round_num}: Skipping trade as predicted digit {predicted_digit} is not within trade conditions")
            continue
        
        print(f"Round {round_num}: Placing {contract_type} trade")

        # Get trade proposal
        try:
            proposal = await api.proposal({
                "proposal": 1,
                "amount": BET_AMOUNT,
                "barrier": str(barrier),
                "basis": "payout",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": 1,  # Duration set to 1 tick
                "duration_unit": "t",
                "symbol": "R_100"
            })
            proposal_id = proposal.get('proposal', {}).get('id')
            if not proposal_id:
                print("Failed to get proposal")
                continue
        except APIError as e:
            print(f"Failed to get proposal: {e}")
            continue
        
        # Execute trade
        try:
            buy_response = await api.buy({"buy": proposal_id, "price": BET_AMOUNT})
            contract_id = buy_response.get('buy', {}).get('contract_id')
            if not contract_id:
                print("Failed to get contract ID")
                continue
        except APIError as e:
            print(f"Failed to buy: {e}")
            continue

        # Wait for the contract to settle
        await asyncio.sleep(1)  # Adjust based on actual contract duration

        # Check profit/loss
        try:
            profit_table = await api.profit_table({"profit_table": 1, "limit": 1})
            if profit_table and 'profit_table' in profit_table:
                latest_trade = profit_table['profit_table']['transactions'][0]
                if 'profit' in latest_trade:
                    pnl = float(latest_trade['profit'])
                    total_pnl += pnl
                    current_balance = initial_balance + total_pnl

                    result = "Win" if pnl > 0 else "Loss"
                    print(f"Round {round_num} result: {result}, PnL = {pnl:.2f}, Current Balance = {current_balance:.2f}")
                else:
                    print(f"Profit data not available for the latest trade: {latest_trade}")
            else:
                print("Failed to retrieve the latest trade result from profit table.")
        except APIError as e:
            print(f"Failed to retrieve profit table: {e}")
            continue
        
        # Check if take profit or stop loss conditions are met
        if current_balance >= initial_balance + TAKE_PROFIT or initial_balance - current_balance >= STOP_LOSS:
            print("Take profit or stop loss condition met.")
            break
    
    # Display final statistics
    try:
        profit_table = await api.profit_table({"profit_table": 1, "description": 1})
        wins = len([t for t in profit_table['profit_table']['transactions'] if float(t.get('profit', 0)) > 0])
        losses = len([t for t in profit_table['profit_table']['transactions'] if float(t.get('profit', 0)) < 0])

        print(f"Final Balance: {current_balance:.2f}")
        print(f"Total PnL: {total_pnl:.2f}")
        print(f"Total Wins: {wins}")
        print(f"Total Losses: {losses}")
    except APIError as e:
        print(f"Failed to retrieve final statistics: {e}")

    # Clear API session
    await api.clear()

# Run the bot
asyncio.run(sample_calls())
