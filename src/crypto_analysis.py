import aiohttp
import asyncio
import json
import os
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CACHE_FILE = 'crypto_cache.json'
CACHE_EXPIRY = 3600  # 1 hour in seconds
BATCH_SIZE = 100  # Maximum allowed by the API

class CryptoCache:
    def __init__(self):
        self.cache = self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    cache_data = json.load(f)
                    if 'quotes' not in cache_data:
                        cache_data['quotes'] = {}
                    if 'timestamp' not in cache_data:
                        cache_data['timestamp'] = {}
                    return cache_data
        except Exception as e:
            print(f"Error loading cache: {e}")
        return {'quotes': {}, 'timestamp': {}}

    def save_cache(self):
        try:
            with open(CACHE_FILE, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def is_valid(self, key, data_type):
        try:
            timestamp = self.cache.get('timestamp', {}).get(key)
            if not timestamp:
                return False
            age = datetime.now() - datetime.fromisoformat(timestamp)
            return age.total_seconds() < CACHE_EXPIRY
        except Exception:
            return False

    def get(self, key, data_type):
        try:
            if self.is_valid(key, data_type):
                return self.cache[data_type].get(key)
        except Exception:
            pass
        return None

    def set(self, key, data_type, value):
        try:
            if data_type not in self.cache:
                self.cache[data_type] = {}
            self.cache[data_type][key] = value
            if 'timestamp' not in self.cache:
                self.cache['timestamp'] = {}
            self.cache['timestamp'][key] = datetime.now().isoformat()
            self.save_cache()
        except Exception as e:
            print(f"Error setting cache: {e}")

async def get_batch_quotes(session, symbols, api_key, cache):
    """Get latest quotes for multiple symbols in one call"""
    cache_key = ','.join(sorted(symbols))
    cached_data = cache.get(cache_key, 'quotes')
    if cached_data:
        return cached_data

    headers = {
        'X-CMC_PRO_API_KEY': api_key,
        'Accept': 'application/json'
    }
    params = {'symbol': ','.join(symbols), 'convert': 'USD'}

    try:
        async with session.get(
            'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest',
            headers=headers,
            params=params
        ) as response:
            if response.status == 429:
                print("Rate limited, waiting 10s...")
                await asyncio.sleep(10)
                return None
                
            data = await response.json()
            if response.status == 200 and data.get('status', {}).get('error_code') == 0:
                cache.set(cache_key, 'quotes', data)
                return data
            else:
                error_msg = data.get('status', {}).get('error_message', 'Unknown error')
                print(f"API Error: {error_msg}")
                return None
    except Exception as e:
        print(f"Request error: {e}")
        return None

async def process_all_tickers(tickers):
    """Process all tickers with optimized batch processing"""
    start_time = datetime.now()
    api_calls = 0
    
    api_key = os.getenv('CMC_API_KEY')
    if not api_key:
        raise ValueError("No CMC_API_KEY found in environment variables")

    cache = CryptoCache()
    results = {}
    failed_tokens = []
    
    # Normalize symbols
    tickers = [t.upper() for t in tickers]
    
    async with aiohttp.ClientSession() as session:
        # Process quotes in large batches
        for i in range(0, len(tickers), BATCH_SIZE):
            batch = tickers[i:i + BATCH_SIZE]
            print(f"\nProcessing batch {i//BATCH_SIZE + 1}/{(len(tickers) + BATCH_SIZE - 1)//BATCH_SIZE}")
            
            # Try up to 3 times for each batch
            for retry in range(3):
                quote_data = await get_batch_quotes(session, batch, api_key, cache)
                api_calls += 1
                
                if quote_data and 'data' in quote_data:
                    break
                    
                if retry < 2:
                    print(f"Retrying batch {i//BATCH_SIZE + 1} (attempt {retry + 2}/3)")
                    await asyncio.sleep(2 ** retry)  # Exponential backoff
            
            if not quote_data or 'data' not in quote_data:
                print(f"Failed to get quotes for batch {i//BATCH_SIZE + 1}")
                continue
            
            # Process each token in the batch
            for symbol in batch:
                try:
                    token_data = quote_data['data'].get(symbol, [])
                    if token_data and len(token_data) > 0:
                        quote = token_data[0].get('quote', {}).get('USD', {})
                        price = quote.get('price')
                        percent_change_24h = quote.get('percent_change_24h', 0)
                        percent_change_7d = quote.get('percent_change_7d', 0)
                        volume_24h = quote.get('volume_24h', 0)
                        market_cap = quote.get('market_cap', 0)
                        
                        if price and price > 0:
                            # Calculate a simple momentum score based on price changes and volume
                            momentum_score = (
                                0.5 * percent_change_24h +  # 50% weight to 24h change
                                0.3 * percent_change_7d +   # 30% weight to 7d change
                                0.2 * (volume_24h / market_cap * 100 if market_cap > 0 else 0)  # 20% weight to volume/market cap ratio
                            )
                            
                            results[symbol] = (momentum_score, price)
                            print(f"Successfully processed {symbol}: Momentum={momentum_score:.2f}, Price=${price:,.8f}")
                        else:
                            print(f"Invalid price for {symbol}: {price}")
                            failed_tokens.append(symbol)
                    else:
                        print(f"No data found for {symbol}")
                        failed_tokens.append(symbol)
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
                    failed_tokens.append(symbol)
            
            await asyncio.sleep(0.1)  # Small delay between batches
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"\nPerformance Metrics:")
    print(f"Total time: {duration:.2f} seconds")
    print(f"Total API calls: {api_calls}")
    print(f"Tokens processed: {len(results)}")
    print(f"Failed tokens: {len(set(failed_tokens))}")
    
    return results, duration, api_calls

def write_results(results):
    """Write results with improved formatting"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open('crypto_analysis.txt', 'w') as f:
        f.write(f"Cryptocurrency Analysis - {timestamp}\n")
        f.write("=" * 50 + "\n\n")
        
        # Sort by momentum score
        sorted_results = sorted(
            [(k, v) for k, v in results.items()],
            key=lambda x: x[1][0],
            reverse=True
        )
        
        for symbol, (momentum, price) in sorted_results:
            f.write(f"{symbol}:\n")
            f.write(f"Current Price: ${price:,.8f}\n")
            f.write(f"Momentum Score: {momentum:.2f}\n")
            f.write("-" * 30 + "\n")
        
        f.write(f"\nTotal tokens analyzed: {len(results)}")

async def main():
    tickers = [line.strip() for line in open('current_tickers.txt') if line.strip()]
    print(f"Processing {len(tickers)} tickers...")
    
    results, duration, api_calls = await process_all_tickers(tickers)
    write_results(results)
    print("\nAnalysis complete. Results written to crypto_analysis.txt")

if __name__ == "__main__":
    asyncio.run(main()) 