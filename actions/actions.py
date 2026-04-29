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
import jieba
import re


#split
def tokenize_query(query: str) -> list:
    """Return a list of tokens (words) from a query, handling both English and Chinese."""
    if not query:
        return []
    
    # Check if the string contains Chinese characters (Unicode range 4E00-9FFF)
    if re.search(r'[\u4e00-\u9fff]', query):
        # Chinese – use jieba for segmentation
        tokens = list(jieba.cut(query))
        # Remove spaces and empty strings
        tokens = [t.strip() for t in tokens if t.strip()]
        return tokens
    else:
        # English or other space-separated languages
        return query.lower().split()


def detect_user_language(text: str) -> str:
    """Detect user language as en, zh-TW, or zh-CN from current input text."""
    if not text:
        return "en"

    if not re.search(r"[\u4e00-\u9fff]", text):
        return "en"

    # Heuristic script hints for Traditional vs Simplified Chinese.
    traditional_hints = "繁體臺萬與為國龍這個嗎麼" 
    simplified_hints = "简体台万与为国龙这个吗么" 

    trad_score = sum(ch in traditional_hints for ch in text)
    simp_score = sum(ch in simplified_hints for ch in text)

    if simp_score > trad_score:
        return "zh-CN"

    return "zh-TW"
    
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


def _is_direct_ticker_mapping(candidate: str) -> bool:
    """Return True when candidate can be normalized into a known ticker mapping."""
    if not candidate:
        return False

    normalized = _clean_ticker(candidate)
    # _clean_ticker falls back to uppercased input when it cannot map.
    return normalized != candidate.strip().upper()


def _extract_best_entity_candidate(query: str) -> str:
    """Extract entity candidate robustly for Chinese and English queries."""
    if not query:
        return None

    stripped_query = query.strip()
    if _is_direct_ticker_mapping(stripped_query):
        return stripped_query

    tokens = tokenize_query(query)
    noise_words = set(_get_noise_words())
    cleaned_tokens = [t for t in tokens if t not in noise_words]

    if not cleaned_tokens:
        return None

    merged_candidates = ["".join(cleaned_tokens), " ".join(cleaned_tokens)]
    for candidate in merged_candidates + cleaned_tokens:
        if _is_direct_ticker_mapping(candidate):
            return candidate

    return cleaned_tokens[0]

# EXTRAc

class ActionExtractSecurityName(Action):
    """Extract security name from user message"""
    
    def name(self) -> Text:
        return "action_extract_security_name"
    
    def _extract_company_from_query(self, query: str) -> str:
        """Extract just the company name from a query"""
        return _extract_best_entity_candidate(query)
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        # Use corrected query if available
        query_to_use = corrected_query if corrected_query else user_message
        
        # Extract company name
        company_name = self._extract_company_from_query(query_to_use)
        
        if company_name:
            # Convert to ticker
            ticker = _clean_ticker(company_name)
            return [SlotSet("security_name", ticker)]
        
        return [SlotSet("security_name", None)]

class ActionExtractIndexName(Action):
    """Extract index name from user message"""
    
    def name(self) -> Text:
        return "action_extract_index_name"
    
    def _extract_index_from_query(self, query: str) -> str:
        """Extract index name from query"""
        if not query:
            return None
        tokens = tokenize_query(query)
        noise_words = set(_get_noise_words())
        cleaned_tokens = [t for t in tokens if t not in noise_words]
        
        # Rebuild the query without noise words
        cleaned_query = " ".join(cleaned_tokens)
        # Check for known indexes
        if 's&p' in cleaned_query or 'sp' in cleaned_query or 's and p' in cleaned_query:
            return 's&p 500'
        elif 'nasdaq' in cleaned_query:
            return 'nasdaq'
        elif 'dow' in cleaned_query:
            return 'dow jones'
        elif 'russell' in cleaned_query:
            return 'russell 2000'
        elif 'ftse' in cleaned_query:
            return 'ftse 100'
        
        return cleaned_tokens[0] if cleaned_tokens else None
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        query_to_use = corrected_query if corrected_query else user_message
        
        index_name = self._extract_index_from_query(query_to_use)
        
        return [SlotSet("index_name", index_name)]

class ActionExtractNewsTopic(Action):
    """Extract news topic from user message"""
    
    def name(self) -> Text:
        return "action_extract_news_topic"
    
    def _extract_topic_from_query(self, query: str) -> str:
        """Extract topic from news query"""
        if not query:
            return None
        
        tokens = tokenize_query(query) 
        noise_words = set(_get_noise_words())
        cleaned = [t for t in tokens if t not in noise_words]
        return cleaned[0] if cleaned else None
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        query_to_use = corrected_query if corrected_query else user_message
        
        topic = self._extract_topic_from_query(query_to_use)
        
        return [SlotSet("news_topic", topic)]

