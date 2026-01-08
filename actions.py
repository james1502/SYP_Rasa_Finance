from typing import Any, Dict, List, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction, UserUttered
import yfinance as yf
from datetime import datetime, timedelta
from difflib import get_close_matches
import re
import requests
import json
import urllib.parse  
import os  

#pattern
def _get_valid_terms_pattern() -> List[str]:
    """Shared valid terms for typo correction"""
    return [
        'stock', 'stocks', 'bond', 'bonds', 'price', 'volume',
        'market', 'index', 'what','is', 'are', 'how', 'when', 
        'where', 'explain', 'show','tell', 'me', 'about', 'define',
        'news', 'data','financial','information','company','share',
        'ticker','quote','history','performance','trend','analysis',
        'report','update','current','value','rate','change','high',
        'low','open','close','today','yesterday','week','month','year',
        '52-week','annual','return','growth','dividend','yield',
        'market cap','revenue','profit','loss','forecast','prediction'
        ,'trend','sector','industry','economy','inflation','interest rate',
        'fed','federal reserve','unemployment','gdp','earnings','calls',
        'meetings','conference','presentation','transcript','compare',
        'versus','vs','and','or','between','among','top','best','worst',
        'performing','underperforming','overperforming','outperforming','and',
        'difference','similarities','differences','key metrics','chart',
        'graph','visualization','table','dataframe','statistics','figures',
        'summary','overview','insights','highlights','details','specifics',
        'news','headlines','articles','reports','updates','bulletin',
        'breaking','latest','recent','trending','popular','notable',
        'goodbye','hello','hi','hey','thanks','thank you','please',
        'assist','help','support','service','customer','client',
        'user','account','profile','settings','preferences','options',
        'features','functionality','capabilities','limitations','issues',
        'problems','bugs','errors','feedback','suggestions','recommendations',
        'improvements','enhancements','updates','upgrades','versions',
        'releases','launches','introductions','announcements','news',   
        'apple', 'tesla', 'microsoft', 'google', 'alphabet', 'amazon', 'meta', 'facebook', 'nvidia', 'netflix', 'amd', 'intel', 'oracle', 'salesforce', 'adobe', 'ibm', 'cisco', 'bitcoin', 'btc', 'ethereum', 'eth', 'binance coin', 'bnb', 'cardano', 'ada', 'solana', 'sol', 'ripple', 'xrp', 'polkadot', 'dot', 'dogecoin', 'doge', 'avalanche', 'avax', 'polygon', 'matic', 'chainlink', 'link', 'litecoin', 'ltc', 'jpmorgan', 'bank of america', 'wells fargo', 'goldman sachs', 'morgan stanley', 'visa', 'mastercard', 'paypal', 'walmart', 'disney', 'coca cola', 'pepsi', 'mcdonalds', 'nike', 'starbucks'
    ]

#Corrects typos
class ActionCorrectTypo(Action):
    """Simple typo correction - just corrects and stores"""
    
    def name(self) -> Text:
        return "action_correct_typo"
    
    def _get_valid_terms(self) -> List[str]:
        return _get_valid_terms_pattern()
    
    def _correct_text(self, text: str) -> tuple:
        """Correct typos and return (corrected_text, was_corrected)"""
        if not text:
            return text, False
            
        valid_terms = self._get_valid_terms()
        words = text.lower().split()
        corrected_words = []
        has_correction = False
        
        for word in words:
            if len(word) <= 2:
                corrected_words.append(word)
                continue
            
            matches = get_close_matches(word, valid_terms, n=1, cutoff=0.7)
            
            if matches and matches[0] != word:
                corrected_words.append(matches[0])
                has_correction = True
            else:
                corrected_words.append(word)
        
        corrected_text = " ".join(corrected_words)
        return corrected_text, has_correction
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_message, has_correction = self._correct_text(user_message)
        
        if has_correction:
            dispatcher.utter_message(
                text=f"I understood: '{corrected_message}'"
            )
            return [SlotSet("corrected_query", corrected_message)]
        
        # No correction needed - store original
        return [SlotSet("corrected_query", user_message)]    

#yahoo market data
"""
class ActionFetchMarketData(Action):
    def name(self) -> Text:
        return "action_fetch_market_data"
    
    def _extract_company_from_query(self, query: str) -> str:
        """#Extract just the company name from a query like 'Apple stock price'
"""
        if not query:
            return None
        
        # Remove common query terms
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = ['stock', 'price', 'data', 'volume', 'current', 'show', 'me', 
                      'get', 'fetch', 'what', 'is', 'the', 'of', 'for']
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        # Return the first remaining word (likely the company name)
        if cleaned_words:
            return cleaned_words[0]
        
        return query.strip()

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        corrected_query = tracker.get_slot("corrected_query")
        security_name = tracker.get_slot("security_name")
        
        # Use corrected query if available, otherwise use security_name
        query_to_use = corrected_query if corrected_query else security_name
        
        # Extract just the company name from the full query
        company_name = self._extract_company_from_query(query_to_use)
        
        # Convert company name to ticker symbol
        cleaned_ticker = _clean_ticker(company_name)

        if not cleaned_ticker or len(cleaned_ticker) < 2:
            dispatcher.utter_message(
                text=f"I couldn't identify a valid stock ticker from '{query_to_use}'. Please provide a ticker symbol like AAPL or a company name like Apple."
            )
            return [SlotSet("security_name", None)]
        
        try:
            ticker = yf.Ticker(cleaned_ticker)
            hist = ticker.history(period="1y")
            
            if hist.empty:
                raise ValueError(f"No data available for {cleaned_ticker}")
            
            info = ticker.info
            
            # Extract data with fallbacks
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]
            volume = info.get('volume') or hist['Volume'].iloc[-1]
            high_52week = info.get('fiftyTwoWeekHigh') or hist['High'].max()
            low_52week = info.get('fiftyTwoWeekLow') or hist['Low'].min()
            
            market_data = (
                f"Current Price: ${current_price:.2f}\n"
                f"Volume: {int(volume):,}\n"
                f"52-Week High: ${high_52week:.2f}\n"
                f"52-Week Low: ${low_52week:.2f}"
            )
            
        except Exception as e:
            print(f"Error fetching data for {cleaned_ticker}: {str(e)}")
            market_data = (
                f"Unable to fetch data for {cleaned_ticker}. "
                f"Error: {str(e)}\n"
                f"Please verify the ticker symbol is correct. "
                f"Common tickers: AAPL (Apple), TSLA (Tesla), MSFT (Microsoft)."
            )
        
        return [
            SlotSet("market_data_output", market_data),
            SlotSet("security_name", cleaned_ticker)
        ]
"""

