import os
import urllib.request
import pandas as pd
import io
import time
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Kotak Neo API settings
KOTAK_CONSUMER_KEY = os.getenv("KOTAK_CONSUMER_KEY", "")
KOTAK_MOBILE = os.getenv("KOTAK_MOBILE", "")
KOTAK_UCC = os.getenv("KOTAK_UCC", "")
KOTAK_MPIN = os.getenv("KOTAK_MPIN", "")
KOTAK_TOTP_SECRET = os.getenv("KOTAK_TOTP_SECRET", "")
KOTAK_ENV = os.getenv("KOTAK_ENV", "prod")  # default to prod

# Directory for caching downloads
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Baseline hardcoded lists (Fallbacks if NSE download fails)
FALLBACK_WATCHLISTS = {
    "Nifty 50 (Top Liquid)": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "BHARTIARTL.NS", "SBIN.NS", "LICI.NS", "ITC.NS", "HINDUNILVR.NS",
        "LT.NS", "BAJFINANCE.NS", "HCLTECH.NS", "MARUTI.NS", "SUNPHARMA.NS",
        "ADANIENT.NS", "KOTAKBANK.NS", "AXISBANK.NS", "TITAN.NS", "ULTRACEMCO.NS",
        "ASIANPAINT.NS", "NTPC.NS", "COALINDIA.NS", "POWERGRID.NS", "TATASTEEL.NS",
        "M&M.NS", "ADANIPORTS.NS", "JSWSTEEL.NS", "ONGC.NS", "TATAMOTORS.NS",
        "HINDALCO.NS", "SBILIFE.NS", "GRASIM.NS", "NESTLEIND.NS", "TECHM.NS",
        "CIPLA.NS", "BRITANNIA.NS", "EICHERMOT.NS", "WIPRO.NS", "ADANIPOWER.NS",
        "BAJAJFINSV.NS", "INDUSINDBK.NS", "BPCL.NS", "ApolloHosp.NS", "TATACONSUM.NS",
        "SHRIRAMFIN.NS", "HEROMOTOCO.NS", "DRREDDY.NS", "HDFCLIFE.NS", "DIVISLAB.NS"
    ],
    "Nifty IT": [
        "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS",
        "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS", "KPITTECH.NS", "MPHASIS.NS"
    ],
    "Nifty Bank": [
        "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
        "INDUSINDBK.NS", "PNB.NS", "BOB.NS", "FEDERALBNK.NS", "AUBANK.NS",
        "IDFCFIRSTB.NS", "BANDHANBNK.NS"
    ]
}

NSE_URLS = {
    "Nifty 50 (Top Liquid)": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "Nifty 100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "Nifty 200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"
}

def load_index_from_nse(name, url):
    """
    Downloads the constituent list of an index from the NSE website.
    Caches it locally for up to 7 days to avoid network latency during UI rendering.
    """
    clean_name = "".join(x for x in name if x.isalnum()).lower()
    cache_path = os.path.join(CACHE_DIR, f"{clean_name}.txt")
    
    # Check if cache is fresh (less than 7 days old)
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        age_days = (time.time() - mtime) / (24 * 3600)
        if age_days < 7:
            try:
                with open(cache_path, "r") as f:
                    symbols = [line.strip() for line in f if line.strip()]
                if len(symbols) > 5:
                    return symbols
            except Exception as e:
                logger.warning(f"Error reading cache for {name}: {e}")

    # Fetch from internet
    logger.info(f"Downloading {name} list from NSE...")
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            csv_data = response.read()
            df = pd.read_csv(io.BytesIO(csv_data))
            if "Symbol" in df.columns:
                symbols = [f"{sym}.NS" for sym in df["Symbol"].tolist() if isinstance(sym, str)]
                # Save to cache
                with open(cache_path, "w") as f:
                    for sym in symbols:
                        f.write(f"{sym}\n")
                logger.info(f"Cached {len(symbols)} symbols for {name}")
                return symbols
    except Exception as e:
        logger.error(f"Failed to fetch {name} from NSE: {e}. Falling back to default list.")
        
    # Return fallback if exists, else return empty list
    return FALLBACK_WATCHLISTS.get(name, FALLBACK_WATCHLISTS["Nifty 50 (Top Liquid)"])

# Watchlists dict containing dynamic and static lists
WATCHLISTS = {}

# Load lists (runs on import, but uses local cache if fresh to prevent delay)
for name, url in NSE_URLS.items():
    WATCHLISTS[name] = load_index_from_nse(name, url)

# Add static fallbacks that don't have direct NSE URLs in our dictionary
WATCHLISTS["Nifty IT"] = FALLBACK_WATCHLISTS["Nifty IT"]
WATCHLISTS["Nifty Bank"] = FALLBACK_WATCHLISTS["Nifty Bank"]

def get_clean_symbol(yfinance_ticker):
    """
    Converts Yahoo Finance ticker (e.g. RELIANCE.NS) to Kotak symbol (e.g. RELIANCE)
    """
    if yfinance_ticker.endswith(".NS"):
        return yfinance_ticker[:-3]
    elif yfinance_ticker.endswith(".BO"):
        return yfinance_ticker[:-3]
    return yfinance_ticker