class ActionExtractComparisonItems(Action):
    """Extract comparison items from user message"""
    
    def name(self) -> Text:
        return "action_extract_comparison_items"
    
    def _extract_companies_from_text(self, text: str) -> str:
        if not text:
            return None
        
        normalized = text.lower()
        tokens = tokenize_query(text)
        noise_words = set(_get_noise_words())
        
        # Remove noise words and keep only potential company names
        cleaned_tokens = [t for t in tokens if t not in noise_words]
        
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
    
        
        
        # Company name to ticker mapping

        
        index_to_ticker = {
            's&p 500': '^GSPC',
            's&p500': '^GSPC',
            'sp500': '^GSPC',
            's and p 500': '^GSPC',
            's&p': '^GSPC',
            'nasdaq': '^IXIC',
            'nasdaq composite': '^IXIC',
            'qqq': '^IXIC',
            'dow jones': '^DJI',
            'djia': '^DJI',
            'russell 2000': '^RUT',
            'ftse 100': '^FTSE',
        }

        found_tickers = []

        for phrase, ticker in index_to_ticker.items():
            if phrase in normalized and ticker not in found_tickers:
                found_tickers.append(ticker)

        for token in cleaned_tokens:
            ticker = company_to_ticker.get(token)
            if ticker and ticker not in found_tickers:
                found_tickers.append(ticker)
            # Also allow direct ticker symbols (e.g., "AAPL")
            elif token.upper() in company_to_ticker.values():
                ticker = token.upper()
                if ticker not in found_tickers:
                    found_tickers.append(ticker)
        
        if len(found_tickers) >= 2:
            return ", ".join(found_tickers[:2])
        
        return None

    def _extract_comparison_criteria(self, text: str) -> str:
        """Infer a comparison criterion or timeframe from the user's message."""
        if not text:
            return None

        normalized = text.lower()

        if any(keyword in normalized for keyword in ["trend", "trends", "performance", "perform", "how are they doing"]):
            return "last month"
        if any(keyword in normalized for keyword in ["ytd", "year to date", "year-to-date", "this year"]):
            return "year-to-date"
        if any(keyword in normalized for keyword in ["volatility", "volatile", "risk"]):
            return "volatility"
        if any(keyword in normalized for keyword in ["week", "last 7 days", "7 days"]):
            return "last week"
        if any(keyword in normalized for keyword in ["month", "last 30 days", "30 days"]):
            return "last month"

        return None
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        query_to_use = corrected_query if corrected_query else user_message
        
        comparison_items = self._extract_companies_from_text(query_to_use)
        comparison_criteria = self._extract_comparison_criteria(query_to_use)

        events = [SlotSet("comparison_items", comparison_items)]
        if comparison_criteria:
            events.append(SlotSet("comparison_criteria", comparison_criteria))

        return events

class ActionExtractAnalysisCompany(Action):
    """Extract company name for analysis from user message"""
    
    def name(self) -> Text:
        return "action_extract_analysis_company"
    
    def _extract_company_from_query(self, query: str) -> str:
        """Extract company name from analysis query"""
        return _extract_best_entity_candidate(query)
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        query_to_use = corrected_query if corrected_query else user_message
        
        company_name = self._extract_company_from_query(query_to_use)
        
        if company_name:
            ticker = _clean_ticker(company_name)
            return [SlotSet("analysis_company", ticker)]
        
        return [SlotSet("analysis_company", None)]

class ActionExtractChartAsset(Action):
    """Extract asset name for chart from user message"""
    
    def name(self) -> Text:
        return "action_extract_chart_asset"
    
    def _extract_asset_from_query(self, query: str) -> str:
        """Extract asset name from chart query"""
        return _extract_best_entity_candidate(query)
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        user_message = tracker.latest_message.get('text', '')
        corrected_query = tracker.get_slot("corrected_query")
        
        query_to_use = corrected_query if corrected_query else user_message
        
        asset_name = self._extract_asset_from_query(query_to_use)
        
        return [SlotSet("chart_asset", asset_name)]


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
        detected_language = detect_user_language(user_message)
        corrected_message, has_correction = self._correct_text(user_message)
        logging.getLogger(__name__).info("Typo correction evaluated text=%r", user_message)

        events: List[Dict[Text, Any]] = []

        lowered_message = user_message.lower()
        suppress_correction_message = any(
            keyword in lowered_message
            for keyword in ["compare", " vs ", " versus ", "difference between", "trend", "trends"]
        )
        
        if has_correction and not suppress_correction_message:
            message = f"I understood: '{corrected_message}'"
            dispatcher.utter_message(
                text=message
            )
            events.append(SlotSet("corrected_query", corrected_message))
            events.append(SlotSet("language", detected_language))
            return events

        if has_correction:
            events.append(SlotSet("corrected_query", corrected_message))
            events.append(SlotSet("language", detected_language))
            return events
        
        # No correction needed - store original
        events.append(SlotSet("corrected_query", user_message))
        events.append(SlotSet("language", detected_language))
        return events    

# matketdata (alpha)

