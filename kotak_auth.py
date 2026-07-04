import time
import pyotp
import logging
from neo_api_client import NeoAPI
import config

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class KotakNeoSession:
    def __init__(self, consumer_key=None, mobile=None, ucc=None, mpin=None, totp_secret=None):
        self.consumer_key = consumer_key or config.KOTAK_CONSUMER_KEY
        self.mobile = mobile or config.KOTAK_MOBILE
        self.ucc = ucc or config.KOTAK_UCC
        self.mpin = mpin or config.KOTAK_MPIN
        self.totp_secret = totp_secret or config.KOTAK_TOTP_SECRET
        self.client = None
        self.is_authenticated = False

    def generate_totp(self):
        """
        Generates 6-digit TOTP code using the secret key if configured.
        """
        if not self.totp_secret:
            logger.warning("TOTP secret key is not configured. Automated login will not work.")
            return None
        try:
            totp = pyotp.TOTP(self.totp_secret.replace(" ", ""))
            return totp.now()
        except Exception as e:
            logger.error(f"Error generating TOTP: {e}")
            return None

    def login(self, manual_totp=None):
        """
        Authenticates with Kotak Neo API using a two-step flow.
        """
        if not self.consumer_key or not self.mobile or not self.ucc or not self.mpin:
            error_msg = "Missing Kotak credentials. Please check your configuration."
            logger.error(error_msg)
            return False, error_msg

        try:
            logger.info("Initializing NeoAPI client...")
            self.client = NeoAPI(environment=config.KOTAK_ENV, consumer_key=self.consumer_key)

            # Get TOTP (automated or manual)
            totp_code = manual_totp
            if not totp_code:
                totp_code = self.generate_totp()

            if not totp_code:
                return False, "TOTP code is required for login."

            logger.info("Step 1: Performing TOTP Login...")
            # Kotak Neo API totp_login takes mobile_number, ucc, and totp
            login_response = self.client.totp_login(
                mobile_number=self.mobile,
                ucc=self.ucc,
                totp=totp_code
            )
            logger.info(f"TOTP Login response: {login_response}")

            # Note: Depending on SDK version, login_response could indicate success or failure.
            # We proceed to validate with MPIN
            logger.info("Step 2: Validating session with MPIN...")
            validate_response = self.client.totp_validate(mpin=self.mpin)
            logger.info(f"MPIN Validation response: {validate_response}")

            self.is_authenticated = True
            return True, "Authenticated successfully"

        except Exception as e:
            self.is_authenticated = False
            error_msg = f"Login failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def get_holdings(self):
        """
        Retrieves current portfolio holdings from Kotak Neo.
        """
        if not self.is_authenticated or not self.client:
            return None, "Not authenticated"
        try:
            holdings = self.client.holdings()
            return holdings, None
        except Exception as e:
            logger.error(f"Failed to fetch holdings: {e}")
            return None, str(e)

    def get_positions(self):
        """
        Retrieves current open positions from Kotak Neo.
        """
        if not self.is_authenticated or not self.client:
            return None, "Not authenticated"
        try:
            positions = self.client.positions()
            return positions, None
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return None, str(e)

    def get_ltp(self, clean_symbol, exchange_segment="nse_cm"):
        """
        Retrieves the Last Traded Price (LTP) or quote for a symbol.
        Note: We need the instrument token, which is usually obtained from a scrip master search.
        In this implementation, we search the instrument or query standard quotes.
        """
        if not self.is_authenticated or not self.client:
            return None, "Not authenticated"
        try:
            # Let's search scrip to find the token
            # Official SDK supports searching: client.search_scrip(exchange_segment, symbol)
            # Let's try searching first to get instrument token.
            search_res = self.client.search_scrip(exchange_segment=exchange_segment, symbol=clean_symbol)
            if search_res and isinstance(search_res, list) and len(search_res) > 0:
                # Find exact match
                scrip_token = None
                for item in search_res:
                    # Let's match the trading symbol
                    if item.get("pSymbol", "").upper() == clean_symbol.upper() or item.get("pSymbolName", "").upper() == clean_symbol.upper():
                        scrip_token = item.get("pToken")
                        break
                
                # If no exact match found, use first item
                if not scrip_token:
                    scrip_token = search_res[0].get("pToken")

                if scrip_token:
                    quote = self.client.quote(instrument_token=scrip_token, exchange_segment=exchange_segment)
                    return quote, None
            return None, f"Symbol {clean_symbol} not found in exchange segment {exchange_segment}."
        except Exception as e:
            logger.error(f"Failed to fetch LTP for {clean_symbol}: {e}")
            return None, str(e)

    def place_swing_order(self, symbol, quantity, transaction_type, order_type="LIMIT", price=None, product="CNC"):
        """
        Places a delivery/swing trade order.
        transaction_type: 'BUY' or 'SELL'
        product: CNC (Cash & Carry) or MIS (Intraday)
        """
        if not self.is_authenticated or not self.client:
            return None, "Not authenticated"
        try:
            # Clean Yahoo Finance symbol to Kotak symbol (e.g. RELIANCE.NS -> RELIANCE)
            clean_sym = config.get_clean_symbol(symbol)
            # Find token
            search_res = self.client.search_scrip(exchange_segment="nse_cm", symbol=clean_sym)
            if not search_res:
                return None, f"Symbol {clean_sym} not found."
            
            token = search_res[0].get("pToken")
            
            # Place order using SDK parameters
            # Typical place_order call signature:
            # client.place_order(
            #     trading_symbol=clean_sym, exchange_segment="nse_cm", transaction_type=transaction_type,
            #     quantity=str(quantity), price=str(price) if price else "0", order_type=order_type,
            #     product_type=product, duration="DAY"
            # )
            order_res = self.client.place_order(
                trading_symbol=clean_sym,
                exchange_segment="nse_cm",
                transaction_type=transaction_type,
                quantity=str(quantity),
                price=str(price) if price else "0",
                order_type=order_type,
                product_type=product,
                duration="DAY",
                instrument_token=token
            )
            return order_res, None
        except Exception as e:
            logger.error(f"Failed to place order for {symbol}: {e}")
            return None, str(e)
