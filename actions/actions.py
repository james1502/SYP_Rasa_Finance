from typing import Any, Dict, List, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction, UserUttered
import yfinance as yf
from datetime import datetime, timedelta
from difflib import get_close_matches
from .db_connection import mongo_db
import re
import requests
import json
import urllib.parse  
import os  
import logging
from langdetect import detect
#pattern

#check
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

#Corrects typos #check
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

#yahoo market data #no need
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
        noise_words = _get_noise_words()

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
        
        print(corrected_query)
        print(security_name)
        query_to_use = security_name.lower()

        # Extract just the company name from the full query
        company_name = self._extract_company_from_query(query_to_use)
        
        # Convert company name to ticker symbol
        cleaned_ticker =to_alpha_vantage_format(company_name)

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

#
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
#
class ActionFetchComparisonData(Action):
    def name(self) -> Text:
        return "action_fetch_comparison_data"

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
 #       
#
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
#
class ActionFetchMarketNews(Action):
    """Fetch market news using Massive API"""
    
    def name(self) -> Text:
        return "action_fetch_market_news"
    
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
        ticker = to_alpha_vantage_format(news_topic)
        
        # Fetch news from Massive API
        news_data = self._fetch_news_from_massive_api(ticker)
        
        # Format the output
        if news_data:
            news_output = self._format_news_output(news_data, news_topic)
        else:
            news_output = f"Unable to fetch news for {news_topic}. Please try again or specify a different company."
        
        return [SlotSet("news_output", news_output)]
#
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
#
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
        noise_words = _get_noise_words()
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
#
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
        noise_words = _get_noise_words()
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