class ActionFetchMarketData(Action):
    """Fetch market data - Alpha Vantage with automatic key rotation on rate limit"""
    
    def name(self) -> Text:
        return "action_fetch_market_data"
    
    def _get_alpha_vantage_keys(self) -> List[str]:
        """Get list of Alpha Vantage API keys from environment"""
        keys = []
        
        # Primary key
        primary_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if primary_key:
            keys.append(primary_key)
        
        # Backup keys (ALPHA_VANTAGE_API_KEY_2, ALPHA_VANTAGE_API_KEY_3, etc.)
        i = 2
        while True:
            backup_key = os.getenv(f"ALPHA_VANTAGE_API_KEY_{i}")
            if backup_key:
                keys.append(backup_key)
                i += 1
            else:
                break
        
        return keys
    
    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        security_name = tracker.get_slot("security_name")
        print(security_name)
        if not security_name or len(security_name) < 2:
            message = "I couldn't identify a valid ticker. Please provide a ticker symbol."
            return [
                SlotSet("market_data_output", message),
                SlotSet("security_name", None)
            ]
        
        
        cleaned_yahoo = _clean_ticker(security_name)
        if cleaned_yahoo.endswith('-USD'):
            return self._fetch_crypto_data_yfinance(cleaned_yahoo, dispatcher)
        else:
            alpha_ticker = to_alpha_vantage_format(security_name)
            return self._fetch_stock_data_alpha_vantage(alpha_ticker, dispatcher)
    def _fetch_crypto_data_yfinance(
        self, 
        crypto_ticker: str, 
        dispatcher: CollectingDispatcher
    ) -> List[Dict[Text, Any]]:
        """Fetch cryptocurrency data using yfinance"""
        
        try:
            ticker = yf.Ticker(crypto_ticker)
            info = ticker.info
            hist = ticker.history(period="1y")
            
            if hist.empty:
                raise ValueError(f"No data available for {crypto_ticker}")
            
            # Extract data
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]
            volume = info.get('volume') or info.get('regularMarketVolume') or hist['Volume'].iloc[-1]
            day_high = info.get('dayHigh') or info.get('regularMarketDayHigh') or hist['High'].iloc[-1]
            day_low = info.get('dayLow') or info.get('regularMarketDayLow') or hist['Low'].iloc[-1]
            
            # Calculate change
            previous_close = info.get('previousClose') or hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else 0
            
            # 52-week high/low
            high_52week = hist['High'].max()
            low_52week = hist['Low'].min()
            
            market_data = (
                f"💰 {crypto_ticker}\n\n"
                f"Current Price: ${current_price:,.2f}\n"
                f"Change: ${change:+,.2f} ({change_percent:+.2f}%)\n"
                f"24h Volume: {int(volume):,}\n"
                f"Day High: ${day_high:,.2f}\n"
                f"Day Low: ${day_low:,.2f}\n"
                f"52-Week High: ${high_52week:,.2f}\n"
                f"52-Week Low: ${low_52week:,.2f}"
            )
            
        except Exception as e:
            print(f"Error fetching crypto data for {crypto_ticker}: {str(e)}")
            market_data = f"Unable to fetch data for {crypto_ticker}."
        
        return [
            SlotSet("market_data_output", market_data),
            SlotSet("security_name", crypto_ticker)
        ]
    
    def _fetch_stock_data_alpha_vantage(
        self, 
        ticker: str, 
        dispatcher: CollectingDispatcher
    ) -> List[Dict[Text, Any]]:
        """Fetch real-time stock data using Alpha Vantage with automatic key rotation"""
        
        api_keys = self._get_alpha_vantage_keys()
        
        if not api_keys:
            market_data = "No Alpha Vantage API keys configured. Please set ALPHA_VANTAGE_API_KEY."
            return [
                SlotSet("market_data_output", market_data),
                SlotSet("security_name", ticker)
            ]
        
        quote_url = "https://www.alphavantage.co/query"
        last_error = None
        
        # Try each API key in sequence
        for key_index, api_key in enumerate(api_keys, 1):
            try:
                print(f"Attempting Alpha Vantage request with API key #{key_index}")
                
                quote_params = {
                    "function": "GLOBAL_QUOTE",
                    "symbol": ticker,
                    "apikey": api_key
                }
                
                quote_response = requests.get(quote_url, params=quote_params, timeout=10)
                quote_data = quote_response.json()
                
                # Check for rate limit
                if "Note" in quote_data:
                    rate_limit_msg = quote_data.get("Note", "")
                    print(f"API key #{key_index} hit rate limit: {rate_limit_msg}")
                    last_error = "Rate limit reached"
                    
                    # Try next key if available
                    if key_index < len(api_keys):
                        print(f"Trying backup API key #{key_index + 1}...")
                        continue
                    else:
                        # All keys exhausted, fallback to yfinance
                        print("All Alpha Vantage API keys exhausted. Falling back to yfinance...")
                        return self._fetch_stock_data_yfinance_fallback(ticker, dispatcher)
                
                # Check for invalid ticker
                if "Error Message" in quote_data:
                    raise ValueError(f"Invalid ticker symbol: {ticker}")
                
                # Check for empty response
                if "Global Quote" not in quote_data or not quote_data["Global Quote"]:
                    raise ValueError(f"No data available for {ticker}")
                
                # Success! Extract data
                quote = quote_data["Global Quote"]
                
                current_price = float(quote.get("05. price", 0))
                volume = int(quote.get("06. volume", 0))
                day_high = float(quote.get("03. high", 0))
                day_low = float(quote.get("04. low", 0))
                previous_close = float(quote.get("08. previous close", 0))
                change = float(quote.get("09. change", 0))
                change_percent = float(quote.get("10. change percent", "0").replace("%", ""))
                
                # Get 52-week high/low from yfinance
                try:
                    yf_ticker = yf.Ticker(ticker)
                    hist = yf_ticker.history(period="1y")
                    
                    if not hist.empty:
                        high_52week = hist['High'].max()
                        low_52week = hist['Low'].min()
                    else:
                        high_52week = day_high
                        low_52week = day_low
                except:
                    high_52week = day_high
                    low_52week = day_low
                
                print(f"Successfully fetched data using API key #{key_index}")
                
                market_data = (
                    f"📊 {ticker}\n\n"
                    f"Current Price: ${current_price:.2f}\n"
                    f"Change: ${change:+.2f} ({change_percent:+.2f}%)\n"
                    f"Volume: {volume:,}\n"
                    f"Day High: ${day_high:.2f}\n"
                    f"Day Low: ${day_low:.2f}\n"
                    f"52-Week High: ${high_52week:.2f}\n"
                    f"52-Week Low: ${low_52week:.2f}"
                )
                
                return [
                    SlotSet("market_data_output", market_data),
                    SlotSet("security_name", ticker)
                ]
                
            except requests.exceptions.RequestException as e:
                print(f"Network error with API key #{key_index}: {str(e)}")
                last_error = str(e)
                
                # Try next key if available
                if key_index < len(api_keys):
                    continue
                else:
                    # All keys failed, fallback to yfinance
                    print("All Alpha Vantage API keys failed. Falling back to yfinance...")
                    return self._fetch_stock_data_yfinance_fallback(ticker, dispatcher)
                    
            except ValueError as e:
                # Don't retry on invalid ticker
                print(f"ValueError: {str(e)}")
                market_data = str(e)
                return [
                    SlotSet("market_data_output", market_data),
                    SlotSet("security_name", ticker)
                ]
                
            except Exception as e:
                print(f"Unexpected error with API key #{key_index}: {str(e)}")
                last_error = str(e)
                
                # Try next key if available
                if key_index < len(api_keys):
                    continue
                else:
                    # All keys failed, fallback to yfinance
                    print("All Alpha Vantage API keys failed. Falling back to yfinance...")
                    return self._fetch_stock_data_yfinance_fallback(ticker, dispatcher)
        
        # Should not reach here, but just in case
        market_data = f"Unable to fetch data for {ticker}. Last error: {last_error}"
        return [
            SlotSet("market_data_output", market_data),
            SlotSet("security_name", ticker)
        ]
    
    def _fetch_stock_data_yfinance_fallback(
        self, 
        ticker: str, 
        dispatcher: CollectingDispatcher
    ) -> List[Dict[Text, Any]]:
        """Fallback to yfinance when all Alpha Vantage keys are exhausted"""
        
        try:
            print(f"Using yfinance fallback for {ticker}")
            
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.info
            hist = yf_ticker.history(period="1y")
            
            if hist.empty:
                raise ValueError(f"No data available for {ticker}")
            
            # Extract data
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or hist['Close'].iloc[-1]
            volume = info.get('volume') or info.get('regularMarketVolume') or hist['Volume'].iloc[-1]
            day_high = info.get('dayHigh') or info.get('regularMarketDayHigh') or hist['High'].iloc[-1]
            day_low = info.get('dayLow') or info.get('regularMarketDayLow') or hist['Low'].iloc[-1]
            
            # Calculate change
            previous_close = info.get('previousClose') or hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            change = current_price - previous_close
            change_percent = (change / previous_close * 100) if previous_close != 0 else 0
            
            # 52-week high/low
            high_52week = hist['High'].max()
            low_52week = hist['Low'].min()
            
            market_data = (
                f"📊 {ticker} (via backup source)\n\n"
                f"Current Price: ${current_price:.2f}\n"
                f"Change: ${change:+.2f} ({change_percent:+.2f}%)\n"
                f"Volume: {int(volume):,}\n"
                f"Day High: ${day_high:.2f}\n"
                f"Day Low: ${day_low:.2f}\n"
                f"52-Week High: ${high_52week:.2f}\n"
                f"52-Week Low: ${low_52week:.2f}"
            )
            
        except Exception as e:
            print(f"Yfinance fallback also failed for {ticker}: {str(e)}")
            market_data = f"Unable to fetch data for {ticker}. Please try again later."
        
        return [
            SlotSet("market_data_output", market_data),
            SlotSet("security_name", ticker)
        ]
