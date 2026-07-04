import pandas as pd
import logging
import concurrent.futures
import requests
import datetime
import strategies
import config

logger = logging.getLogger(__name__)

def fetch_historical_data(ticker, period="2y", interval="1d"):
    """
    Downloads historical data directly from Yahoo Finance raw chart API to bypass rate limits.
    """
    try:
        # Construct range parameter
        # yfinance period format maps directly to range format
        # standard daily period is 2y
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval={interval}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }
        
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code != 200:
            logger.warning(f"Yahoo chart API returned status code {response.status_code} for {ticker}")
            return None
            
        data = response.json()
        result = data.get("chart", {}).get("result")
        if not result:
            logger.warning(f"No result returned in chart API for {ticker}: {data.get('chart', {}).get('error')}")
            return None
            
        res = result[0]
        timestamps = res.get("timestamp", [])
        quote = res.get("indicators", {}).get("quote", [{}])[0]
        
        if not timestamps or not quote:
            logger.warning(f"Empty timestamp or quote indicator arrays for {ticker}")
            return None
            
        # Parse timestamp to date objects
        dates = [datetime.date.fromtimestamp(ts) for ts in timestamps]
        
        df = pd.DataFrame({
            "Date": dates,
            "Open": quote.get("open", []),
            "High": quote.get("high", []),
            "Low": quote.get("low", []),
            "Close": quote.get("close", []),
            "Volume": quote.get("volume", [])
        })
        
        # Standardize and drop incomplete data rows
        df = df.dropna(subset=["Close", "Open", "High", "Low"])
        df = df.reset_index(drop=True)
        
        # Ensure we have minimum number of candles for analysis
        if len(df) < 50:
            logger.warning(f"Insufficient data points ({len(df)}) returned for {ticker}")
            return None
            
        return df
    except Exception as e:
        logger.error(f"Error fetching direct data for {ticker}: {e}")
        return None

def update_with_kotak_ltp(df, symbol, kotak_session):
    """
    If Kotak Neo API is connected, fetch the live LTP and update/append the latest price to the dataframe.
    This enables real-time scanning during market hours.
    """
    if not kotak_session or not kotak_session.is_authenticated:
        return df

    try:
        clean_sym = config.get_clean_symbol(symbol)
        quote, err = kotak_session.get_ltp(clean_sym)
        if err or not quote:
            return df
            
        # Extract LTP from quote response
        # Official Kotak quote response structure usually has 'ltp' or similar field in payload.
        # Let's inspect typical keys or assume standard: quote.get("lastPrice") or quote.get("ltp")
        # Let's check for common quote fields: 'lastPrice', 'ltp', 'buyPrice', 'close'
        ltp = None
        if isinstance(quote, dict):
            # Sometimes quote returns a dict inside a list or nested structure
            # e.g., {'stat': 'Ok', 'data': {'ltp': '2430.5', ...}}
            # or directly key values. Let's look for common ones:
            data = quote.get("data", quote)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            if isinstance(data, dict):
                ltp = data.get("ltp") or data.get("lastPrice") or data.get("closePrice") or data.get("close")
                
        if ltp is not None:
            ltp = float(ltp)
            # Check if today's date is already the last row in df
            # If so, update the Close/LTP. If not, append a new row.
            today_date = pd.Timestamp.now().normalize()
            last_row_date = pd.to_datetime(df['Date'].iloc[-1]).normalize()
            
            if last_row_date == today_date:
                df.loc[df.index[-1], 'Close'] = ltp
                # We can also update high/low if the current LTP exceeds them
                if ltp > df.loc[df.index[-1], 'High']:
                    df.loc[df.index[-1], 'High'] = ltp
                if ltp < df.loc[df.index[-1], 'Low']:
                    df.loc[df.index[-1], 'Low'] = ltp
            else:
                # Append a new row for today
                new_row = {
                    "Date": today_date,
                    "Open": ltp,
                    "High": ltp,
                    "Low": ltp,
                    "Close": ltp,
                    "Volume": 0
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                
    except Exception as e:
        logger.error(f"Failed to update LTP from Kotak for {symbol}: {e}")
        
    return df

def scan_single_symbol(symbol, kotak_session=None):
    """
    Downloads data for a single symbol, updates with live LTP if available,
    and runs all strategies.
    """
    df = fetch_historical_data(symbol)
    if df is None:
        return []
        
    # Update with Kotak LTP if available
    df = update_with_kotak_ltp(df, symbol, kotak_session)
    
    # Run strategies
    return strategies.run_all_strategies(df, symbol)

def run_scanner(watchlist_name, kotak_session=None, max_workers=10):
    """
    Runs the swing scanner on a selected watchlist using concurrency.
    """
    tickers = config.WATCHLISTS.get(watchlist_name, [])
    if not tickers:
        logger.error(f"Watchlist {watchlist_name} not found or empty.")
        return []
        
    all_opportunities = []
    
    # Run scan using concurrent futures for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Map tickers to scan function
        future_to_ticker = {executor.submit(scan_single_symbol, ticker, kotak_session): ticker for ticker in tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    all_opportunities.extend(result)
            except Exception as exc:
                logger.error(f"Scanner generated an exception for {ticker}: {exc}")
                
    return all_opportunities
