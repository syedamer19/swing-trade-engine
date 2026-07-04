import pandas as pd
import numpy as np

def calculate_rsi(df, period=14):
    """
    Calculate Relative Strength Index (RSI).
    """
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    
    # First values
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # Wilder's smoothing
    for i in range(period, len(df)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(df, period=20):
    """
    Calculate Exponential Moving Average (EMA).
    """
    return df['Close'].ewm(span=period, adjust=False).mean()

def calculate_macd(df, fast=12, slow=26, signal=9):
    """
    Calculate MACD Line, Signal Line and Histogram.
    """
    ema_fast = calculate_ema(df, fast)
    ema_slow = calculate_ema(df, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

def calculate_bollinger_bands(df, period=20, std_dev=2):
    """
    Calculate Bollinger Bands (Upper, Middle, Lower).
    """
    middle_band = df['Close'].rolling(window=period).mean()
    std = df['Close'].rolling(window=period).std()
    upper_band = middle_band + (std_dev * std)
    lower_band = middle_band - (std_dev * std)
    return upper_band, middle_band, lower_band

def is_hammer(open_p, high_p, low_p, close_p):
    """
    Detect Hammer/Pinbar Candlestick Pattern.
    """
    body = abs(close_p - open_p)
    candle_range = high_p - low_p
    if candle_range == 0:
        return False
        
    lower_shadow = min(open_p, close_p) - low_p
    upper_shadow = high_p - max(open_p, close_p)
    
    # Lower shadow should be at least 2 times the body size
    # Upper shadow should be very small (less than 10% of candle range)
    is_hammer_pattern = (lower_shadow >= 2 * body) and (upper_shadow <= 0.15 * candle_range) and (body > 0)
    return is_hammer_pattern

def is_bullish_engulfing(prev_open, prev_close, curr_open, curr_close):
    """
    Detect Bullish Engulfing Candlestick Pattern.
    """
    prev_is_red = prev_close < prev_open
    curr_is_green = curr_close > curr_open
    engulfs = (curr_close >= prev_open) and (curr_open <= prev_close)
    return prev_is_red and curr_is_green and engulfs

def scan_rsi_reversal(df, symbol):
    """
    Strategy 1: RSI Oversold & Reversal (RSI fell below 35 and crossed back above 35 recently).
    """
    if len(df) < 20:
        return None
        
    rsi = calculate_rsi(df, 14)
    df = df.copy()
    df['RSI'] = rsi
    
    # Look at last 5 candles
    recent_rsi = df['RSI'].tail(5).values
    recent_close = df['Close'].tail(5).values
    recent_low = df['Low'].tail(5).values
    
    # Check if RSI crossed above 35 from below in the last 2 days
    # (i.e. RSI[t-1] < 35 and RSI[t] >= 35) or similarly crossed recently
    triggered = False
    trigger_idx = -1
    
    # Scan back starting from today (index -1)
    for i in range(-1, -4, -1):
        prev_rsi = df['RSI'].iloc[i-1]
        curr_rsi = df['RSI'].iloc[i]
        if prev_rsi < 35 and curr_rsi >= 35:
            triggered = True
            trigger_idx = i
            break
            
    if triggered:
        entry_price = round(df['Close'].iloc[-1], 2)
        # Stop loss at lowest low of last 5 days
        stop_loss = round(df['Low'].tail(5).min(), 2)
        risk = entry_price - stop_loss
        
        if risk <= 0:
            risk = entry_price * 0.02  # fallback 2% SL
            stop_loss = round(entry_price - risk, 2)
            
        target_price = round(entry_price + (2 * risk), 2)
        # Ensure at least 5% target
        min_target = round(entry_price * 1.05, 2)
        if target_price < min_target:
            target_price = min_target
            
        rr_ratio = round((target_price - entry_price) / (entry_price - stop_loss), 2)
        
        return {
            "Symbol": symbol,
            "Strategy": "RSI Reversal",
            "Details": f"RSI was oversold and crossed back above 35 (Current RSI: {round(df['RSI'].iloc[-1], 2)})",
            "Entry": entry_price,
            "StopLoss": stop_loss,
            "Target": target_price,
            "RiskReward": rr_ratio,
            "LTP": entry_price
        }
    return None

def scan_ema_pullback(df, symbol):
    """
    Strategy 2: EMA Pullback (Strong uptrend 20 EMA > 50 EMA > 200 EMA, and price pulls back to 20/50 EMA).
    """
    if len(df) < 200:
        return None
        
    df = df.copy()
    df['EMA20'] = calculate_ema(df, 20)
    df['EMA50'] = calculate_ema(df, 50)
    df['EMA200'] = calculate_ema(df, 200)
    
    # Check trend confirmation: 20 EMA > 50 EMA > 200 EMA
    curr_ema20 = df['EMA20'].iloc[-1]
    curr_ema50 = df['EMA50'].iloc[-1]
    curr_ema200 = df['EMA200'].iloc[-1]
    
    in_uptrend = curr_ema20 > curr_ema50 and curr_ema50 > curr_ema200
    if not in_uptrend:
        return None
        
    # Check if price pulled back to 20 EMA or 50 EMA in the last 2 days
    # i.e., Low was below or near the EMA, but Close was above or near the EMA.
    # Let's check for today and yesterday.
    triggered = False
    trigger_type = ""
    
    for i in range(-1, -3, -1):
        low = df['Low'].iloc[i]
        high = df['High'].iloc[i]
        close = df['Close'].iloc[i]
        open_p = df['Open'].iloc[i]
        ema20 = df['EMA20'].iloc[i]
        ema50 = df['EMA50'].iloc[i]
        
        # Pullback to 20 EMA zone (low is within 1% of or below 20 EMA, close is above 20 EMA)
        near_ema20 = (low <= ema20 * 1.01) and (close >= ema20 * 0.99)
        # Pullback to 50 EMA zone
        near_ema50 = (low <= ema50 * 1.01) and (close >= ema50 * 0.99)
        
        # Bullish reversal candle confirmation
        is_rev = is_hammer(open_p, high, low, close) or \
                 is_bullish_engulfing(df['Open'].iloc[i-1], df['Close'].iloc[i-1], open_p, close) or \
                 (close > open_p and close > df['Close'].iloc[i-1]) # strong green candle
                 
        if (near_ema20 or near_ema50) and is_rev:
            triggered = True
            trigger_type = "20 EMA" if near_ema20 else "50 EMA"
            break
            
    if triggered:
        entry_price = round(df['Close'].iloc[-1], 2)
        # Stop loss below the recent low (lowest low of last 3 days)
        stop_loss = round(df['Low'].tail(3).min() * 0.995, 2)
        risk = entry_price - stop_loss
        
        if risk <= 0:
            risk = entry_price * 0.015
            stop_loss = round(entry_price - risk, 2)
            
        target_price = round(entry_price + (2 * risk), 2)
        # Ensure minimum 5% target
        min_target = round(entry_price * 1.05, 2)
        if target_price < min_target:
            target_price = min_target
            
        rr_ratio = round((target_price - entry_price) / (entry_price - stop_loss), 2)
        
        return {
            "Symbol": symbol,
            "Strategy": "EMA Pullback",
            "Details": f"Pulled back to {trigger_type} in an uptrend with a bullish reversal candlestick.",
            "Entry": entry_price,
            "StopLoss": stop_loss,
            "Target": target_price,
            "RiskReward": rr_ratio,
            "LTP": entry_price
        }
    return None

def scan_macd_crossover(df, symbol):
    """
    Strategy 3: MACD Crossover (MACD line crosses above Signal line below zero).
    """
    if len(df) < 35:
        return None
        
    df = df.copy()
    macd_line, signal_line, macd_hist = calculate_macd(df)
    df['MACD'] = macd_line
    df['Signal'] = signal_line
    
    # Check crossover in last 2 days
    triggered = False
    for i in range(-1, -3, -1):
        prev_macd = df['MACD'].iloc[i-1]
        prev_sig = df['Signal'].iloc[i-1]
        curr_macd = df['MACD'].iloc[i]
        curr_sig = df['Signal'].iloc[i]
        
        # MACD crossed above Signal, and both are below 0 (oversold/reversal setup)
        if prev_macd < prev_sig and curr_macd >= curr_sig and curr_macd < 0:
            triggered = True
            break
            
    if triggered:
        entry_price = round(df['Close'].iloc[-1], 2)
        # Stop loss at lowest low of last 5 days
        stop_loss = round(df['Low'].tail(5).min(), 2)
        risk = entry_price - stop_loss
        
        if risk <= 0:
            risk = entry_price * 0.02
            stop_loss = round(entry_price - risk, 2)
            
        target_price = round(entry_price + (2 * risk), 2)
        min_target = round(entry_price * 1.05, 2)
        if target_price < min_target:
            target_price = min_target
            
        rr_ratio = round((target_price - entry_price) / (entry_price - stop_loss), 2)
        
        return {
            "Symbol": symbol,
            "Strategy": "MACD Crossover",
            "Details": f"MACD line crossed above Signal line below the zero axis (MACD: {round(df['MACD'].iloc[-1], 2)}).",
            "Entry": entry_price,
            "StopLoss": stop_loss,
            "Target": target_price,
            "RiskReward": rr_ratio,
            "LTP": entry_price
        }
    return None

def scan_bb_rebound(df, symbol):
    """
    Strategy 4: Bollinger Bands Rebound (Price closes below lower BB and rebounds back inside).
    """
    if len(df) < 25:
        return None
        
    df = df.copy()
    upper, middle, lower = calculate_bollinger_bands(df)
    df['LowerBB'] = lower
    df['MiddleBB'] = middle
    df['UpperBB'] = upper
    
    # Check if:
    # 1. Previous close was below/near lower BB (or previous low breached lower BB)
    # 2. Today's close is back inside the bands (above lower BB)
    prev_low = df['Low'].iloc[-2]
    prev_close = df['Close'].iloc[-2]
    prev_lower = df['LowerBB'].iloc[-2]
    
    curr_close = df['Close'].iloc[-1]
    curr_lower = df['LowerBB'].iloc[-1]
    curr_middle = df['MiddleBB'].iloc[-1]
    curr_upper = df['UpperBB'].iloc[-1]
    
    # Rebound condition
    breached_lower = prev_low <= prev_lower * 1.005 or prev_close <= prev_lower
    closed_inside = curr_close > curr_lower
    
    # Bullish candle today
    bullish_candle = curr_close > df['Open'].iloc[-1]
    
    if breached_lower and closed_inside and bullish_candle:
        entry_price = round(curr_close, 2)
        # Stop loss below the recent low
        stop_loss = round(df['Low'].tail(3).min() * 0.995, 2)
        risk = entry_price - stop_loss
        
        if risk <= 0:
            risk = entry_price * 0.02
            stop_loss = round(entry_price - risk, 2)
            
        # Target 1 is Middle Band, Target 2 is Upper Band. Let's use 1:2 R:R or Middle Band, whichever is higher
        target_price = round(max(curr_middle, entry_price + (2 * risk)), 2)
        min_target = round(entry_price * 1.05, 2)
        if target_price < min_target:
            target_price = min_target
            
        rr_ratio = round((target_price - entry_price) / (entry_price - stop_loss), 2)
        
        return {
            "Symbol": symbol,
            "Strategy": "BB Rebound",
            "Details": f"Low breached lower Bollinger Band ({round(curr_lower, 2)}) and closed back inside.",
            "Entry": entry_price,
            "StopLoss": stop_loss,
            "Target": target_price,
            "RiskReward": rr_ratio,
            "LTP": entry_price
        }
    return None

def run_all_strategies(df, symbol):
    """
    Run all swing trading strategies on the data and return matches.
    """
    opportunities = []
    
    # Run strategies
    res_rsi = scan_rsi_reversal(df, symbol)
    if res_rsi:
        opportunities.append(res_rsi)
        
    res_ema = scan_ema_pullback(df, symbol)
    if res_ema:
        opportunities.append(res_ema)
        
    res_macd = scan_macd_crossover(df, symbol)
    if res_macd:
        opportunities.append(res_macd)
        
    res_bb = scan_bb_rebound(df, symbol)
    if res_bb:
        opportunities.append(res_bb)
        
    return opportunities