#alpha market
class ActionFetchMarketData(Action):
    def name(self) -> Text:
        return "action_fetch_market_data"
    
    def _extract_company_from_query(self, query: str) -> str:
        """Extract just the company name from a query like 'Apple stock price'"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = ['stock', 'price', 'data', 'volume', 'current', 'show', 'me', 
                      'get', 'fetch', 'what', 'is', 'the', 'of', 'for']
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        # Return the first remaining word (likely the company name)
        if cleaned_words:
            return cleaned_words[0]
        
        return query.strip()

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Replace with your actual Alpha Vantage API key
        API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
        
        corrected_query = tracker.get_slot("corrected_query")
        security_name = tracker.get_slot("security_name")
        
        # Use corrected query if available, otherwise use security_name
        query_to_use = corrected_query if corrected_query else security_name
        
        # Extract just the company name from the full query
        company_name = self._extract_company_from_query(query_to_use)
        
        # Convert company name to ticker symbol
        cleaned_ticker = _clean_ticker(company_name)

        if not cleaned_ticker or len(cleaned_ticker) < 2:
            dispatcher.utter_message(
                text=f"I couldn't identify a valid stock ticker from '{query_to_use}'. Please provide a ticker symbol like AAPL or a company name like Apple."
            )
            return [SlotSet("security_name", None)]
        
        try:
            # Alpha Vantage API endpoints
            quote_url = f"https://www.alphavantage.co/query"
            
            # Get real-time quote data
            quote_params = {
                "function": "GLOBAL_QUOTE",
                "symbol": cleaned_ticker,
                "apikey": API_KEY
            }
            
            quote_response = requests.get(quote_url, params=quote_params, timeout=10)
            quote_data = quote_response.json()
            
            # Check for errors
            if "Error Message" in quote_data:
                raise ValueError(f"Invalid ticker symbol: {cleaned_ticker}")
            
            if "Note" in quote_data:
                raise ValueError("API rate limit reached. Please try again in a minute.")
            
            if "Global Quote" not in quote_data or not quote_data["Global Quote"]:
                raise ValueError(f"No data available for {cleaned_ticker}")
            
            quote = quote_data["Global Quote"]
            
            # Extract data from Alpha Vantage response
            current_price = float(quote.get("05. price", 0))
            volume = int(quote.get("06. volume", 0))
            high = float(quote.get("03. high", 0))
            low = float(quote.get("04. low", 0))
            
            # Get 52-week high/low (requires TIME_SERIES_DAILY)
            daily_url = f"https://www.alphavantage.co/query"
            daily_params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": cleaned_ticker,
                "apikey": API_KEY,
                "outputsize": "full"  # Get full history for 52-week calculation
            }
            
            daily_response = requests.get(daily_url, params=daily_params, timeout=10)
            daily_data = daily_response.json()
            
            # Calculate 52-week high/low
            high_52week = high
            low_52week = low
            
            if "Time Series (Daily)" in daily_data:
                time_series = daily_data["Time Series (Daily)"]
                
                # Get last 252 trading days (approximately 1 year)
                recent_dates = sorted(time_series.keys(), reverse=True)[:252]
                
                highs = [float(time_series[date]["2. high"]) for date in recent_dates]
                lows = [float(time_series[date]["3. low"]) for date in recent_dates]
                
                high_52week = max(highs) if highs else high
                low_52week = min(lows) if lows else low
            
            market_data = (
                f"Current Price: ${current_price:.2f}\n"
                f"Volume: {volume:,}\n"
                f"52-Week High: ${high_52week:.2f}\n"
                f"52-Week Low: ${low_52week:.2f}"
            )
            
        except requests.exceptions.RequestException as e:
            print(f"Network error fetching data for {cleaned_ticker}: {str(e)}")
            market_data = (
                f"Unable to fetch data for {cleaned_ticker} due to network issues. "
                f"Please try again later."
            )
        except ValueError as e:
            print(f"Error fetching data for {cleaned_ticker}: {str(e)}")
            market_data = str(e)
        except Exception as e:
            print(f"Unexpected error fetching data for {cleaned_ticker}: {str(e)}")
            market_data = (
                f"Unable to fetch data for {cleaned_ticker}. "
                f"Please verify the ticker symbol is correct. "
                f"Common tickers: AAPL (Apple), TSLA (Tesla), MSFT (Microsoft)."
            )
        
        return [
            SlotSet("market_data_output", market_data),
            SlotSet("security_name", cleaned_ticker)
        ]

class ActionFetchIndexInfo(Action):
    def name(self) -> Text:
        return "action_fetch_index_info"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        index_name = tracker.get_slot("index_name")
        
        if not index_name:
            return [SlotSet("index_info_output", "Please specify which index you'd like information about.")]
        
        # Map common index names to Yahoo Finance tickers
        index_mapping = {
            "s&p 500": "^GSPC",
            "s&p500": "^GSPC",
            "sp500": "^GSPC",
            "s and p 500": "^GSPC",
            "dow jones": "^DJI",
            "dow": "^DJI",
            "djia": "^DJI",
            "nasdaq": "^IXIC",
            "nasdaq composite": "^IXIC",
            "russell 2000": "^RUT",
            "russell": "^RUT",
            "ftse 100": "^FTSE",
            "ftse": "^FTSE"
        }
        
        # Clean and normalize the index name - REMOVE BACKSLASHES
        index_name_clean = index_name.lower().strip().replace("\\", "")
        ticker_symbol = index_mapping.get(index_name_clean, index_name)
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="1y")
            
            if hist.empty:
                raise ValueError(f"No data available for {index_name}")
            
            current_level = hist['Close'].iloc[-1]
            previous_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_level
            change = current_level - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else 0
            
            # Calculate YTD return
            ytd_start = datetime(datetime.now().year, 1, 1)
            ytd_hist = ticker.history(start=ytd_start)
            
            if not ytd_hist.empty:
                ytd_return = ((current_level - ytd_hist['Close'].iloc[0]) / ytd_hist['Close'].iloc[0] * 100)
            else:
                ytd_return = 0.0
            
            index_info = (
                f"Current Level: {current_level:,.2f}\n"
                f"Change: {change:+.2f} ({change_percent:+.2f}%)\n"
                f"YTD Return: {ytd_return:+.1f}%"
            )
            
        except Exception as e:
            print(f"Error fetching index data for {index_name}: {str(e)}")
            index_info = f"Unable to fetch data for {index_name}. Please verify the index name is correct."
        
        return [SlotSet("index_info_output", index_info)]

class ActionFetchComparisonData(Action):
    def name(self) -> Text:
        return "action_fetch_comparison_data"

    def _extract_companies_from_text(self, text: str) -> List[str]:
        """
        Extract company names from natural language.
        Handles patterns like: 'compare Apple and Tesla', 'AAPL vs TSLA'
        """
        # Clean and lower the text
        text_lower = text.lower().strip()
        
        # Common company name to ticker mapping (expanded for robustness)
        company_to_ticker = {
            'apple': 'AAPL', 'aapl': 'AAPL',
            'tesla': 'TSLA', 'tsla': 'TSLA',
            'microsoft': 'MSFT', 'msft': 'MSFT',
            'google': 'GOOGL', 'googl': 'GOOGL', 'alphabet': 'GOOGL',
            'amazon': 'AMZN', 'amzn': 'AMZN',
            'meta': 'META', 'facebook': 'META',
            'nvidia': 'NVDA', 'nvda': 'NVDA',
            'netflix': 'NFLX', 'nflx': 'NFLX',
        }
        
        found_tickers = []
        words = re.findall(r'[a-zA-Z]{2,}', text_lower)  # Find all words of 2+ letters
        
        for word in words:
            if word in company_to_ticker:
                ticker = company_to_ticker[word]
                if ticker not in found_tickers:
                    found_tickers.append(ticker)
            # Also check for direct uppercase ticker symbols in the original text
            elif word.upper() in company_to_ticker.values():
                ticker = word.upper()
                if ticker not in found_tickers:
                    found_tickers.append(ticker)
        
        # Return the first 2 unique tickers found (for comparison)
        return found_tickers[:2]

    def _fetch_company_metrics(self, ticker_symbol: str) -> Dict:
        """Fetch key metrics for a single company using yfinance."""
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            hist = ticker.history(period="1y")
            
            if hist.empty:
                return None
            
            # Current price and basic info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]
            company_name = info.get('longName') or info.get('shortName') or ticker_symbol
            
            # Calculate YTD return
            current_year = datetime.now().year
            ytd_start = f"{current_year}-01-01"
            ytd_hist = ticker.history(start=ytd_start)
            
            if len(ytd_hist) > 0:
                ytd_return_pct = ((hist['Close'].iloc[-1] - ytd_hist['Close'].iloc[0]) / ytd_hist['Close'].iloc[0]) * 100
            else:
                ytd_return_pct = 0.0
            
            # Key financial metrics (with fallbacks)
            metrics = {
                'ticker': ticker_symbol,
                'name': company_name,
                'current_price': round(current_price, 2),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'ytd_return': round(ytd_return_pct, 2),
                '52_week_high': info.get('fiftyTwoWeekHigh') or hist['High'].max(),
                '52_week_low': info.get('fiftyTwoWeekLow') or hist['Low'].min(),
                'volume': info.get('volume') or hist['Volume'].iloc[-1],
            }
            
            return metrics
            
        except Exception as e:
            print(f"Error fetching data for {ticker_symbol}: {str(e)}")
            return None

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        comparison_items = tracker.get_slot("comparison_items")
        comparison_criteria = tracker.get_slot("comparison_criteria")
        
        if not comparison_items:
            error_msg = "I need at least two items to compare."
            return [SlotSet("comparison_output", error_msg)]
        
        try:
            items_str = str(comparison_items)
            if " and " in items_str.lower():
                items_str = items_str.lower().replace(" and ", ", ")
            
            items = [item.strip() for item in items_str.split(",") if item.strip()]
            
            if len(items) < 2:
                error_msg = "I need at least two items to compare."
                return [SlotSet("comparison_output", error_msg)]
            
            # Determine period based on criteria
            period = "1mo"
            if comparison_criteria:
                criteria_lower = str(comparison_criteria).lower()
                if "month" in criteria_lower:
                    period = "1mo"
                elif "year" in criteria_lower or "ytd" in criteria_lower:
                    period = "1y"
                elif "week" in criteria_lower:
                    period = "1wk"
            
            comparison_results = []
            for item in items:
                ticker_symbol = _clean_ticker(item)
                
                try:
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period=period)
                    
                    if not hist.empty:
                        start_price = hist['Close'].iloc[0]
                        end_price = hist['Close'].iloc[-1]
                        return_pct = ((end_price - start_price) / start_price * 100)
                        
                        # Enhanced format with current price
                        comparison_results.append(
                            f"{item.strip()}: {return_pct:+.2f}% (${end_price:.2f})"
                        )
                    else:
                        comparison_results.append(f"{item.strip()}: No data")
                        
                except Exception as ticker_error:
                    comparison_results.append(f"{item.strip()}: Error")
            
            # Add summary
            comparison_output = f"📊 **{period.upper()} Performance Comparison**\n\n"
            comparison_output += "\n".join(comparison_results)
            
            # Add winner summary
            # Add winner summary
            if len(comparison_results) == 2:
                # Extract percentage values from results
                percentages = []
                for result in comparison_results:
                    # Extract the percentage value (e.g., "-5.48%" or "+16.24%")
                    import re
                    match = re.search(r'([+-]?\d+\.\d+)%', result)
                    if match:
                        percentages.append(float(match.group(1)))
                    else:
                        percentages.append(float('-inf'))
                
                # Determine winner (higher percentage is better)
                winner_idx = 0 if percentages[0] > percentages[1] else 1
                comparison_output += f"\n\n✨ **Winner:** {items[winner_idx]}"
               
            
        except Exception as e:
            comparison_output = f"Unable to perform comparison."
        
        return [SlotSet("comparison_output", comparison_output)]

    def _format_comparison_table(self, companies_data: List[Dict]) -> str:
        """Format the comparison data into a readable table."""
        if not companies_data:
            return "No comparison data available."
        
        # Define the metrics to show in the table
        headers = ["Metric", companies_data[0]['ticker'], companies_data[1]['ticker']]
        
        # Prepare rows for key metrics
        rows = [
            ["Company", companies_data[0].get('name', 'N/A'), companies_data[1].get('name', 'N/A')],
            ["Current Price", f"${companies_data[0].get('current_price', 'N/A'):,}", f"${companies_data[1].get('current_price', 'N/A'):,}"],
            ["Market Cap", f"${self._format_large_number(companies_data[0].get('market_cap', 0))}", f"${self._format_large_number(companies_data[1].get('market_cap', 0))}"],
            ["P/E Ratio", f"{companies_data[0].get('pe_ratio', 'N/A'):.2f}" if companies_data[0].get('pe_ratio') else 'N/A', 
                        f"{companies_data[1].get('pe_ratio', 'N/A'):.2f}" if companies_data[1].get('pe_ratio') else 'N/A'],
            ["YTD Return", f"{companies_data[0].get('ytd_return', 0):+.2f}%", f"{companies_data[1].get('ytd_return', 0):+.2f}%"],
            ["52-Week High", f"${companies_data[0].get('52_week_high', 0):.2f}", f"${companies_data[1].get('52_week_high', 0):.2f}"],
            ["52-Week Low", f"${companies_data[0].get('52_week_low', 0):.2f}", f"${companies_data[1].get('52_week_low', 0):.2f}"],
        ]
        
        # Create the table
        table = "📊 **Comparison Results**\n\n"
        table += "| " + " | ".join(headers) + " |\n"
        table += "|:" + "-|:" * (len(headers)-1) + "-|\n"
        
        for row in rows:
            table += "| " + " | ".join(str(cell) for cell in row) + " |\n"
        
        # Add a summary insight
        table += f"\n**Summary:** {companies_data[0]['ticker']} has a {'higher' if companies_data[0].get('pe_ratio', 0) > companies_data[1].get('pe_ratio', 1) else 'lower'} P/E ratio than {companies_data[1]['ticker']}, indicating {'higher growth expectations' if companies_data[0].get('pe_ratio', 0) > companies_data[1].get('pe_ratio', 1) else 'more value-oriented pricing'}."
        
        return table

    def _format_large_number(self, num: float) -> str:
        """Format large numbers into billions/trillions for readability."""
        if num is None:
            return "N/A"
        
        if num >= 1e12:
            return f"{num/1e12:.2f}T"
        elif num >= 1e9:
            return f"{num/1e9:.2f}B"
        elif num >= 1e6:
            return f"{num/1e6:.2f}M"
        else:
            return f"{num:,.0f}"
        
class ActionValidateComparisonItems(Action):
    def name(self) -> Text:
        return "validate_comparison_items"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        comparison_items = tracker.get_slot("comparison_items")
        
        if not comparison_items:
            return [SlotSet("comparison_items", None)]
        
        # Validate format
        items = comparison_items.split(",") if isinstance(comparison_items, str) else comparison_items
        
        if len(items) < 2:
            dispatcher.utter_message(text="Please provide at least two items to compare.")
            return [SlotSet("comparison_items", None)]
        
        # Validation succeeded
        return [SlotSet("comparison_items", comparison_items)]

class ActionFetchMarketNews(Action):
    """Fetch market news using Massive API"""
    
    def name(self) -> Text:
        return "action_fetch_market_news"
    
    def _get_ticker_from_topic(self, topic: str) -> str:
        """Convert company name or topic to ticker symbol"""
        company_to_ticker = {
            'apple': 'AAPL',
            'tesla': 'TSLA',
            'microsoft': 'MSFT',
            'google': 'GOOGL',
            'alphabet': 'GOOGL',
            'amazon': 'AMZN',
            'meta': 'META',
            'facebook': 'META',
            'nvidia': 'NVDA',
            'netflix': 'NFLX',
        }
        
        topic_lower = topic.lower().strip()
        
        # Check if it's a company name
        if topic_lower in company_to_ticker:
            return company_to_ticker[topic_lower]
        
        # If it's already a ticker (2-5 uppercase letters), return it
        if topic.isupper() and 2 <= len(topic) <= 5:
            return topic
            
        return None
    
    def _fetch_news_from_massive_api(self, ticker: str = None) -> List[Dict]:
        """Fetch news from a financial API (Corrected Version)."""
        # 1. REPLACE with a valid API Key from Alpha Vantage (get free key at https://www.alphavantage.co/support/#api-key)
        api_key = "ALPHA_VANTAGE_API_KEY"
        
        # 2. CORRECT the endpoint to a NEWS API (Alpha Vantage example)
        base_url = "https://www.alphavantage.co/query"
        
        try:
            # 3. SET correct parameters for a news API
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker if ticker else "",
                "apikey": api_key,
                "sort": "LATEST"
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()  # Check for HTTP errors
            
            data = response.json()
            
            # 4. PARSE the correct response structure (Alpha Vantage returns a dict with a 'feed' key)
            if "feed" in data:
                return data["feed"][:5]  # Return top 5 news items
            else:
                print(f"Unexpected API response structure: {data}")
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching news from API: {str(e)}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing API response as JSON: {str(e)}")
            return []
        
    def _format_news_output(self, news_data: List[Dict], topic: str) -> str:
        """Format news data into readable output"""
        if not news_data:
            return f"No recent news found for {topic}."
        
        # Take top 5 news items
        news_items = news_data[:5]
        formatted_news = [f"Latest news about {topic}:\n"]
        
        for idx, item in enumerate(news_items, 1):
            # Adjust field names based on actual API response structure
            title = item.get('title', item.get('headline', 'No title'))
            date = item.get('date', item.get('published_date', 'Unknown date'))
            summary = item.get('summary', item.get('description', ''))
            
            news_entry = f"{idx}. {title}"
            if date:
                news_entry += f" ({date})"
            if summary:
                news_entry += f"\n   {summary[:150]}..."
            
            formatted_news.append(news_entry)
        
        return "\n\n".join(formatted_news)

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        news_topic = tracker.get_slot("news_topic")
        
        if not news_topic:
            news_output = "Please specify what topic or company you'd like news about."
            return [SlotSet("news_output", news_output)]
        
        # Convert topic to ticker if it's a company name
        ticker = _clean_ticker(news_topic)
        
        # Fetch news from Massive API
        news_data = self._fetch_news_from_massive_api(ticker)
        
        # Format the output
        if news_data:
            news_output = self._format_news_output(news_data, news_topic)
        else:
            news_output = f"Unable to fetch news for {news_topic}. Please try again or specify a different company."
        
        return [SlotSet("news_output", news_output)]

class ActionRouteClarifiedQuery(Action):

    def name(self) -> Text:
        return "action_route_clarified_query"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        clarified_intent = tracker.get_slot("clarified_intent")
        return []

class ActionFetchAnalysis(Action):
    """Fetch comprehensive financial analysis for a company"""
    
    def name(self) -> Text:
        return "action_fetch_analysis"

    def _extract_company_from_query(self, query: str) -> str:
        """Extract just the company name from a query like 'give me Apple analysis'"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = ['give', 'me', 'analysis', 'analyze', 'financial', 
                      'performance', 'of', 'the', 'a', 'an', 'show', 'get', 
                      'fetch', 'what', 'is', 'for', 'about']
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        # Return the first remaining word (likely the company name)
        if cleaned_words:
            return cleaned_words[0]
        
        return query.strip()

    def _calculate_technical_indicators(self, hist) -> Dict:
        """Calculate technical indicators like moving averages and RSI"""
        if hist.empty or len(hist) < 50:
            return {}
        
        # Simple Moving Averages
        sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        
        # RSI (Relative Strength Index)
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))
        
        return {
            'sma_20': sma_20,
            'sma_50': sma_50,
            'rsi': rsi
        }
    
    def _get_trend_signal(self, current_price: float, sma_20: float, sma_50: float) -> str:
        """Determine trend based on moving averages"""
        if current_price > sma_20 > sma_50:
            return "Strong Uptrend 📈"
        elif current_price > sma_20:
            return "Moderate Uptrend ↗️"
        elif current_price < sma_20 < sma_50:
            return "Strong Downtrend 📉"
        elif current_price < sma_20:
            return "Moderate Downtrend ↘️"
        else:
            return "Sideways/Neutral ➡️"
    
    def _get_rsi_signal(self, rsi: float) -> str:
        """Interpret RSI value"""
        if rsi > 70:
            return "Overbought ⚠️"
        elif rsi < 30:
            return "Oversold 💡"
        else:
            return "Neutral"
    
    def _get_performance_description(self, ytd_return: float, month_return: float) -> str:
        """Generate descriptive text for performance metrics"""
        descriptions = []
        
        # YTD performance description
        if ytd_return > 20:
            descriptions.append(f"The stock has shown exceptional year-to-date performance with a {ytd_return:+.2f}% gain, significantly outperforming the broader market.")
        elif ytd_return > 10:
            descriptions.append(f"The stock has delivered strong year-to-date returns of {ytd_return:+.2f}%, indicating solid investor confidence.")
        elif ytd_return > 0:
            descriptions.append(f"The stock has posted modest year-to-date gains of {ytd_return:+.2f}%, showing positive but measured growth.")
        elif ytd_return > -10:
            descriptions.append(f"The stock has experienced a slight year-to-date decline of {ytd_return:.2f}%, reflecting some market headwinds.")
        else:
            descriptions.append(f"The stock has faced significant year-to-date challenges with a {ytd_return:.2f}% loss, underperforming the market.")
        
        # Recent momentum description
        if month_return > 5:
            descriptions.append(f"Recent momentum has been particularly strong with a {month_return:+.2f}% gain over the past month.")
        elif month_return > 0:
            descriptions.append(f"The stock has maintained positive momentum with a {month_return:+.2f}% increase in the last month.")
        elif month_return > -5:
            descriptions.append(f"Recent performance has been slightly negative with a {month_return:.2f}% decline over the past month.")
        else:
            descriptions.append(f"The stock has experienced notable weakness recently, down {month_return:.2f}% in the past month.")
        
        return " ".join(descriptions)
    
    def _get_valuation_description(self, pe_ratio: float, forward_pe: float, peg_ratio: float) -> str:
        """Generate descriptive text for valuation metrics"""
        descriptions = []
        
        if pe_ratio:
            if pe_ratio > 30:
                descriptions.append(f"With a P/E ratio of {pe_ratio:.2f}, the stock trades at a premium valuation, suggesting high growth expectations from investors.")
            elif pe_ratio > 20:
                descriptions.append(f"The P/E ratio of {pe_ratio:.2f} indicates a moderate valuation, typical for established growth companies.")
            elif pe_ratio > 15:
                descriptions.append(f"At a P/E ratio of {pe_ratio:.2f}, the stock appears reasonably valued relative to earnings.")
            else:
                descriptions.append(f"The P/E ratio of {pe_ratio:.2f} suggests the stock may be undervalued or facing growth concerns.")
        
        if peg_ratio:
            if peg_ratio < 1:
                descriptions.append(f"The PEG ratio of {peg_ratio:.2f} indicates the stock may be undervalued relative to its growth rate.")
            elif peg_ratio < 2:
                descriptions.append(f"The PEG ratio of {peg_ratio:.2f} suggests fair valuation considering growth prospects.")
            else:
                descriptions.append(f"The PEG ratio of {peg_ratio:.2f} may indicate the stock is expensive relative to its growth potential.")
        
        return " ".join(descriptions) if descriptions else "Valuation metrics suggest a balanced risk-reward profile."
    
    def _get_technical_description(self, current_price: float, indicators: Dict) -> str:
        """Generate descriptive text for technical indicators"""
        descriptions = []
        
        sma_20 = indicators.get('sma_20', 0)
        sma_50 = indicators.get('sma_50', 0)
        rsi = indicators.get('rsi', 50)
        
        # Trend description
        if current_price > sma_20 > sma_50:
            descriptions.append("The stock is in a strong uptrend with price trading above both key moving averages, indicating bullish momentum.")
        elif current_price > sma_20:
            descriptions.append("The stock shows moderate upward momentum with price above the 20-day moving average.")
        elif current_price < sma_20 < sma_50:
            descriptions.append("The stock is in a downtrend with price below both moving averages, suggesting bearish pressure.")
        else:
            descriptions.append("The stock is trading in a neutral range with mixed technical signals.")
        
        # RSI description
        if rsi > 70:
            descriptions.append(f"The RSI of {rsi:.1f} indicates overbought conditions, suggesting potential for a pullback.")
        elif rsi < 30:
            descriptions.append(f"The RSI of {rsi:.1f} shows oversold conditions, which could present a buying opportunity.")
        else:
            descriptions.append(f"The RSI of {rsi:.1f} is in neutral territory, indicating balanced buying and selling pressure.")
        
        return " ".join(descriptions)
    
    def _get_volume_description(self, volume_ratio: float) -> str:
        """Generate descriptive text for volume analysis"""
        if volume_ratio > 2:
            return "Trading volume is exceptionally high, indicating strong investor interest and potentially significant price action."
        elif volume_ratio > 1.5:
            return "Trading volume is elevated above average, suggesting increased market activity and attention."
        elif volume_ratio > 0.8:
            return "Trading volume is within normal ranges, indicating steady market participation."
        else:
            return "Trading volume is below average, which may indicate reduced market interest or liquidity concerns."
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        corrected_query = tracker.get_slot("corrected_query")
        analysis_company = tracker.get_slot("analysis_company")
        
        # Use corrected query if available, otherwise use analysis_company
        query_to_use = corrected_query if corrected_query else analysis_company
        
        if not query_to_use:
            analysis_output = "Please specify which company you'd like me to analyze."
            return [SlotSet("analysis_output", analysis_output)]
        
        # Extract just the company name from the full query
        company_name = self._extract_company_from_query(query_to_use)
        
        # Convert company name to ticker symbol
        ticker_symbol = _clean_ticker(company_name)
        
        if not ticker_symbol or len(ticker_symbol) < 2:
            analysis_output = (
                f"I couldn't identify a valid company from '{query_to_use}'. "
                f"Please provide a company name like Apple or a ticker symbol like AAPL."
            )
            return [
                SlotSet("analysis_output", analysis_output),
                SlotSet("analysis_company", None)
            ]
        
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info
            hist = ticker.history(period="1y")
            
            if hist.empty:
                raise ValueError(f"No data available for {ticker_symbol}")
            
            # Basic Info
            company_full_name = info.get('longName', ticker_symbol)
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]
            market_cap = info.get('marketCap', 0)
            
            # Performance Metrics
            ytd_start = datetime(datetime.now().year, 1, 1)
            ytd_hist = ticker.history(start=ytd_start)
            
            if not ytd_hist.empty:
                ytd_return = ((current_price - ytd_hist['Close'].iloc[0]) / ytd_hist['Close'].iloc[0] * 100)
            else:
                ytd_return = 0.0
            
            # 1-month performance
            month_ago = datetime.now() - timedelta(days=30)
            month_hist = ticker.history(start=month_ago)
            if not month_hist.empty:
                month_return = ((current_price - month_hist['Close'].iloc[0]) / month_hist['Close'].iloc[0] * 100)
            else:
                month_return = 0.0
            
            # Technical Indicators
            indicators = self._calculate_technical_indicators(hist)
            
            # Valuation Metrics
            pe_ratio = info.get('trailingPE')
            forward_pe = info.get('forwardPE')
            peg_ratio = info.get('pegRatio')
            
            # Volume Analysis
            avg_volume = hist['Volume'].mean()
            current_volume = hist['Volume'].iloc[-1]
            volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 1.0
            
            # Build Analysis Output with Descriptions
            analysis_output = f"**{company_full_name} ({ticker_symbol}) - Comprehensive Analysis**\n\n"
            
            # Executive Summary
            analysis_output += "📋 **Executive Summary:**\n"
            analysis_output += self._get_performance_description(ytd_return, month_return)
            analysis_output += "\n\n"
            
            # Current Status
            analysis_output += f"💰 **Current Market Data:**\n"
            analysis_output += f"  • Current Price: ${current_price:.2f}\n"
            analysis_output += f"  • Market Cap: ${self._format_large_number(market_cap)}\n\n"
            
            # Performance
            analysis_output += f"📈 **Performance Metrics:**\n"
            analysis_output += f"  • YTD Return: {ytd_return:+.2f}%\n"
            analysis_output += f"  • 1-Month Return: {month_return:+.2f}%\n\n"
            
            # Technical Analysis with Description
            if indicators:
                analysis_output += f"🔍 **Technical Analysis:**\n"
                analysis_output += self._get_technical_description(current_price, indicators)
                analysis_output += f"\n\n  • Trend: {self._get_trend_signal(current_price, indicators.get('sma_20', 0), indicators.get('sma_50', 0))}\n"
                analysis_output += f"  • RSI (14): {indicators.get('rsi', 0):.1f} - {self._get_rsi_signal(indicators.get('rsi', 50))}\n"
                analysis_output += f"  • 20-Day SMA: ${indicators.get('sma_20', 0):.2f}\n"
                analysis_output += f"  • 50-Day SMA: ${indicators.get('sma_50', 0):.2f}\n\n"
            
            # Valuation with Description
            if pe_ratio or forward_pe:
                analysis_output += f"💼 **Valuation Analysis:**\n"
                analysis_output += self._get_valuation_description(pe_ratio, forward_pe, peg_ratio)
                analysis_output += "\n\n"
                if pe_ratio:
                    analysis_output += f"  • P/E Ratio: {pe_ratio:.2f}\n"
                if forward_pe:
                    analysis_output += f"  • Forward P/E: {forward_pe:.2f}\n"
                if peg_ratio:
                    analysis_output += f"  • PEG Ratio: {peg_ratio:.2f}\n"
                analysis_output += "\n"
            
            # Volume with Description
            analysis_output += f"📊 **Volume Analysis:**\n"
            analysis_output += self._get_volume_description(volume_ratio)
            analysis_output += f"\n\n  • Current Volume: {int(current_volume):,}\n"
            analysis_output += f"  • Avg Volume: {int(avg_volume):,}\n"
            analysis_output += f"  • Volume Ratio: {volume_ratio:.2f}x {'(High Activity)' if volume_ratio > 1.5 else '(Normal)'}\n"
            
        except Exception as e:
            print(f"Error fetching analysis for {ticker_symbol}: {str(e)}")
            analysis_output = (
                f"Unable to fetch analysis for {ticker_symbol}. "
                f"Please verify the ticker symbol is correct."
            )
        
        return [
            SlotSet("analysis_output", analysis_output),
            SlotSet("analysis_company", ticker_symbol)
        ]
    
    def _format_large_number(self, num: float) -> str:
        """Format large numbers into billions/trillions"""
        if num is None or num == 0:
            return "N/A"