# index info (yqhoo

class ActionFetchIndexInfo(Action):
    """Fetch index information"""
    
    def name(self) -> Text:
        return "action_fetch_index_info"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        index_name = tracker.get_slot("index_name")
        print(index_name)
        if not index_name:
            return [SlotSet("index_info_output", "Please specify which index you'd like information about.")]
        
        # Map common index names to Yahoo Finance tickers
        index_mapping = {
            # S&P 500 variations
            "s&p 500": "^GSPC",
            "s&p500": "^GSPC",
            "sp500": "^GSPC",
            "s and p 500": "^GSPC",
            "s&p": "^GSPC",
            "spy": "^GSPC",
            
            # Dow Jones variations
            "dow jones": "^DJI",
            "dow": "^DJI",
            "djia": "^DJI",
            "dia": "^DJI",
            
            # NASDAQ variations
            "nasdaq": "^IXIC",
            "nasdaq composite": "^IXIC",
            "qqq": "^IXIC",
            
            # Russell variations
            "russell 2000": "^RUT",
            "russell": "^RUT",
            "iwm": "^RUT",
            
            # FTSE variations
            "ftse 100": "^FTSE",
            "ftse": "^FTSE",
            "ftse100": "^FTSE",
            
            # International indices
            "nikkei": "^N225",
            "nikkei 225": "^N225",
            
            # Broad market ETFs (can also track these)
            "voo": "VOO",
            "vti": "VTI",
            "vt": "VT",
            "vxus": "VXUS",
            
            # Emerging markets
            "eem": "EEM",
            "emerging": "EEM",
            "vwo": "VWO",
            "iefa": "IEFA",
            "efa": "EFA",
            
            # Sector ETFs
            "xlk": "XLK",  # Technology
            "xlf": "XLF",  # Financials
            "xle": "XLE",  # Energy
            "xlv": "XLV",  # Healthcare
            "xly": "XLY",  # Consumer Discretionary
            "xlp": "XLP",  # Consumer Staples
            "xli": "XLI",  # Industrials
            "xlb": "XLB",  # Materials
            "xlre": "XLRE",  # Real Estate
            "xlu": "XLU",  # Utilities
            
            # ARK ETFs
            "arkk": "ARKK",
            "arkw": "ARKW",
            "arkg": "ARKG",
            "arkf": "ARKF",
            "arkq": "ARKQ",
            
            # Commodity ETFs
            "gld": "GLD",  # Gold
            "slv": "SLV",  # Silver
            "uso": "USO",  # Oil
            "ung": "UNG",  # Natural Gas
            
            # Bond ETFs
            "tlt": "TLT",  # 20+ Year Treasury
            "ief": "IEF",  # 7-10 Year Treasury
            "shy": "SHY",  # 1-3 Year Treasury
            "hyg": "HYG",  # High Yield Corporate
            "lqd": "LQD",  # Investment Grade Corporate
            "jnk": "JNK",  # High Yield
            "emb": "EMB",  # Emerging Market Bonds
            "mub": "MUB",  # Municipal Bonds
        }
        
        # Clean and normalize the index name
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

