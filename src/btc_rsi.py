import requests
import pandas as pd
import numpy as np
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_cmc_data():
    # Get API key from environment variable
    api_key = os.getenv('CMC_API_KEY')
    if not api_key:
        raise ValueError("No CMC_API_KEY found in environment variables")

    # Base URL and headers
    base_url = 'https://pro-api.coinmarketcap.com/v2'
    headers = {
        'X-CMC_PRO_API_KEY': api_key,
        'Accept': 'application/json'
    }

    # Get historical data for BTC
    params = {
        'id': '1',  # BTC id
        'count': '100',  # Last 100 data points
        'interval': 'daily'
    }
    
    try:
        response = requests.get(
            f'{base_url}/cryptocurrency/quotes/historical',
            headers=headers,
            params=params
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_rsi(data, periods=14):
    # Convert price data to pandas series
    prices = pd.Series([d['quote']['USD']['price'] for d in data['data']['quotes']])
    
    # Calculate price changes
    delta = prices.diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)
    
    # Calculate average gains and losses
    avg_gains = gains.rolling(window=periods).mean()
    avg_losses = losses.rolling(window=periods).mean()
    
    # Calculate RS and RSI
    rs = avg_gains / avg_losses
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.iloc[-1]  # Return most recent RSI value

def write_results(current_price, rsi):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open('btc_analysis.txt', 'w') as f:
        f.write(f"Bitcoin Analysis - {timestamp}\n")
        f.write("-" * 50 + "\n")
        f.write(f"Current Price: ${current_price:,.2f}\n")
        f.write(f"14-day RSI: {rsi:.2f}\n")
        f.write("\nRSI Interpretation:\n")
        if rsi >= 70:
            f.write("Market is potentially overbought\n")
        elif rsi <= 30:
            f.write("Market is potentially oversold\n")
        else:
            f.write("Market is in neutral territory\n")

def main():
    # Fetch data
    data = get_cmc_data()
    if not data:
        return
    
    # Get current price
    current_price = data['data']['quotes'][-1]['quote']['USD']['price']
    
    # Calculate RSI
    rsi = calculate_rsi(data)
    
    # Write results
    write_results(current_price, rsi)
    print("Analysis complete. Results written to btc_analysis.txt")

if __name__ == "__main__":
    main() 