#yahoo (T&S cinese) #check
def _clean_ticker(item: str) -> str:
    """Convert company/crypto name (English, Traditional Chinese, Simplified Chinese) to Yahoo Finance ticker"""
    company_to_ticker = {
        # Tech Companies
        'apple': 'AAPL',
        '苹果': 'AAPL',           
        '蘋果': 'AAPL',          
        'tesla': 'TSLA',
        '特斯拉': 'TSLA',        
        'microsoft': 'MSFT',
        '微软': 'MSFT',           
        '微軟': 'MSFT',          
        'google': 'GOOGL',
        '谷歌': 'GOOGL',         
        'alphabet': 'GOOGL',
        '字母表': 'GOOGL',        
        '字母表': 'GOOGL',       
        'amazon': 'AMZN',
        '亚马逊': 'AMZN',         
        '亞馬遜': 'AMZN',        
        'meta': 'META',
        'meta': 'META',
        'facebook': 'META',
        '脸书': 'META',           
        '臉書': 'META',          
        'nvidia': 'NVDA',
        '英伟达': 'NVDA',         
        '英偉達': 'NVDA',        
        'netflix': 'NFLX',
        '奈飞': 'NFLX',           
        '奈飛': 'NFLX',          
        
        # Additional Tech
        'amd': 'AMD',
        '超威': 'AMD',           
        'intel': 'INTC',
        '英特尔': 'INTC',         
        '英特爾': 'INTC',        
        'oracle': 'ORCL',
        '甲骨文': 'ORCL',        
        'salesforce': 'CRM',
        '赛富时': 'CRM',          
        '賽富時': 'CRM',         
        'adobe': 'ADBE',
        '奥多比': 'ADBE',         
        '奧多比': 'ADBE',        
        'ibm': 'IBM',
        'ibm': 'IBM',
        'cisco': 'CSCO',
        '思科': 'CSCO',          
        
        # Cryptocurrencies
        'bitcoin': 'BTC-USD',
        'btc': 'BTC-USD',
        '比特币': 'BTC-USD',      
        '比特幣': 'BTC-USD',     
        'ethereum': 'ETH-USD',
        'eth': 'ETH-USD',
        '以太坊': 'ETH-USD',      
        '以太坊': 'ETH-USD',     
        'binance coin': 'BNB-USD',
        'bnb': 'BNB-USD',
        '币安币': 'BNB-USD',      
        '幣安幣': 'BNB-USD',     
        'cardano': 'ADA-USD',
        'ada': 'ADA-USD',
        '卡尔达诺': 'ADA-USD',    
        '卡爾達諾': 'ADA-USD',   
        'solana': 'SOL-USD',
        'sol': 'SOL-USD',
        '索拉纳': 'SOL-USD',      
        '索拉納': 'SOL-USD',     
        'ripple': 'XRP-USD',
        'xrp': 'XRP-USD',
        '瑞波币': 'XRP-USD',      
        '瑞波幣': 'XRP-USD',     
        'polkadot': 'DOT-USD',
        'dot': 'DOT-USD',
        '波卡': 'DOT-USD',       
        'dogecoin': 'DOGE-USD',
        'doge': 'DOGE-USD',
        '狗狗币': 'DOGE-USD',     
        '狗狗幣': 'DOGE-USD',    
        'avalanche': 'AVAX-USD',
        'avax': 'AVAX-USD',
        '雪崩': 'AVAX-USD',      
        'polygon': 'MATIC-USD',
        'matic': 'MATIC-USD',
        '多边形': 'MATIC-USD',    
        '多邊形': 'MATIC-USD',   
        'chainlink': 'LINK-USD',
        'link': 'LINK-USD',
        '链环': 'LINK-USD',       
        '鏈環': 'LINK-USD',      
        'litecoin': 'LTC-USD',
        'ltc': 'LTC-USD',
        '莱特币': 'LTC-USD',      
        '萊特幣': 'LTC-USD',     
        
        # Financial Services
        'jpmorgan': 'JPM',
        '摩根大通': 'JPM',       
        'bank of america': 'BAC',
        '美国银行': 'BAC',        
        '美國銀行': 'BAC',       
        'wells fargo': 'WFC',
        '富国银行': 'WFC',        
        '富國銀行': 'WFC',       
        'goldman sachs': 'GS',
        '高盛': 'GS',            
        'morgan stanley': 'MS',
        '摩根士丹利': 'MS',      
        'visa': 'V',
        'visa': 'V',
        'mastercard': 'MA',
        '万事达': 'MA',           
        '萬事達': 'MA',          
        'paypal': 'PYPL',
        '贝宝': 'PYPL',           
        '貝寶': 'PYPL',          
        
        # Other Major Companies
        'walmart': 'WMT',
        '沃尔玛': 'WMT',          
        '沃爾瑪': 'WMT',         
        'disney': 'DIS',
        '迪士尼': 'DIS',         
        'coca cola': 'KO',
        '可口可乐': 'KO',         
        '可口可樂': 'KO',        
        'pepsi': 'PEP',
        '百事': 'PEP',           
        'mcdonalds': 'MCD',
        '麦当劳': 'MCD',          
        '麥當勞': 'MCD',         
        'nike': 'NKE',
        '耐克': 'NKE',           
        'starbucks': 'SBUX',
        '星巴克': 'SBUX',        
    }
    
    item_lower = item.strip().lower()  # .lower() affects only English letters
    return company_to_ticker.get(item_lower, item.strip().upper())

#check
def to_alpha_vantage_format(item: str) -> str:
    """Convert Yahoo-style ticker to Alpha Vantage format."""
    yahoo_ticker = _clean_ticker(item)  # from your function
    if yahoo_ticker.endswith("-USD"):
        # Remove "-USD" suffix -> e.g., BTC-USD -> BTC
        return yahoo_ticker[:-4]
    # Stocks remain the same
    return yahoo_ticker