# news (alpha)
class ActionFetchMarketNews(Action):
    """Fetch market news using Alpha Vantage API"""
    
    def name(self) -> Text:
        return "action_fetch_market_news"
    
    def _format_news_output(self, news_data: List[Dict], topic: str) -> str:
        """Format news data into readable output"""
        if not news_data:
            return f"No recent news found for {topic}."
        
        # Take top 5 news items
        news_items = news_data[:5]
        formatted_news = [f"Latest news about {topic}:\n"]
        
        for idx, item in enumerate(news_items, 1):
            title = item.get('title', 'No title')
            date = item.get('time_published', 'Unknown date')
            summary = item.get('summary', '')
            
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
        
        API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
        
        news_topic = tracker.get_slot("news_topic")
        print(news_topic)
        if not news_topic:
            news_output = "Please specify what topic or company you'd like news about."
            return [SlotSet("news_output", news_output)]
        
        # Convert topic to ticker if it's a company name
        ticker = to_alpha_vantage_format(news_topic)
        
        try:
            base_url = "https://www.alphavantage.co/query"
            
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "apikey": API_KEY,
                "sort": "LATEST"
            }
            
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if "feed" in data:
                news_data = data["feed"]
                news_output = self._format_news_output(news_data, news_topic)
            else:
                news_output = f"Unable to fetch news for {news_topic}. Please try again later."
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching news: {str(e)}")
            news_output = f"Unable to fetch news for {news_topic}. Please try again later."
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            news_output = f"Unable to fetch news for {news_topic}."
        
        return [SlotSet("news_output", news_output)]

# compare

class ActionFetchComparisonData(Action):
    """Compare performance between securities using Alpha Vantage"""
    
    def name(self) -> Text:
        return "action_fetch_comparison_data"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "YOUR_API_KEY_HERE")
        
        comparison_items = tracker.get_slot("comparison_items")
        comparison_criteria = tracker.get_slot("comparison_criteria")
        print(f"comparison_items={comparison_items}")
        print(f"comparison_criteria={comparison_criteria}")
        
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
            percentages = []
            
            for item in items:
                ticker_symbol = _clean_ticker(item)
                
                try:
                    # Use yfinance for comparison (more reliable for historical data)
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period=period)
                    
                    if not hist.empty:
                        start_price = hist['Close'].iloc[0]
                        end_price = hist['Close'].iloc[-1]
                        return_pct = ((end_price - start_price) / start_price * 100)
                        
                        comparison_results.append(
                            f"{item.strip()}: {return_pct:+.2f}% (${end_price:.2f})"
                        )
                        percentages.append(return_pct)
                    else:
                        comparison_results.append(f"{item.strip()}: No data")
                        percentages.append(float('-inf'))
                        
                except Exception as ticker_error:
                    print(f"Error fetching data for {item}: {str(ticker_error)}")
                    comparison_results.append(f"{item.strip()}: Error")
                    percentages.append(float('-inf'))
            
            # Build output
            comparison_output = f"📊 **{period.upper()} Performance Comparison**\n\n"
            comparison_output += "\n".join(comparison_results)
            
            # Add winner summary
            if len(comparison_results) == 2 and len(percentages) == 2:
                winner_idx = 0 if percentages[0] > percentages[1] else 1
                comparison_output += f"\n\n✨ **Winner:** {items[winner_idx]}"
            
        except Exception as e:
            print(f"Error in comparison: {str(e)}")
            comparison_output = "Unable to perform comparison."
        
        return [SlotSet("comparison_output", comparison_output)]