class ActionShowChart(Action):
    
    def name(self) -> Text:
        return "action_show_chart"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Get corrected query first
        corrected_query = tracker.get_slot("corrected_query")
        message = corrected_query if corrected_query else tracker.latest_message.get("text", "").lower()
        
        # Extract asset name from the message
        asset_name = self._extract_asset_from_message(message)
        
        if not asset_name:
            dispatcher.utter_message(text="📊 Which asset would you like to see a chart for? Try: 'Bitcoin chart', 'Apple chart', or 'S&P 500 chart'")
            return []
        
        asset_lower = asset_name.lower()
        
        # Define mappings
        crypto_map = {
            "bitcoin": "bitcoin", "btc": "bitcoin",
            "ethereum": "ethereum", "eth": "ethereum",
            "dogecoin": "dogecoin", "doge": "dogecoin",
            "solana": "solana", "sol": "solana",
            "cardano": "cardano", "ada": "cardano",
            "binancecoin": "binancecoin", "bnb": "binancecoin",
            "ripple": "ripple", "xrp": "ripple",
            "avalanche-2": "avalanche-2", "avax": "avalanche-2",
            "chainlink": "chainlink", "link": "chainlink",
            "matic-network": "matic-network", "matic": "matic-network",
            "polygon": "matic-network",
            "uniswap": "uniswap", "uni": "uniswap",
            "cosmos": "cosmos", "atom": "cosmos",
            "polkadot": "polkadot", "dot": "polkadot",
            "litecoin": "litecoin", "ltc": "litecoin"
        }
        
        index_map = {
            "sp500": "SPY", "s&p 500": "SPY", "s&p": "SPY", "s and p 500": "SPY",
            "nasdaq": "QQQ",
            "dow": "DIA", "dow jones": "DIA",
            "ftse100": "EWU", "ftse": "EWU",
            "nikkei": "EWJ"
        }
        
        # Check if it's a crypto
        if asset_lower in crypto_map or asset_lower in crypto_map.values():
            coin_id = crypto_map.get(asset_lower, asset_lower)
            return self.show_crypto_chart(dispatcher, coin_id)
        
        # Check if it's an index
        elif asset_lower in index_map:
            symbol = index_map.get(asset_lower)
            return self.show_index_chart(dispatcher, asset_lower, symbol)
        
        # Otherwise treat as stock ticker
        else:
            ticker_symbol = _clean_ticker(asset_name)
            return self.show_stock_chart(dispatcher, ticker_symbol)
    
    def _extract_asset_from_message(self, message: str) -> str:
        """Extract asset name from user message"""
        # Remove noise words
        noise_words = ['chart', 'show', 'me', 'the', 'a', 'an', 'for', 'of', 
                      'price', 'graph', 'visualization', 'display']
        
        words = message.lower().split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        # Return the cleaned phrase
        if cleaned_words:
            return " ".join(cleaned_words)
        
        return None
    
    def generate_quickchart_url(self, labels: list, data: list, title: str, is_positive: bool) -> str:
        """Generate QuickChart URL for visualization"""
        color = "rgb(0, 211, 149)" if is_positive else "rgb(255, 107, 107)"
        bg_color = "rgba(0, 211, 149, 0.2)" if is_positive else "rgba(255, 107, 107, 0.2)"
        
        chart_config = {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": title,
                    "data": data,
                    "borderColor": color,
                    "backgroundColor": bg_color,
                    "fill": True,
                    "lineTension": 0.4,
                    "pointRadius": 0,
                    "borderWidth": 2
                }]
            },
            "options": {
                "elements": {
                    "line": {
                        "tension": 0.4
                    }
                },
                "plugins": {
                    "legend": {"display": False},
                    "title": {
                        "display": True,
                        "text": title,
                        "color": "#ffffff",
                        "font": {"size": 16}
                    }
                },
                "scales": {
                    "x": {
                        "display": False
                    },
                    "y": {
                        "ticks": {"color": "#aaaaaa"},
                        "grid": {"color": "rgba(255,255,255,0.1)"}
                    }
                }
            }
        }
        
        chart_json = json.dumps(chart_config)
        encoded = urllib.parse.quote(chart_json)
        return f"https://quickchart.io/chart?c={encoded}&backgroundColor=%231a1a2e&width=500&height=300"
    
    def show_crypto_chart(self, dispatcher: CollectingDispatcher, coin_id: str) -> List[Dict[Text, Any]]:
        """Generate chart for cryptocurrency"""
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=7"
            response = requests.get(url, timeout=15)
            data = response.json()
            
            if "prices" not in data:
                dispatcher.utter_message(text=f"📊 Couldn't fetch data for {coin_id}.")
                return []
            
            prices = data["prices"]
            
            # Sample data points
            sampled = prices[::len(prices)//30] if len(prices) > 30 else prices
            
            labels = [datetime.fromtimestamp(p[0]/1000).strftime("%m/%d %H:%M") for p in sampled]
            values = [round(p[1], 2) for p in sampled]
            
            current_price = prices[-1][1]
            first_price = prices[0][1]
            price_change = ((current_price - first_price) / first_price) * 100
            is_positive = price_change >= 0
            
            chart_url = self.generate_quickchart_url(labels, values, f"{coin_id.title()} - 7 Day", is_positive)
            
            emoji = "📈" if is_positive else "📉"
            dispatcher.utter_message(
                text=f"{emoji} {coin_id.title()} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%",
                image=chart_url
            )
            
        except Exception as e:
            print(f"Error generating crypto chart: {str(e)}")
            dispatcher.utter_message(text=f"📊 Error generating chart for {coin_id}.")
        
        return []
    
    def show_stock_chart(self, dispatcher: CollectingDispatcher, ticker_symbol: str) -> List[Dict[Text, Any]]:
        """Generate chart for stock using yfinance"""
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="7d")
            
            if hist.empty:
                dispatcher.utter_message(text=f"📊 Couldn't fetch data for {ticker_symbol}.")
                return []
            
            labels = [date.strftime("%m/%d") for date in hist.index]
            values = [round(price, 2) for price in hist['Close'].values]
            
            current_price = values[-1]
            first_price = values[0]
            price_change = ((current_price - first_price) / first_price) * 100
            is_positive = price_change >= 0
            
            chart_url = self.generate_quickchart_url(labels, values, f"{ticker_symbol} - 7 Day", is_positive)
            
            emoji = "📈" if is_positive else "📉"
            dispatcher.utter_message(
                text=f"{emoji} {ticker_symbol} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%",
                image=chart_url
            )
            
        except Exception as e:
            print(f"Error generating stock chart: {str(e)}")
            dispatcher.utter_message(text=f"📊 Error generating chart for {ticker_symbol}.")
        
        return []
    
    def show_index_chart(self, dispatcher: CollectingDispatcher, index_name: str, symbol: str) -> List[Dict[Text, Any]]:
        """Generate chart for market index using yfinance (simpler than Alpha Vantage)"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="7d")
            
            if hist.empty:
                dispatcher.utter_message(text=f"📊 Couldn't fetch data for {index_name}.")
                return []
            
            labels = [date.strftime("%m/%d") for date in hist.index]
            values = [round(price, 2) for price in hist['Close'].values]
            
            current_price = values[-1]
            first_price = values[0]
            price_change = ((current_price - first_price) / first_price) * 100
            is_positive = price_change >= 0
            
            display_name = index_name.upper().replace("SP500", "S&P 500").replace("DOW", "Dow Jones")
            chart_url = self.generate_quickchart_url(labels, values, f"{display_name} - 7 Day", is_positive)
            
            emoji = "📈" if is_positive else "📉"
            dispatcher.utter_message(
                text=f"{emoji} {display_name} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%",
                image=chart_url
            )
            
        except Exception as e:
            print(f"Error generating index chart: {str(e)}")
            dispatcher.utter_message(text=f"📊 Error generating chart for {index_name}.")
        
        return []

def _clean_ticker(item: str) -> str:
    """Convert company name or crypto to ticker symbol"""
    company_to_ticker = {
        # Tech Companies
        'apple': 'AAPL',
        'tesla': 'TSLA',
        'microsoft': 'MSFT',
        'google': 'GOOGL',
        'alphabet': 'GOOGL',
        'amazon': 'AMZN',
        'meta': 'META',
        'facebook': 'META',
        'nvidia': 'NVDA',
        'netflix': 'NFLX',
        
        # Additional Tech
        'amd': 'AMD',
        'intel': 'INTC',
        'oracle': 'ORCL',
        'salesforce': 'CRM',
        'adobe': 'ADBE',
        'ibm': 'IBM',
        'cisco': 'CSCO',
        
        # Cryptocurrencies (Yahoo Finance format)
        'bitcoin': 'BTC-USD',
        'btc': 'BTC-USD',
        'ethereum': 'ETH-USD',
        'eth': 'ETH-USD',
        'binance coin': 'BNB-USD',
        'bnb': 'BNB-USD',
        'cardano': 'ADA-USD',
        'ada': 'ADA-USD',
        'solana': 'SOL-USD',
        'sol': 'SOL-USD',
        'ripple': 'XRP-USD',
        'xrp': 'XRP-USD',
        'polkadot': 'DOT-USD',
        'dot': 'DOT-USD',
        'dogecoin': 'DOGE-USD',
        'doge': 'DOGE-USD',
        'avalanche': 'AVAX-USD',
        'avax': 'AVAX-USD',
        'polygon': 'MATIC-USD',
        'matic': 'MATIC-USD',
        'chainlink': 'LINK-USD',
        'link': 'LINK-USD',
        'litecoin': 'LTC-USD',
        'ltc': 'LTC-USD',
        
        # Financial Services
        'jpmorgan': 'JPM',
        'bank of america': 'BAC',
        'wells fargo': 'WFC',
        'goldman sachs': 'GS',
        'morgan stanley': 'MS',
        'visa': 'V',
        'mastercard': 'MA',
        'paypal': 'PYPL',
        
        # Other Major Companies
        'walmart': 'WMT',
        'disney': 'DIS',
        'coca cola': 'KO',
        'pepsi': 'PEP',
        'mcdonalds': 'MCD',
        'nike': 'NKE',
        'starbucks': 'SBUX',
    }
    
    item_lower = item.strip().lower()
    return company_to_ticker.get(item_lower, item.strip().upper())