# Shared noise words for entity extraction
def _get_noise_words() -> List[str]:
    # ──────────────────────────────────────────────────────────────
    # ENGLISH
    # ──────────────────────────────────────────────────────────────
    english = [
        # Basic question words
        'what', 'is', 'are', 'was', 'were', 'how', 'when', 'where', 'why', 'which',
        'who', 'whom', 'whose', 'does', 'do', 'did', 'has', 'have', 'had',
        
        # Verbs (action words)
        'show', 'tell', 'give', 'get', 'fetch', 'retrieve', 'find', 'search',
        'look', 'see', 'view', 'display', 'print', 'output', 'return',
        'calculate', 'compute', 'determine', 'figure', 'analyze', 'analyse',
        'explain', 'describe', 'define', 'clarify', 'elaborate', 'summarize',
        'compare', 'contrast', 'differentiate', 'distinguish', 'evaluate',
        'assess', 'review', 'check', 'verify', 'confirm', 'validate',
        
        # Prepositions / conjunctions
        'the', 'a', 'an', 'of', 'for', 'to', 'in', 'on', 'at', 'by', 'with',
        'without', 'about', 'regarding', 'concerning', 'per', 'via', 'through',
        'and', 'or', 'but', 'so', 'because', 'as', 'like', 'versus', 'vs',
        'between', 'among', 'within', 'outside', 'including', 'excluding',
        
        # Pronouns & determiners
        'me', 'you', 'him', 'her', 'it', 'us', 'them', 'my', 'your', 'his',
        'her', 'its', 'our', 'their', 'this', 'that', 'these', 'those',
        'some', 'any', 'no', 'every', 'all', 'both', 'each', 'either', 'neither',
        
        # Financial / market terms (to be removed)
        'stock', 'stocks', 'bond', 'bonds', 'etf', 'etfs', 'fund', 'funds',
        'price', 'prices', 'quote', 'quotes', 'value', 'values', 'rate', 'rates',
        'volume', 'volumes', 'market', 'markets', 'index', 'indices', 'benchmark',
        'ticker', 'symbol', 'security', 'securities', 'asset', 'assets',
        'portfolio', 'holdings', 'position', 'positions', 'trade', 'trades',
        'transaction', 'transactions', 'buy', 'sell', 'purchase', 'sale',
        'dividend', 'yield', 'return', 'returns', 'performance', 'growth',
        'profit', 'loss', 'revenue', 'earnings', 'income', 'expense', 'cost',
        
        # Time / period words
        'today', 'yesterday', 'tomorrow', 'now', 'current', 'latest', 'recent',
        'past', 'last', 'next', 'upcoming', 'previous', 'following',
        'day', 'week', 'month', 'year', 'quarter', 'decade', 'ytd', 'ytd',
        'annual', 'yearly', 'monthly', 'weekly', 'daily', 'intraday',
        'historical', 'history', 'past', 'future', 'forecast', 'prediction',
        
        # Data / reporting words
        'data', 'information', 'info', 'details', 'specifics', 'figures',
        'numbers', 'statistics', 'stats', 'metrics', 'indicators', 'measures',
        'report', 'reports', 'reporting', 'update', 'updates', 'news',
        'headlines', 'articles', 'analysis', 'analytics', 'insights',
        'summary', 'overview', 'breakdown', 'details', 'full', 'complete',
        
        # Help / UI / conversational
        'please', 'kindly', 'thanks', 'thank', 'sorry', 'hello', 'hi', 'hey',
        'help', 'support', 'assist', 'guide', 'walk', 'through', 'step',
        'howto', 'tutorial', 'example', 'sample', 'demo', 'try', 'test',
    ]
    
    # ──────────────────────────────────────────────────────────────
    # SIMPLIFIED CHINESE (简体中文)
    # ──────────────────────────────────────────────────────────────
    chinese_simplified = [
        # Question words / pronouns
        '什么', '什么是', '哪个', '哪些', '谁', '谁的', '怎样', '怎么', '如何',
        '为什么', '何时', '何地', '哪里', '哪儿', '这', '这个', '这些', '那', '那个', '那些',
        '我', '我们', '你', '你们', '他', '她', '它', '他们', '她们', '它们',
        
        # Verbs (action)
        '显示', '展示', '呈现', '告诉', '说', '讲', '给', '给我', '获取', '得到',
        '找', '寻找', '查看', '看', '看到', '输出', '返回', '计算', '算出',
        '分析', '解析', '解释', '说明', '描述', '定义', '总结', '概括',
        '比较', '对比', '对照', '评估', '评价', '审查', '检查', '确认', '验证',
        
        # Prepositions / connectors
        '的', '了', '在', '于', '对', '对于', '关于', '有关', '与', '和', '跟',
        '同', '及', '以及', '或', '或者', '但', '但是', '所以', '因为', '由于',
        '像', '例如', '比如', '之间', '之中', '之内', '之外', '包括', '排除',
        
        # Financial / market terms (remove)
        '股票', '证券', '债券', '基金', 'ETF', '价格', '报价', '价值', '数值',
        '费率', '利率', '成交量', '交易量', '市场', '指数', '基准', '代码',
        '符号', '资产', '组合', '持仓', '头寸', '交易', '买卖', '买入', '卖出',
        '股息', '分红', '收益率', '回报', '表现', '增长', '利润', '亏损',
        '收入', '收益', '成本', '费用',
        
        # Time / period
        '今天', '昨天', '明天', '现在', '当前', '最新', '最近', '过去', '上',
        '下', '接下来', '即将', '日', '天', '周', '月', '年', '季度', '年初至今',
        '年度', '每月', '每周', '每日', '历史', '以往', '未来', '预测', '预估',
        
        # Data / reporting
        '数据', '信息', '资料', '细节', '具体', '数字', '统计', '指标', '度量',
        '报告', '报道', '更新', '新闻', '头条', '文章', '分析', '洞察',
        '摘要', '概览', '概况', '完整', '全部',
        
        # Conversational / UI
        '请', '请问', '谢谢', '感谢', '抱歉', '对不起', '你好', '嗨', '帮助',
        '支持', '协助', '指导', '示例', '例子', '试试', '测试',
    ]
    
    # ──────────────────────────────────────────────────────────────
    # TRADITIONAL CHINESE (繁體中文)
    # ──────────────────────────────────────────────────────────────
    chinese_traditional = [
        # Question words / pronouns
        '什麼', '什麼是', '哪個', '哪些', '誰', '誰的', '怎樣', '怎麼', '如何',
        '為什麼', '何時', '何地', '哪裡', '哪兒', '這', '這個', '這些', '那', '那個', '那些',
        '我', '我們', '你', '你們', '他', '她', '它', '他們', '她們', '它們',
        
        # Verbs
        '顯示', '展示', '呈現', '告訴', '說', '講', '給', '給我', '獲取', '得到',
        '找', '尋找', '查看', '看', '看到', '輸出', '返回', '計算', '算出',
        '分析', '解析', '解釋', '說明', '描述', '定義', '總結', '概括',
        '比較', '對比', '對照', '評估', '評價', '審查', '檢查', '確認', '驗證',
        
        # Prepositions / connectors
        '的', '了', '在', '於', '對', '對於', '關於', '有關', '與', '和', '跟',
        '同', '及', '以及', '或', '或者', '但', '但是', '所以', '因為', '由於',
        '像', '例如', '比如', '之間', '之中', '之內', '之外', '包括', '排除',
        
        # Financial / market
        '股票', '證券', '債券', '基金', 'ETF', '價格', '報價', '價值', '數值',
        '費率', '利率', '成交量', '交易量', '市場', '指數', '基準', '代碼',
        '符號', '資產', '組合', '持倉', '頭寸', '交易', '買賣', '買入', '賣出',
        '股息', '分紅', '收益率', '回報', '表現', '增長', '利潤', '虧損',
        '收入', '收益', '成本', '費用',
        
        # Time / period
        '今天', '昨天', '明天', '現在', '當前', '最新', '最近', '過去', '上',
        '下', '接下來', '即將', '日', '天', '週', '月', '年', '季度', '年初至今',
        '年度', '每月', '每週', '每日', '歷史', '以往', '未來', '預測', '預估',
        
        # Data / reporting
        '數據', '資訊', '資料', '細節', '具體', '數字', '統計', '指標', '度量',
        '報告', '報道', '更新', '新聞', '頭條', '文章', '分析', '洞察',
        '摘要', '概覽', '概況', '完整', '全部',
        
        # Conversational / UI
        '請', '請問', '謝謝', '感謝', '抱歉', '對不起', '你好', '嗨', '幫助',
        '支持', '協助', '指導', '示例', '例子', '試試', '測試',
    ]
    
    # Combine and remove duplicates (use set then list)
    all_noise = set(english + chinese_simplified + chinese_traditional)
    return list(all_noise)