#analysis

class ActionFetchAnalysis(Action):
    """Fetch comprehensive financial analysis with Ollama-generated summary"""
    
    def name(self) -> Text:
        return "action_fetch_analysis"
    
    def _generate_ollama_summary(
        self, 
        company_name: str,
        ticker: str,
        current_price: float,
        ytd_return: float,
        month_return: float,
        market_cap: float,
        pe_ratio: float,
        indicators: Dict
    ) -> str:
        """Generate executive summary using Ollama"""
        
        try:
            # Ollama API endpoint
            ollama_url = "http://localhost:11434/api/generate"
            
            # Prepare data for LLM
            rsi = indicators.get('rsi', 50) if indicators else 50
            sma_20 = indicators.get('sma_20', current_price) if indicators else current_price
            sma_50 = indicators.get('sma_50', current_price) if indicators else current_price
            
            # Determine trend
            if current_price > sma_20 > sma_50:
                trend = "strong uptrend"
            elif current_price > sma_20:
                trend = "moderate uptrend"
            elif current_price < sma_20 < sma_50:
                trend = "strong downtrend"
            elif current_price < sma_20:
                trend = "moderate downtrend"
            else:
                trend = "sideways/neutral"
            
            # Create prompt
            prompt = f"""You are a financial analyst. Write a concise 2-3 sentence executive summary for {company_name} ({ticker}) based on the following data:

- Current Price: ${current_price:.2f}
- Market Cap: ${market_cap:,.0f}
- YTD Return: {ytd_return:+.2f}%
- 1-Month Return: {month_return:+.2f}%
- P/E Ratio: {pe_ratio if pe_ratio else 'N/A'}
- RSI (14): {rsi:.1f}
- Trend: {trend}

Write a professional, objective summary that highlights the key performance and technical indicators. Focus on facts, not recommendations. Keep it under 100 words. Do not include any preamble or explanation, just provide the summary."""

            # Call Ollama APIS
            payload = {
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 150
                }
            }
            
            response = requests.post(
                ollama_url, 
                json=payload, 
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result.get('response', '').strip()
                
                # Clean up the response
                summary = summary.replace("Here is the summary:", "").strip()
                summary = summary.replace("Here's the summary:", "").strip()
                
                return summary if summary else self._template_summary(ytd_return)
            else:
                print(f"Ollama API error: {response.status_code}")
                return self._template_summary(ytd_return)
            
        except requests.exceptions.Timeout:
            print("Ollama API timeout - using template summary")
            return self._template_summary(ytd_return)
        except Exception as e:
            print(f"Error generating Ollama summary: {str(e)}")
            return self._template_summary(ytd_return)
    
    def _template_summary(self, ytd_return: float) -> str:
        """Fallback template-based summary"""
        if ytd_return > 20:
            return f"The stock has shown exceptional year-to-date performance with a {ytd_return:+.2f}% gain."
        elif ytd_return > 10:
            return f"The stock has delivered strong year-to-date returns of {ytd_return:+.2f}%."
        elif ytd_return > 0:
            return f"The stock has posted modest year-to-date gains of {ytd_return:+.2f}%."
        else:
            return f"The stock has experienced a year-to-date decline of {ytd_return:.2f}%."
    
    def _calculate_technical_indicators(self, hist) -> Dict:
        """Calculate technical indicators"""
        if hist.empty or len(hist) < 50:
            return {}
        
        # Simple Moving Averages
        sma_20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        sma_50 = hist['Close'].rolling(window=50).mean().iloc[-1]
        
        # RSI
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs.iloc[ -1]))
        
        return {
            'sma_20': sma_20,
            'sma_50': sma_50,
            'rsi': rsi
        }
    
    def _get_trend_signal(self, current_price: float, sma_20: float, sma_50: float) -> str:
        """Determine trend"""
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
        """Interpret RSI"""
        if rsi > 70:
            return "Overbought ⚠️"
        elif rsi < 30:
            return "Oversold 💡"
        else:
            return "Neutral"
    
    def _format_large_number(self, num: float) -> str:
        """Format large numbers"""
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

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        analysis_company = tracker.get_slot("analysis_company")
        print(analysis_company)

        if not analysis_company:
            analysis_output = "Please specify which company you'd like me to analyze."
            return [SlotSet("analysis_output", analysis_output)]
        
        ticker_symbol = analysis_company
        
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
            
            # Build Analysis Output
            analysis_output = f"**{company_full_name} ({ticker_symbol}) - Comprehensive Analysis**\n\n"
            
            # Ollama-Generated Executive Summary
            analysis_output += "📋 **Executive Summary:**\n"
            ollama_summary = self._generate_ollama_summary(
                company_full_name,
                ticker_symbol,
                current_price,
                ytd_return,
                month_return,
                market_cap,
                pe_ratio,
                indicators
            )
            analysis_output += f"{ollama_summary}\n\n"
            
            # Current Status
            analysis_output += f"💰 **Current Market Data:**\n"
            analysis_output += f"  • Current Price: ${current_price:.2f}\n"
            analysis_output += f"  • Market Cap: ${self._format_large_number(market_cap)}\n\n"
            
            # Performance
            analysis_output += f"📈 **Performance Metrics:**\n"
            analysis_output += f"  • YTD Return: {ytd_return:+.2f}%\n"
            analysis_output += f"  • 1-Month Return: {month_return:+.2f}%\n\n"
            
            # Technical Analysis
            if indicators:
                analysis_output += f"🔍 **Technical Analysis:**\n"
                sma_20 = indicators.get('sma_20', 0)
                sma_50 = indicators.get('sma_50', 0)
                rsi = indicators.get('rsi', 50)
                
                analysis_output += f"  • Trend: {self._get_trend_signal(current_price, sma_20, sma_50)}\n"
                analysis_output += f"  • RSI (14): {rsi:.1f} - {self._get_rsi_signal(rsi)}\n"
                analysis_output += f"  • 20-Day SMA: ${sma_20:.2f}\n"
                analysis_output += f"  • 50-Day SMA: ${sma_50:.2f}\n\n"
            
            # Valuation
            if pe_ratio or forward_pe:
                analysis_output += f"💼 **Valuation Analysis:**\n"
                if pe_ratio:
                    analysis_output += f"  • P/E Ratio: {pe_ratio:.2f}\n"
                if forward_pe:
                    analysis_output += f"  • Forward P/E: {forward_pe:.2f}\n"
                if peg_ratio:
                    analysis_output += f"  • PEG Ratio: {peg_ratio:.2f}\n"
                analysis_output += "\n"
            
            # Volume
            analysis_output += f"📊 **Volume Analysis:**\n"
            analysis_output += f"  • Current Volume: {int(current_volume):,}\n"
            analysis_output += f"  • Avg Volume: {int(avg_volume):,}\n"
            analysis_output += f"  • Volume Ratio: {volume_ratio:.2f}x {'(High Activity)' if volume_ratio > 1.5 else '(Normal)'}\n"
            
        except Exception as e:
            print(f"Error fetching analysis for {ticker_symbol}: {str(e)}")
            analysis_output = f"Unable to fetch analysis for {ticker_symbol}. Please verify the ticker symbol is correct."
        
        return [
            SlotSet("analysis_output", analysis_output),
            SlotSet("analysis_company", ticker_symbol)
        ]
    
