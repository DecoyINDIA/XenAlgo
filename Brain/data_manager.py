import os
import time
import logging
import datetime
import urllib.request
import io
import duckdb
import pandas as pd
import numpy as np
import requests
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("QuantPlatform.DataManager")

class DataManager:
    """
    Manages historical market data downloads, local caching in DuckDB, 
    and panel data loading for backtesting.
    """
    def __init__(self, config: dict):
        self.config = config
        self.db_path = config["database"]["db_path"]
        self.data_dir = config["database"]["data_dir"]
        
        # Ensure database and data directories exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.client_id = config["dhan"]["client_id"]
        self.access_token = config["dhan"]["access_token"]
        self.scrip_master_url = config["dhan"]["scrip_master_url"]
        self.nifty200_url = config["dhan"]["nifty200_url"]
        self.nifty500_url = config["dhan"]["nifty500_url"]
        
        # Determine if we should run in synthetic mode
        self.is_synthetic = (
            self.client_id == "YOUR_DHAN_CLIENT_ID" 
            or self.access_token == "YOUR_DHAN_ACCESS_TOKEN"
            or not self.client_id 
            or not self.access_token
        )
        
        if self.is_synthetic:
            logger.warning("Dhan API credentials not configured. Running in SYNTHETIC DATA MODE.")
            
        self.conn = duckdb.connect(self.db_path)

        # Ensure the daily_ohlcv table exists
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_ohlcv (
                symbol VARCHAR,
                date DATE,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                security_id VARCHAR,
                UNIQUE(symbol, date)
            )
        """)

    def close(self):
        """Close connection to DuckDB."""
        if self.conn:
            self.conn.close()

    def get_nse200_universe(self) -> List[str]:
        """
        Fetch the Nifty 200 symbol list from NSE, falling back to a static list if offline.
        """
        logger.info("Fetching Nifty 200 universe...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
        }

        try:
            req = urllib.request.Request(self.nifty200_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))

            if 'Symbol' in df.columns:
                symbols = df['Symbol'].str.strip().tolist()
                logger.info(f"Successfully loaded {len(symbols)} symbols from Nifty 200 CSV.")
                return symbols
        except Exception as e:
            logger.warning(f"Failed to fetch Nifty 200 list from NSE: {e}. Using fallback universe.")

        # Fallback universe of major NSE symbols
        fallback_symbols = [
            "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC", "SBI", "BHARTIARTL", "LT",
            "KOTAKBANK", "AXISBANK", "ASIANPAINT", "BAJFINANCE", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "ADANIENT", "JSWSTEEL",
            "HINDALCO", "TATASTEEL", "POWERGRID", "NTPC", "ONGC", "COALINDIA", "ADANIPORTS", "GRASIM", "BAJAJFINSV", "WIPRO",
            "TECHM", "M&M", "INDUSINDBK", "SBILIFE", "HDFCLIFE", "DIVISLAB", "CIPLA", "EICHERMOT", "BRITANNIA", "BPCL",
            "TATACONSUM", "NESTLEIND", "DRREDDY", "APOLLOHOSP", "HEROMOTOCO", "BAJAJ-AUTO", "UPL", "TATAMOTORS", "SBIN", "TRENT"
        ]
        return fallback_symbols

    def get_nse500_universe(self) -> List[str]:
        """
        Fetch the Nifty 500 symbol list from NSE, falling back to Nifty 200 if offline.
        """
        logger.info("Fetching Nifty 500 universe...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
        }
        try:
            req = urllib.request.Request(self.nifty500_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
            if 'Symbol' in df.columns:
                symbols = df['Symbol'].str.strip().tolist()
                logger.info(f"Successfully loaded {len(symbols)} symbols from Nifty 500 CSV.")
                return symbols
        except Exception as e:
            logger.warning(f"Failed to fetch Nifty 500 list: {e}. Falling back to Nifty 200.")
        return self.get_nse200_universe()

    def download_scrip_master(self) -> pd.DataFrame:
        """
        Downloads the compact scrip master from Dhan to map NSE symbols to security IDs.
        """
        logger.info("Downloading Dhan scrip master...")
        local_scrip_file = os.path.join(self.data_dir, "api-scrip-master.csv")
        
        # Check if cache is fresh (less than 24 hours old)
        if os.path.exists(local_scrip_file):
            mtime = os.path.getmtime(local_scrip_file)
            if time.time() - mtime < 86400: # 1 day
                logger.info("Using cached Dhan scrip master.")
                return pd.read_csv(local_scrip_file, low_memory=False)
                
        try:
            # Download file
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(self.scrip_master_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read()
            with open(local_scrip_file, 'wb') as f:
                f.write(content)
            logger.info("Dhan scrip master downloaded and cached.")
            return pd.read_csv(local_scrip_file, low_memory=False)
        except Exception as e:
            logger.error(f"Failed to download Dhan scrip master: {e}")
            if os.path.exists(local_scrip_file):
                logger.info("Using expired cached scrip master as fallback.")
                return pd.read_csv(local_scrip_file, low_memory=False)
            raise RuntimeError("Scrip master download failed and no cache is available.") from e

    def build_security_mapping(self, symbols: List[str]) -> Dict[str, Tuple[str, str]]:
        """
        Maps symbols to (security_id, instrument_type) using the scrip master.
        Returns: { 'TCS': ('1333', 'EQUITY'), ... }
        """
        if self.is_synthetic:
            # Mock mapping
            return {sym: (str(1000 + idx), "EQUITY") for idx, sym in enumerate(symbols)}
            
        try:
            df = self.download_scrip_master()
            # Filter for NSE segment & Equity type
            # Standard columns in compact scrip master:
            # SEM_EXM_EXCH_ID (NSE), SEM_SEGMENT (E for Equity), SEM_TRADING_SYMBOL, SEM_SM_ID, SEM_INSTRUMENT_NAME
            # Let's clean up columns
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Map NSE Equity segment
            mask = (df['SEM_EXM_EXCH_ID'].astype(str).str.strip().str.upper() == 'NSE') & \
                   (df['SEM_SEGMENT'].astype(str).str.strip().str.upper() == 'E')
            
            nse_df = df[mask]
            
            mapping = {}
            for _, row in nse_df.iterrows():
                symbol = str(row['SEM_TRADING_SYMBOL']).strip()
                sec_id = str(int(row['SEM_SMST_SECURITY_ID']) if pd.notna(row['SEM_SMST_SECURITY_ID']) else row['SEM_SMST_SECURITY_ID']).strip()
                inst_name = str(row.get('SEM_INSTRUMENT_NAME', 'EQUITY')).strip()
                mapping[symbol] = (sec_id, inst_name)
                
            # Filter mapping to only include our universe symbols
            universe_mapping = {}
            for sym in symbols:
                if sym in mapping:
                    universe_mapping[sym] = mapping[sym]
                else:
                    # Keep symbol but mark with a mock ID for safety if not found
                    universe_mapping[sym] = (f"MOCK_{sym}", "EQUITY")
                    
            return universe_mapping
        except Exception as e:
            logger.error(f"Error building security mapping: {e}. Falling back to mock mapping.")
            return {sym: (str(1000 + idx), "EQUITY") for idx, sym in enumerate(symbols)}

    def fetch_dhan_historical(
        self, security_id: str, exchange_segment: str, instrument: str, from_date: str, to_date: str
    ) -> Optional[pd.DataFrame]:
        """
        Sends a direct HTTP POST request to the Dhan historical charts API.
        Implements rate-limiting retries and returns a parsed DataFrame.
        """
        url = "https://api.dhan.co/v2/charts/historical"
        headers = {
            "client-id": self.client_id,
            "access-token": self.access_token,
            "Content-Type": "application/json"
        }
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument,
            "fromDate": from_date,
            "toDate": to_date
        }

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                # Direct API call
                response = requests.post(url, json=payload, headers=headers, timeout=15)

                # Check for rate-limiting
                if response.status_code == 429:
                    logger.warning(f"Rate limited (429) for security {security_id}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue

                response.raise_for_status()
                res_data = response.json()

                if not res_data or 'open' not in res_data:
                    # Dhan API might return a container under 'data' or directly
                    if 'data' in res_data:
                        res_data = res_data['data']
                    else:
                        logger.warning(f"Invalid response format for security {security_id}: {res_data}")
                        return None

                # Check again if we have the arrays
                if 'open' not in res_data or len(res_data['open']) == 0:
                    return None

                # Parse the arrays: open, high, low, close, volume, timestamp
                df = pd.DataFrame({
                    "open": res_data["open"],
                    "high": res_data["high"],
                    "low": res_data["low"],
                    "close": res_data["close"],
                    "volume": res_data["volume"],
                    "timestamp": res_data["timestamp"]
                })

                # Convert timestamps (seconds since 1970)
                df['date'] = pd.to_datetime(df['timestamp'], unit='s').dt.date
                df.drop(columns=['timestamp'], inplace=True, errors='ignore')
                return df

            except Exception as e:
                logger.error(f"Error calling Dhan API for security {security_id} (Attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(backoff)
                backoff *= 2.0

        return None

    def generate_synthetic_ohlcv(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Generates high-quality synthetic daily OHLCV data using a geometric Brownian motion model.
        Used as a fallback when credentials aren't provided or the Dhan API fails.
        """
        # Parse dates
        start = pd.to_datetime(start_date).date()
        end = pd.to_datetime(end_date).date()
        
        # Generate trading calendar (weekdays)
        date_range = pd.date_range(start=start, end=end, freq='B')
        n_days = len(date_range)
        
        if n_days == 0:
            return pd.DataFrame()
            
        # Deterministic seed based on symbol name to make data reproducible
        seed = sum(ord(char) for char in symbol) % 2**32
        np.random.seed(seed)
        
        # Parameters for GBM: drift (mu) and volatility (sigma)
        mu = np.random.uniform(0.05, 0.20) / 252.0  # 5% to 20% annual drift
        sigma = np.random.uniform(0.15, 0.40) / np.sqrt(252) # 15% to 40% annual vol
        
        # Starting price based on symbol seed
        start_price = np.random.uniform(50.0, 2000.0)
        
        # Simulated log returns
        returns = np.random.normal(mu, sigma, n_days)
        price_path = start_price * np.exp(np.cumsum(returns))
        
        # Generate open, high, low, close, volume
        # Daily high/low from daily vol approximation
        daily_vol = np.random.uniform(0.01, 0.03, n_days)
        
        close_prices = price_path
        open_prices = np.zeros(n_days)
        high_prices = np.zeros(n_days)
        low_prices = np.zeros(n_days)
        
        prev_close = start_price
        for i in range(n_days):
            # Open is close to previous close with a small gap
            gap_return = np.random.normal(0, 0.003)
            open_prices[i] = prev_close * np.exp(gap_return)
            
            # High & Low
            h_ret = np.abs(np.random.normal(0.005, daily_vol[i]))
            l_ret = np.abs(np.random.normal(0.005, daily_vol[i]))
            
            high_prices[i] = max(open_prices[i], close_prices[i]) * (1 + h_ret)
            low_prices[i] = min(open_prices[i], close_prices[i]) * (1 - l_ret)
            prev_close = close_prices[i]
            
        # Volume: lognormal distribution with correlation to price movement
        vol_mean = np.random.uniform(10.0, 15.0)
        vol_noise = np.random.normal(0, 0.5, n_days)
        volume = np.exp(vol_mean + vol_noise + 0.1 * np.abs(returns / sigma))
        
        df = pd.DataFrame({
            "symbol": symbol,
            "date": date_range.date,
            "open": np.round(open_prices, 2),
            "high": np.round(high_prices, 2),
            "low": np.round(low_prices, 2),
            "close": np.round(close_prices, 2),
            "volume": np.round(volume, 0),
            "security_id": f"MOCK_{symbol}"
        })
        
        return df

    def sync_data(self, start_date: str, end_date: str, force_download: bool = False, universe_size: str = "200"):
        """
        Synchronizes historical data. Only downloads missing records.
        universe_size: "200" or "500" (NIFTY 200 or NIFTY 500).
        """
        if universe_size == "500":
            universe = self.get_nse500_universe()
        else:
            universe = self.get_nse200_universe()
        mappings = self.build_security_mapping(universe)
        
        logger.info(f"Starting synchronization of {len(universe)} symbols...")
        
        # Batch size for logging
        batch_size = 50
        count = 0
        
        for symbol in universe:
            sec_id, inst_type = mappings.get(symbol, (f"MOCK_{symbol}", "EQUITY"))
            
            # Find the last date in the database
            res = self.conn.execute(
                "SELECT MAX(date) FROM daily_ohlcv WHERE symbol = ?", [symbol]
            ).fetchone()
            
            last_date = res[0] if res else None
            
            # Determine start date for download
            if force_download or not last_date:
                fetch_start = start_date
            else:
                # Start downloading from the day after the last date
                last_dt = pd.to_datetime(last_date).date()
                fetch_start_dt = last_dt + datetime.timedelta(days=1)
                
                # Check if fetch_start is in the future relative to end_date
                end_dt = pd.to_datetime(end_date).date()
                if fetch_start_dt > end_dt:
                    # Already up to date
                    continue
                fetch_start = fetch_start_dt.strftime("%Y-%m-%d")
                
            logger.debug(f"Fetching data for {symbol} from {fetch_start} to {end_date}")
            
            # Fetch data (from Dhan API or Synthetic)
            if self.is_synthetic:
                df = self.generate_synthetic_ohlcv(symbol, fetch_start, end_date)
            else:
                # Add delay to avoid rate limit (9 requests per second limit; 0.15s is safe)
                time.sleep(0.15)
                df = self.fetch_dhan_historical(sec_id, "NSE_EQ", inst_type, fetch_start, end_date)
                
                # Fallback to synthetic if API fails
                if df is None or df.empty:
                    logger.warning(f"No API data returned for {symbol}. Generating synthetic data as fallback.")
                    df = self.generate_synthetic_ohlcv(symbol, fetch_start, end_date)
                    
            if df is not None and not df.empty:
                df["symbol"] = symbol
                df["security_id"] = sec_id
                # Write to DuckDB
                self.conn.register("df_temp", df)
                self.conn.execute("""
                    INSERT OR REPLACE INTO daily_ohlcv 
                    SELECT symbol, date, open, high, low, close, volume, security_id FROM df_temp
                """)
                self.conn.unregister("df_temp")
                
            count += 1
            if count % batch_size == 0:
                logger.info(f"Synchronized {count}/{len(universe)} symbols.")
                
        logger.info("Synchronization complete.")

    def load_panel(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        Loads daily OHLCV data from DuckDB and returns the pivoted panel dictionary.
        """
        logger.info(f"Loading data panel from DuckDB for dates {start_date} to {end_date}...")
        
        # Load all data from DuckDB
        query = """
            SELECT symbol, date, open, high, low, close, volume
            FROM daily_ohlcv
            WHERE date >= ? AND date <= ?
            ORDER BY date, symbol
        """
        df = self.conn.execute(query, [start_date, end_date]).fetchdf()
        
        if df.empty:
            logger.error("No historical data found in the database. Please run download/update first.")
            return {
                "open": pd.DataFrame(),
                "high": pd.DataFrame(),
                "low": pd.DataFrame(),
                "close": pd.DataFrame(),
                "volume": pd.DataFrame(),
            }
            
        # Convert date to datetime for consistency in time series
        df['date'] = pd.to_datetime(df['date'])
        
        # Clean duplicates if any (shouldn't be, but prevent pivot errors)
        df.drop_duplicates(subset=['date', 'symbol'], keep='last', inplace=True)
        
        # Pivot each column
        panel = {}
        for metric in ["open", "high", "low", "close", "volume"]:
            # Pivot table: rows are dates, columns are symbols
            pivoted = df.pivot(index='date', columns='symbol', values=metric)
            pivoted = pivoted.sort_index()
            
            # Forward-fill gaps for thin markets or stock suspensions, then fillna(0) for volume
            if metric == "volume":
                pivoted = pivoted.fillna(0.0)
            else:
                pivoted = pivoted.ffill().bfill()
            panel[metric] = pivoted

        # Compute VWAP as (high + low + close) / 3 — a standard daily approximation
        panel["vwap"] = (panel["high"] + panel["low"] + panel["close"]) / 3.0

        logger.info(f"Loaded panel with {panel['close'].shape[0]} dates and {panel['close'].shape[1]} symbols.")
        return panel