##mid trrm

logger = logging.getLogger(__name__)

def _get_current_price(ticker: str) -> float:
    """Get current price from Yahoo Finance"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
        return 0.0
    except Exception as e:
        print(f"Error fetching price for {ticker}: {str(e)}")
        return 0.0


#data fixing
def _parse_date(date_str: str) -> str:
    """Parse various date formats to YYYY-MM-DD"""
    try:
        from datetime import datetime, timedelta
        
        # Handle "today"
        if date_str.lower() == "today":
            return datetime.now().strftime('%Y-%m-%d')
        
        # Handle "yesterday"
        if date_str.lower() == "yesterday":
            return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Try standard formats in order
        date_formats = [
            '%Y-%m-%d',      # 2026-02-14 (ISO format - try FIRST)
            '%d-%m-%Y',      # 14-02-2026
            '%d/%m/%Y',      # 14/02/2026
            '%m/%d/%Y',      # 02/14/2026
            '%Y/%m/%d',      # 2026/02/14
        ]
        
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        # If nothing worked, return as-is and let caller handle error
        print(f"Warning: Could not parse date '{date_str}', returning as-is")
        return date_str
        
    except Exception as e:
        print(f"Error in _parse_date: {e}")
        return date_str

#get historic data
def _get_historical_price(ticker: str, date: str) -> float:
    """Get historical CLOSING price for a specific date"""
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
        today = datetime.now()
        
        if target_date.date() > today.date():
            print(f"Error: Cannot fetch future price for {ticker} on {date}")
            return 0.0
        
        stock = yf.Ticker(ticker)
        
        # Fetch 5 days before and after to handle weekends/holidays
        start_date = target_date - timedelta(days=5)
        end_date = target_date + timedelta(days=5)
        
        hist = stock.history(start=start_date, end=end_date, interval="1d")
        
        if hist.empty:
            print(f"No data for {ticker} around {date}")
            return 0.0
        
        # Find the closest date
        hist.index = hist.index.tz_localize(None)  # Remove timezone
        time_diffs = (hist.index - target_date).to_series().abs()
        closest_idx = time_diffs.argmin()
        closing_price = hist['Close'].iloc[closest_idx]
        
        return round(float(closing_price), 2)
        
    except Exception as e:
        print(f"Error fetching historical price: {e}")
        return 0.0


#save transaction to mongo
class ActionSaveTransaction(Action):
    """Save transaction to MongoDB with historical price from transaction date"""
    
    def name(self) -> Text:
        return "action_save_transaction"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        try:
            # Get slot values
            transaction_type = tracker.get_slot("transaction_type")
            transaction_shares = tracker.get_slot("transaction_shares")
            transaction_asset = tracker.get_slot("transaction_asset")
            transaction_date = tracker.get_slot("transaction_date")
            
            print(f"DEBUG: Slots received - type={transaction_type}, shares={transaction_shares}, asset={transaction_asset}, date={transaction_date}")
            
            # Validate
            if not all([transaction_type, transaction_shares, transaction_asset, transaction_date]):
                dispatcher.utter_message(text="❌ Missing required transaction information.")
                return []
            
            # Convert to ticker
            ticker = _clean_ticker(transaction_asset)
            print(f"DEBUG: Cleaned ticker = {ticker}")
            
            # Parse date
            parsed_date = _parse_date(transaction_date)
            print(f"DEBUG: Parsed date = {parsed_date}")
            
            # Get historical price
            print(f"DEBUG: Fetching historical price for {ticker} on {parsed_date}")
            historical_price = _get_historical_price(ticker, parsed_date)
            print(f"DEBUG: Historical price = {historical_price}")
            
            if historical_price == 0.0:
                dispatcher.utter_message(
                    text=f"❌ Could not fetch historical price for {ticker} on {parsed_date}. "
                        f"Please verify the date and ticker symbol."
                )
                return [
                    SlotSet("transaction_type", None),
                    SlotSet("transaction_shares", None),
                    SlotSet("transaction_asset", None),
                    SlotSet("transaction_date", None)
                ]
            
            # Calculate total value
            total_value = float(transaction_shares) * historical_price
            
            # Create transaction data
            transaction_data = {
                "transaction_type": transaction_type.lower(),
                "amount": float(transaction_shares),
                "asset": ticker,
                "date": parsed_date,
                "price_at_transaction": historical_price
            }
            
            # Save to MongoDB
            print(f"DEBUG: Saving transaction to MongoDB")
            transaction_id = mongo_db.save_transaction(transaction_data)
            print(f"DEBUG: Transaction saved with ID = {transaction_id}")
            
            dispatcher.utter_message(
                text=f"✅ **Transaction Recorded!**\n\n"
                    f"Type: {transaction_type.upper()}\n"
                    f"Asset: {ticker}\n"
                    f"Shares: {transaction_shares}\n"
                    f"Price on {parsed_date}: ${historical_price:.2f}\n"
                    f"Date: {parsed_date}\n"
                    f"Total Value: ${total_value:.2f}"
            )
            
            return [
                SlotSet("transaction_type", None),
                SlotSet("transaction_shares", None),
                SlotSet("transaction_asset", None),
                SlotSet("transaction_date", None)
            ]
            
        except Exception as e:
            print(f"ERROR in ActionSaveTransaction: {str(e)}")
            import traceback
            traceback.print_exc()
            dispatcher.utter_message(text=f"❌ Error processing transaction: {str(e)}")
            return []

#get transaction
class ActionGetTransactions(Action):
    """Retrieve all transactions and calculate portfolio P&L"""
    
    def name(self) -> Text:
        return "action_get_transactions"
    
    def _calculate_positions(self, transactions: List[Dict]) -> Dict:
        """Calculate positions and P&L by asset"""
        positions = {}
        
        for txn in transactions:
            asset = txn['asset']
            txn_type = txn['transaction_type']
            amount = txn['amount']
            price = txn.get('price_at_transaction', 0)
            
            if asset not in positions:
                positions[asset] = {
                    'shares': 0,
                    'total_cost': 0,
                    'transactions': []
                }
            
            positions[asset]['transactions'].append(txn)
            
            if txn_type == 'buy':
                positions[asset]['shares'] += amount
                positions[asset]['total_cost'] += (amount * price)
            elif txn_type == 'sell':
                positions[asset]['shares'] -= amount
                positions[asset]['total_cost'] -= (amount * price)
        
        # Calculate P&L with current prices
        for asset, data in positions.items():
            current_price = _get_current_price(asset)
            current_value = data['shares'] * current_price
            total_cost = data['total_cost']
            pnl = current_value - total_cost
            pnl_percent = (pnl / total_cost * 100) if total_cost != 0 else 0
            
            data['current_price'] = current_price
            data['current_value'] = current_value
            data['pnl'] = pnl
            data['pnl_percent'] = pnl_percent
            data['avg_cost'] = total_cost / data['shares'] if data['shares'] != 0 else 0
        
        return positions
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        # Get all transactions
        transactions = mongo_db.get_all_transactions()
        
        if not transactions:
            dispatcher.utter_message(
                text="📊 **Your Portfolio**\n\nNo transactions recorded yet.\n\n"
                     "Start by recording a buy or sell transaction!"
            )
            return []
        
        # Calculate positions
        positions = self._calculate_positions(transactions)
        
        # Build message
        message = "📊 **Your Portfolio**\n\n"
        
        total_pnl = 0
        total_value = 0
        total_cost = 0
        
        for asset, data in sorted(positions.items()):
            shares = data['shares']
            
            # Skip if position is closed
            if shares == 0:
                continue
            
            current_price = data['current_price']
            current_value = data['current_value']
            avg_cost = data['avg_cost']
            pnl = data['pnl']
            pnl_percent = data['pnl_percent']
            
            total_pnl += pnl
            total_value += current_value
            total_cost += data['total_cost']
            
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            
            message += f"**{asset}**\n"
            message += f"  Shares: {shares:.4f}\n"
            message += f"  Avg Cost: ${avg_cost:.2f}\n"
            message += f"  Current: ${current_price:.2f}\n"
            message += f"  Value: ${current_value:.2f}\n"
            message += f"  P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%) {pnl_emoji}\n\n"
        
        # Summary
        total_pnl_percent = (total_pnl / total_cost * 100) if total_cost != 0 else 0
        summary_emoji = "📈" if total_pnl >= 0 else "📉"
        
        message += "━━━━━━━━━━━━━━━━━━━━\n"
        message += f"**Portfolio Summary**\n"
        message += f"Total Value: ${total_value:.2f}\n"
        message += f"Total Cost: ${total_cost:.2f}\n"
        message += f"Total P&L: ${total_pnl:+.2f} ({total_pnl_percent:+.2f}%) {summary_emoji}\n"
        message += f"Transactions: {len(transactions)}"
        
        dispatcher.utter_message(text=message)
        return []

#
class ActionGetTransactionsByAsset(Action):
    """Get transactions and P&L for a specific asset"""
    
    def name(self) -> Text:
        return "action_get_transactions_by_asset"
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        filter_asset = tracker.get_slot("filter_asset")
        
        if not filter_asset:
            dispatcher.utter_message(text="Please specify which asset to filter by.")
            return []
        
        # Convert to ticker
        ticker = _clean_ticker(filter_asset)
        
        # Get transactions
        transactions = mongo_db.get_transactions_by_asset(ticker)
        
        if not transactions:
            dispatcher.utter_message(text=f"No transactions found for {ticker}.")
            return [SlotSet("filter_asset", None)]
        
        # Calculate position
        total_shares = 0
        total_cost = 0
        buy_count = 0
        sell_count = 0
        
        for txn in transactions:
            txn_type = txn['transaction_type']
            amount = txn['amount']
            price = txn.get('price_at_transaction', 0)
            
            if txn_type == 'buy':
                total_shares += amount
                total_cost += (amount * price)
                buy_count += 1
            elif txn_type == 'sell':
                total_shares -= amount
                total_cost -= (amount * price)
                sell_count += 1
        
        # Get current price and calculate P&L
        current_price = _get_current_price(ticker)
        current_value = total_shares * current_price
        pnl = current_value - total_cost
        pnl_percent = (pnl / total_cost * 100) if total_cost != 0 else 0
        avg_cost = total_cost / total_shares if total_shares != 0 else 0
        
        # Build message
        message = f"📊 **{ticker} Transaction History**\n\n"
        
        # Transaction list
        for txn in sorted(transactions, key=lambda x: x['date'], reverse=True):
            txn_type = txn['transaction_type'].upper()
            amount = txn['amount']
            date = txn['date']
            price = txn.get('price_at_transaction', 0)
            value = amount * price
            
            emoji = "🟢" if txn_type == "BUY" else "🔴"
            message += f"{emoji} {txn_type}: {amount:.4f} @ ${price:.2f} = ${value:.2f}\n"
            message += f"   Date: {date}\n\n"
        
        # Position summary
        message += "━━━━━━━━━━━━━━━━━━━━\n"
        message += f"**Current Position**\n"
        message += f"Shares: {total_shares:.4f}\n"
        message += f"Avg Cost: ${avg_cost:.2f}\n"
        message += f"Current Price: ${current_price:.2f}\n"
        message += f"Current Value: ${current_value:.2f}\n"
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        message += f"P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%) {pnl_emoji}\n\n"
        message += f"Transactions: {buy_count} buys, {sell_count} sells"
        
        dispatcher.utter_message(text=message)
        return [SlotSet("filter_asset", None)]