#chart

class ActionShowChart(Action):
    """Generate and display charts"""
    
    def name(self) -> Text:
        return "action_show_chart"

    def generate_quickchart_url(self, labels: list, data: list, title: str, is_positive: bool) -> str:
        """Generate QuickChart URL"""
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

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        chart_asset = tracker.get_slot("chart_asset")
        print(chart_asset)

        if not chart_asset:
            message = "📊 Which asset would you like to see a chart for? Try: 'Bitcoin chart', 'Apple chart', or 'S&P 500 chart'"
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", ""),
                FollowupAction("utter_chart_results")
            ]
        
        asset_lower = chart_asset.lower()
        
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
            ticker_symbol = _clean_ticker(chart_asset)
            return self.show_stock_chart(dispatcher, ticker_symbol)
    
    def show_crypto_chart(self, dispatcher: CollectingDispatcher, coin_id: str) -> List[Dict[Text, Any]]:
        """Generate chart for cryptocurrency"""
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=7"
            response = requests.get(url, timeout=15)
            data = response.json()
            
            if "prices" not in data:
                message = f"📊 Couldn't fetch data for {coin_id}."
                return [
                    SlotSet("chart_output", message),
                    SlotSet("chart_image_url", ""),
                    FollowupAction("utter_chart_results")
                ]
            
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
            message = f"{emoji} {coin_id.title()} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%"
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", chart_url),
                FollowupAction("utter_chart_results")
            ]
            
        except Exception as e:
            print(f"Error generating crypto chart: {str(e)}")
            message = f"📊 Error generating chart for {coin_id}."
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", ""),
                FollowupAction("utter_chart_results")
            ]
    
    def show_stock_chart(self, dispatcher: CollectingDispatcher, ticker_symbol: str) -> List[Dict[Text, Any]]:
        """Generate chart for stock using yfinance"""
        try:
            ticker = yf.Ticker(ticker_symbol)
            hist = ticker.history(period="7d")
            
            if hist.empty:
                message = f"📊 Couldn't fetch data for {ticker_symbol}."
                return [
                    SlotSet("chart_output", message),
                    SlotSet("chart_image_url", ""),
                    FollowupAction("utter_chart_results")
                ]
            
            labels = [date.strftime("%m/%d") for date in hist.index]
            values = [round(price, 2) for price in hist['Close'].values]
            
            current_price = values[-1]
            first_price = values[0]
            price_change = ((current_price - first_price) / first_price) * 100
            is_positive = price_change >= 0
            
            chart_url = self.generate_quickchart_url(labels, values, f"{ticker_symbol} - 7 Day", is_positive)
            
            emoji = "📈" if is_positive else "📉"
            message = f"{emoji} {ticker_symbol} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%"
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", chart_url),
                FollowupAction("utter_chart_results")
            ]
            
        except Exception as e:
            print(f"Error generating stock chart: {str(e)}")
            message = f"📊 Error generating chart for {ticker_symbol}."
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", ""),
                FollowupAction("utter_chart_results")
            ]
    
    def show_index_chart(self, dispatcher: CollectingDispatcher, index_name: str, symbol: str) -> List[Dict[Text, Any]]:
        """Generate chart for market index"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="7d")
            
            if hist.empty:
                message = f"📊 Couldn't fetch data for {index_name}."
                return [
                    SlotSet("chart_output", message),
                    SlotSet("chart_image_url", ""),
                    FollowupAction("utter_chart_results")
                ]
            
            labels = [date.strftime("%m/%d") for date in hist.index]
            values = [round(price, 2) for price in hist['Close'].values]
            
            current_price = values[-1]
            first_price = values[0]
            price_change = ((current_price - first_price) / first_price) * 100
            is_positive = price_change >= 0
            
            display_name = index_name.upper().replace("SP500", "S&P 500").replace("DOW", "Dow Jones")
            chart_url = self.generate_quickchart_url(labels, values, f"{display_name} - 7 Day", is_positive)
            
            emoji = "📈" if is_positive else "📉"
            message = f"{emoji} {display_name} - 7 Day Chart\nCurrent: ${current_price:,.2f}\n7d Change: {price_change:+.2f}%"
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", chart_url),
                FollowupAction("utter_chart_results")
            ]
            
        except Exception as e:
            print(f"Error generating index chart: {str(e)}")
            message = f"📊 Error generating chart for {index_name}."
            return [
                SlotSet("chart_output", message),
                SlotSet("chart_image_url", ""),
                FollowupAction("utter_chart_results")
            ]


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

        # Market indices
        's&p 500': '^GSPC',
        's&p500': '^GSPC',
        'sp500': '^GSPC',
        's and p 500': '^GSPC',
        's&p': '^GSPC',
        'nasdaq': '^IXIC',
        'nasdaq composite': '^IXIC',
        'dow jones': '^DJI',
        'djia': '^DJI',
        'russell 2000': '^RUT',
        'ftse 100': '^FTSE',
    }
    
    item_lower = item.strip().lower()  # .lower() affects only English letters

    # Exact match first.
    direct = company_to_ticker.get(item_lower)
    if direct:
        return direct

    # Fallback for phrase-like inputs (e.g., "bitcoin price", "比特幣價格").
    # Prefer longer keys so specific phrases win over short tokens.
    for key in sorted(company_to_ticker.keys(), key=len, reverse=True):
        if key and key in item_lower:
            return company_to_ticker[key]

    return item.strip().upper()

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
                message = "❌ Missing required transaction information."
                return [
                    SlotSet("transaction_result_output", message),
                    SlotSet("transaction_type", None),
                    SlotSet("transaction_shares", None),
                    SlotSet("transaction_asset", None),
                    SlotSet("transaction_date", None)
                ]
            
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
                message = (
                    f"❌ Could not fetch historical price for {ticker} on {parsed_date}. "
                    f"Please verify the date and ticker symbol."
                )
                return [
                    SlotSet("transaction_result_output", message),
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
            message = (
                f"✅ **Transaction Recorded!**\n\n"
                f"Type: {transaction_type.upper()}\n"
                f"Asset: {ticker}\n"
                f"Shares: {transaction_shares}\n"
                f"Price on {parsed_date}: ${historical_price:.2f}\n"
                f"Date: {parsed_date}\n"
                f"Total Value: ${total_value:.2f}"
            )
            
            return [
                SlotSet("transaction_result_output", message),
                SlotSet("transaction_type", None),
                SlotSet("transaction_shares", None),
                SlotSet("transaction_asset", None),
                SlotSet("transaction_date", None)
            ]
            
        except Exception as e:
            print(f"ERROR in ActionSaveTransaction: {str(e)}")
            import traceback
            traceback.print_exc()
            message = f"❌ Error processing transaction: {str(e)}"
            return [
                SlotSet("transaction_result_output", message),
                SlotSet("transaction_type", None),
                SlotSet("transaction_shares", None),
                SlotSet("transaction_asset", None),
                SlotSet("transaction_date", None)
            ]

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
            message = "📊 **Your Portfolio**\n\nNo transactions recorded yet.\n\nStart by recording a buy or sell transaction!"
            return [
                SlotSet("portfolio_output", message),
                FollowupAction("utter_portfolio_results")
            ]
        
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

        return [
            SlotSet("portfolio_output", message),
            FollowupAction("utter_portfolio_results")
        ]

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
            message = "Please specify which asset to filter by."
            return [
                SlotSet("asset_transactions_output", message),
                SlotSet("filter_asset", None),
                FollowupAction("utter_asset_transactions_results")
            ]
        
        # Convert to ticker
        ticker = _clean_ticker(filter_asset)
        
        # Get transactions
        transactions = mongo_db.get_transactions_by_asset(ticker)
        
        if not transactions:
            message = f"No transactions found for {ticker}."
            return [
                SlotSet("asset_transactions_output", message),
                SlotSet("filter_asset", None),
                FollowupAction("utter_asset_transactions_results")
            ]
        
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

        return [
            SlotSet("asset_transactions_output", message),
            SlotSet("filter_asset", None),
            FollowupAction("utter_asset_transactions_results")
        ]
