from typing import Any, Dict, List, Text
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction, UserUttered, SessionStarted, ActionExecuted
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
# typo
def _get_valid_terms_pattern() -> List[str]:
    """Shared valid for typo correction"""
    return [
        # Basic
        'stock', 'stocks', 'bond', 'bonds', 'price', 'volume', 'last',
        'market', 'index', 'indices', 'what', 'is', 'are', 'how', 'when', 
        'where', 'explain', 'show', 'tell', 'me', 'about', 'define',
        'news', 'data', 'financial', 'information', 'company', 'share',
        'shares', 'ticker', 'quote', 'history', 'performance', 'trend',
        'analysis', 'report', 'update', 'current', 'value', 'rate',
        'change', 'high', 'low', 'open', 'close', 'today', 'yesterday',
        'week', 'month', 'year', 'day', 'days', 'weeks', 'months', 'years','want'
        
        # Time periods
        '52-week', 'annual', 'quarterly', 'monthly', 'weekly', 'daily',
        'ytd', 'year-to-date', 'mtd', 'month-to-date',
        
        # Financial metrics
        'return', 'returns', 'growth', 'dividend', 'dividends', 'yield',
        'market cap', 'marketcap', 'capitalization', 'revenue', 'revenues',
        'profit', 'profits', 'loss', 'losses', 'earnings', 'eps',
        'pe', 'p/e', 'ratio', 'peg', 'beta', 'volatility',
        'forecast', 'prediction', 'estimate', 'target',
        
        # Economic
        'trend', 'sector', 'industry', 'economy', 'economic',
        'inflation', 'deflation', 'interest', 'rate', 'rates',
        'fed', 'federal', 'reserve', 'unemployment', 'gdp',
        'recession', 'bull', 'bear', 'rally', 'correction', 'crash',
        
        # Corporate events
        'earnings', 'calls', 'meetings', 'conference', 'presentation',
        'transcript', 'guidance', 'outlook', 'results',
        'ipo', 'merger', 'acquisition', 'buyback', 'split',
        
        # Comparison
        'compare', 'comparison', 'versus', 'vs', 'and', 'or',
        'between', 'among', 'against', 'top', 'best', 'worst',
        'better', 'worse', 'higher', 'lower', 'more', 'less',
        'performing', 'underperforming', 'overperforming', 'outperforming',
        'difference', 'differences', 'similarities', 'similar',
        'key', 'metrics', 'indicators', 'fundamentals',
        
        # Visualization
        'chart', 'charts', 'graph', 'graphs', 'visualization',
        'visualize', 'plot', 'table', 'dataframe', 'statistics',
        'stats', 'figures', 'summary', 'overview', 'insights',
        'highlights', 'details', 'specifics', 'breakdown',
        
        # News
        'news', 'headlines', 'articles', 'reports', 'updates',
        'bulletin', 'breaking', 'latest', 'recent', 'new',
        'trending', 'popular', 'notable', 'important', 'major',
        
        # Conversational
        'goodbye', 'bye', 'exit', 'quit', 'stop', 'end',
        'hello', 'hi', 'hey', 'greetings', 'good morning',
        'good afternoon', 'good evening', 'thanks', 'thank you',
        'please', 'help', 'assist', 'support', 'service',
        
        # User/System
        'customer', 'client', 'user', 'account', 'profile',
        'settings', 'preferences', 'options', 'features',
        'functionality', 'capabilities', 'limitations',
        'issues', 'problems', 'bugs', 'errors', 'feedback',
        'suggestions', 'recommendations', 'improvements',
        'enhancements', 'updates', 'upgrades', 'versions',
        'releases', 'launches', 'introductions', 'announcements',
        
        # =====COMPANIES =====
        # FAANG/MAMAA
        'apple', 'meta', 'facebook', 'amazon', 'microsoft', 'alphabet', 'google',
        
        # Major Tech
        'nvidia', 'nvda', 'tesla', 'tsla', 'netflix', 'nflx',
        'amd', 'intel', 'intc', 'oracle', 'orcl', 'salesforce', 'crm',
        'adobe', 'adbe', 'ibm', 'cisco', 'csco', 'qualcomm', 'qcom',
        'broadcom', 'avgo', 'texas instruments', 'txn', 'micron', 'mu',
        
        # Software/Cloud
        'servicenow', 'now', 'snowflake', 'snow', 'datadog', 'ddog',
        'crowdstrike', 'crwd', 'palo alto', 'panw', 'fortinet', 'ftnt',
        'mongodb', 'mdb', 'splunk', 'splk', 'twilio', 'twlo',
        'zoom', 'zm', 'slack', 'okta', 'okta', 'docusign', 'docu',
        
        # E-commerce/Retail Tech
        'shopify', 'shop', 'square', 'sq', 'paypal', 'pypl',
        'ebay', 'ebay', 'etsy', 'etsy', 'wayfair', 'w',
        
        # Social Media/Gaming
        'snap', 'snapchat', 'pinterest', 'pins', 'twitter', 'twtr',
        'roblox', 'rblx', 'unity', 'u', 'activision', 'atvi',
        'electronic arts', 'ea', 'take-two', 'ttwo',
        
        # Semiconductors
        'asml', 'asml', 'lam research', 'lrcx', 'applied materials', 'amat',
        'klac', 'klac', 'nvidia', 'nvda', 'tsmc', 'tsm',
        
        # ===== FINANCIAL SERVICES =====
        # Banks
        'jpmorgan', 'jpm', 'bank of america', 'bac', 'wells fargo', 'wfc',
        'citigroup', 'c', 'goldman sachs', 'gs', 'morgan stanley', 'ms',
        'us bank', 'usb', 'pnc', 'pnc', 'truist', 'tfc',
        'capital one', 'cof', 'charles schwab', 'schw',
        
        # Payment Processors
        'visa', 'v', 'mastercard', 'ma', 'american express', 'axp',
        'discover', 'dfs', 'paypal', 'pypl', 'square', 'sq',
        
        # Insurance
        'berkshire hathaway', 'brk', 'progressive', 'pgr',
        'allstate', 'all', 'travelers', 'trv', 'chubb', 'cb',
        'metlife', 'met', 'prudential', 'pru', 'aig', 'aig',
        
        # Investment Firms
        'blackrock', 'blk', 'vanguard', 'state street', 'stt',
        't rowe price', 'trow', 'franklin templeton', 'ben',
        
        # ===== CONSUMER & RETAIL =====
        # Mega Retailers
        'walmart', 'wmt', 'target', 'tgt', 'costco', 'cost',
        'home depot', 'hd', 'lowes', 'low', 'best buy', 'bby',
        
        # E-commerce
        'amazon', 'amzn', 'alibaba', 'baba', 'jd.com', 'jd',
        'mercadolibre', 'meli', 'coupang', 'cpng',
        
        # Luxury/Apparel
        'nike', 'nke', 'adidas', 'addyy', 'lululemon', 'lulu',
        'gap', 'gps', 'tjx', 'tjx', 'ross stores', 'rost',
        'lvmh', 'lvmuy', 'hermes', 'hesay', 'kering', 'ppruy',
        
        # Food & Beverage
        'coca cola', 'ko', 'pepsi', 'pep', 'mcdonalds', 'mcd',
        'starbucks', 'sbux', 'chipotle', 'cmg', 'yum brands', 'yum',
        'dominos', 'dpz', 'restaurant brands', 'qsr',
        'kraft heinz', 'khc', 'general mills', 'gis',
        'kellogg', 'k', 'mondelez', 'mdlz', 'hershey', 'hsy',
        
        # Consumer Goods
        'procter gamble', 'pg', 'unilever', 'ul', 'colgate', 'cl',
        'kimberly clark', 'kmb', 'estee lauder', 'el',
        
        # ===== HEALTHCARE & PHARMA =====
        # Pharma
        'pfizer', 'pfe', 'moderna', 'mrna', 'johnson johnson', 'jnj',
        'merck', 'mrk', 'abbvie', 'abbv', 'eli lilly', 'lly',
        'bristol myers', 'bmy', 'amgen', 'amgn', 'gilead', 'gild',
        'regeneron', 'regn', 'biogen', 'biib', 'vertex', 'vrtx',
        
        # Medical Devices
        'medtronic', 'mdt', 'abbott', 'abt', 'boston scientific', 'bsx',
        'stryker', 'syk', 'intuitive surgical', 'isrg',
        'dexcom', 'dxcm', 'edwards lifesciences', 'ew',
        
        # Health Insurance/Services
        'unitedhealth', 'unh', 'cvs', 'cvs', 'cigna', 'ci',
        'humana', 'hum', 'anthem', 'antm', 'centene', 'cnc',
        
        # ===== ENERGY & UTILITIES =====
        # Oil & Gas
        'exxon', 'xom', 'chevron', 'cvx', 'conocophillips', 'cop',
        'shell', 'shel', 'bp', 'bp', 'totalenergies', 'tte',
        'marathon', 'mpc', 'valero', 'vlo', 'phillips 66', 'psx',
        
        # Renewables
        'nextera', 'nee', 'first solar', 'fslr', 'enphase', 'enph',
        'sunrun', 'run', 'plug power', 'plug', 'bloom energy', 'be',
        
        # Utilities
        'duke energy', 'duk', 'southern company', 'so',
        'dominion', 'd', 'american electric', 'aep',
        
        # ===== INDUSTRIALS & MATERIALS =====
        # Aerospace/Defense
        'boeing', 'ba', 'lockheed martin', 'lmt', 'raytheon', 'rtx',
        'northrop grumman', 'noc', 'general dynamics', 'gd',
        
        # Automotive
        'ford', 'f', 'gm', 'general motors', 'stellantis', 'stla',
        'ferrari', 'race', 'rivian', 'rivn', 'lucid', 'lcid',
        
        # Industrial
        'caterpillar', 'cat', 'deere', 'de', '3m', 'mmm',
        'honeywell', 'hon', 'ge', 'general electric',
        'united rentals', 'uri', 'waste management', 'wm',
        
        # ===== TELECOMMUNICATIONS =====
        'verizon', 'vz', 'att', 't', 't-mobile', 'tmus',
        'comcast', 'cmcsa', 'charter', 'chtr', 'dish', 'dish',
        
        # ===== REAL ESTATE =====
        'american tower', 'amt', 'prologis', 'pld', 'crown castle', 'cci',
        'equinix', 'eqix', 'digital realty', 'dlr', 'simon property', 'spg',
        
        # ===== CRYPTOCURRENCIES =====
        'bitcoin', 'btc', 'ethereum', 'eth', 'binance coin', 'bnb',
        'cardano', 'ada', 'solana', 'sol', 'ripple', 'xrp',
        'polkadot', 'dot', 'dogecoin', 'doge', 'shiba', 'shib',
        'avalanche', 'avax', 'polygon', 'matic', 'chainlink', 'link',
        'litecoin', 'ltc', 'uniswap', 'uni', 'cosmos', 'atom',
        'algorand', 'algo', 'stellar', 'xlm', 'tron', 'trx',
        'monero', 'xmr', 'tezos', 'xtz', 'eos', 'eos',

        'alibaba', 'baba', 'tencent', 'tcehy', 'baidu', 'bidu',
        'jd.com', 'jd', 'pinduoduo', 'pdd', 'nio', 'nio',
        'xpeng', 'xpev', 'li auto', 'li', 'didi', 'didi',
        
        'asml', 'asml', 'sap', 'sap', 'siemens', 'siegy',
        'airbus', 'eadsy', 'volkswagen', 'vwagy', 'bmw', 'bmwyy',
        'nestle', 'nsrgy', 'roche', 'rhhby', 'novartis', 'nvs',

        'toyota', 'tm', 'sony', 'sony', 'nintendo', 'ntdoy',
        'softbank', 'sftby', 'keyence', 'kyccf',
        
        'samsung', 'ssnlf', 'hyundai', 'hymtf', 'lg', 'lpl',
        
        # ===== ETFS & INDEXES =====
        'spy', 's&p', 'qqq', 'nasdaq', 'dia', 'dow',
        'iwm', 'russell', 'voo', 'vti', 'vt', 'vxus',
        'eem', 'emerging', 'vwo', 'iefa', 'efa',
        'xlk', 'xlf', 'xle', 'xlv', 'xly', 'xlp', 'xli', 'xlb', 'xlre', 'xlu',
        'arkk', 'arkw', 'arkg', 'arkf', 'arkq',
        'gld', 'slv', 'uso', 'ung', 'tlt', 'ief', 'shy',
        'hyg', 'lqd', 'jnk', 'emb', 'mub',
        
        # ===== ADDITIONAL SECTORS =====
        # Media & Entertainment
        'disney', 'dis', 'warner bros', 'wbd', 'paramount', 'para',
        'netflix', 'nflx', 'comcast', 'cmcsa', 'fox', 'foxa',
        'spotify', 'spot', 'live nation', 'lyv',
        
        # Travel & Leisure
        'booking', 'bkng', 'expedia', 'expe', 'airbnb', 'abnb',
        'marriott', 'mar', 'hilton', 'hlt', 'hyatt', 'h',
        'delta', 'dal', 'united', 'ual', 'american airlines', 'aal',
        'southwest', 'luv', 'spirit', 'save', 'jetblue', 'jblu',
        'carnival', 'ccl', 'royal caribbean', 'rcl', 'norwegian', 'nclh',
        
        # Gaming/Betting
        'draftkings', 'dkng', 'fanduel', 'flutter', 'penn', 'penn',
        'caesars', 'czr', 'mgm', 'mgm', 'wynn', 'wynn',
        
        # Biotech
        'illumina', 'ilmn', 'crispr', 'crsp', 'editas', 'edit',
        'intellia', 'ntla', 'biontech', 'bntx', 'novavax', 'nvax',
        'alnylam', 'alny', 'sarepta', 'srpt', 'bluebird', 'blue',
        
        # Fintech
        'block', 'sq', 'affirm', 'afrm', 'sofi', 'sofi',
        'upstart', 'upst', 'lemonade', 'lmnd', 'coinbase', 'coin',
        'robinhood', 'hood', 'marqeta', 'mq',
    ]

#ticker
def _clean_ticker(item: str) -> str:
    """Convert company name or crypto to ticker symbol - COMPLETE EXPANDED VERSION"""
    item_lower = item.lower().strip()
    
    company_to_ticker = {
        # TECH
        'apple': 'AAPL', 'aapl': 'AAPL', 'meta': 'META', 'facebook': 'META', 
        'amazon': 'AMZN', 'amzn': 'AMZN', 'microsoft': 'MSFT', 'msft': 'MSFT', 
        'alphabet': 'GOOGL', 'google': 'GOOGL', 'googl': 'GOOGL',
        
        #- Major Tech
        'nvidia': 'NVDA', 'nvda': 'NVDA', 'tesla': 'TSLA', 'tsla': 'TSLA', 
        'netflix': 'NFLX', 'nflx': 'NFLX', 'amd': 'AMD', 'intel': 'INTC', 'intc': 'INTC',
        'oracle': 'ORCL', 'orcl': 'ORCL', 'salesforce': 'CRM', 'crm': 'CRM',
        'adobe': 'ADBE', 'adbe': 'ADBE', 'ibm': 'IBM', 'cisco': 'CSCO', 'csco': 'CSCO',
        'qualcomm': 'QCOM', 'qcom': 'QCOM', 'broadcom': 'AVGO', 'avgo': 'AVGO',
        'texas instruments': 'TXN', 'txn': 'TXN', 'micron': 'MU', 'mu': 'MU',
        
        #- Software/Cloud
        'servicenow': 'NOW', 'now': 'NOW', 'snowflake': 'SNOW', 'snow': 'SNOW',
        'datadog': 'DDOG', 'ddog': 'DDOG', 'crowdstrike': 'CRWD', 'crwd': 'CRWD',
        'palo alto': 'PANW', 'panw': 'PANW', 'fortinet': 'FTNT', 'ftnt': 'FTNT',
        'mongodb': 'MDB', 'mdb': 'MDB', 'splunk': 'SPLK', 'splk': 'SPLK',
        'twilio': 'TWLO', 'twlo': 'TWLO', 'zoom': 'ZM', 'zm': 'ZM',
        'slack': 'WORK', 'okta': 'OKTA', 'docusign': 'DOCU', 'docu': 'DOCU',
        
        #- E-commerce/Retail Tech
        'shopify': 'SHOP', 'shop': 'SHOP', 'square': 'SQ', 'sq': 'SQ', 'block': 'SQ',
        'paypal': 'PYPL', 'pypl': 'PYPL', 'ebay': 'EBAY', 'etsy': 'ETSY',
        'wayfair': 'W', 'w': 'W',
        
        #- Social Media/Gaming
        'snap': 'SNAP', 'snapchat': 'SNAP', 'pinterest': 'PINS', 'pins': 'PINS',
        'twitter': 'TWTR', 'twtr': 'TWTR', 'roblox': 'RBLX', 'rblx': 'RBLX',
        'unity': 'U', 'u': 'U', 'activision': 'ATVI', 'atvi': 'ATVI',
        'electronic arts': 'EA', 'ea': 'EA', 'take-two': 'TTWO', 'ttwo': 'TTWO',
        
        #- Semiconductors
        'asml': 'ASML', 'lam research': 'LRCX', 'lrcx': 'LRCX',
        'applied materials': 'AMAT', 'amat': 'AMAT', 'klac': 'KLAC',
        'tsmc': 'TSM', 'tsm': 'TSM',
        
        # FINANCIAL - Banks
        'jpmorgan': 'JPM', 'jpm': 'JPM', 'jp morgan': 'JPM',
        'bank of america': 'BAC', 'bac': 'BAC', 'bofa': 'BAC',
        'wells fargo': 'WFC', 'wfc': 'WFC', 'citigroup': 'C', 'citi': 'C',
        'goldman sachs': 'GS', 'gs': 'GS', 'goldman': 'GS',
        'morgan stanley': 'MS', 'ms': 'MS', 'us bank': 'USB', 'usb': 'USB',
        'pnc': 'PNC', 'truist': 'TFC', 'tfc': 'TFC',
        'capital one': 'COF', 'cof': 'COF',
        'charles schwab': 'SCHW', 'schw': 'SCHW', 'schwab': 'SCHW',
        
        # FINANCIAL - Payment Processors
        'visa': 'V', 'v': 'V', 'mastercard': 'MA', 'ma': 'MA',
        'american express': 'AXP', 'axp': 'AXP', 'amex': 'AXP',
        'discover': 'DFS', 'dfs': 'DFS',
        
        # FINANCIAL - Insurance
        'berkshire hathaway': 'BRK.B', 'berkshire': 'BRK.B', 'brk': 'BRK.B',
        'progressive': 'PGR', 'pgr': 'PGR', 'allstate': 'ALL',
        'travelers': 'TRV', 'trv': 'TRV', 'chubb': 'CB', 'cb': 'CB',
        'metlife': 'MET', 'met': 'MET', 'prudential': 'PRU', 'pru': 'PRU',
        'aig': 'AIG',
        
        # FINANCIAL - Investment Firms
        'blackrock': 'BLK', 'blk': 'BLK', 'vanguard': 'VGRD',
        'state street': 'STT', 'stt': 'STT', 't rowe price': 'TROW', 'trow': 'TROW',
        'franklin templeton': 'BEN', 'ben': 'BEN',
        
        # CONSUMER - Mega Retailers
        'walmart': 'WMT', 'wmt': 'WMT', 'target': 'TGT', 'tgt': 'TGT',
        'costco': 'COST', 'cost': 'COST', 'home depot': 'HD', 'hd': 'HD',
        'lowes': 'LOW', 'low': 'LOW', 'best buy': 'BBY', 'bby': 'BBY',
        
        # CONSUMER - E-commerce
        'alibaba': 'BABA', 'baba': 'BABA', 'jd.com': 'JD', 'jd': 'JD',
        'mercadolibre': 'MELI', 'meli': 'MELI', 'coupang': 'CPNG', 'cpng': 'CPNG',
        
        # CONSUMER - Luxury/Apparel
        'nike': 'NKE', 'nke': 'NKE', 'adidas': 'ADDYY', 'addyy': 'ADDYY',
        'lululemon': 'LULU', 'lulu': 'LULU', 'gap': 'GPS', 'gps': 'GPS',
        'tjx': 'TJX', 'ross stores': 'ROST', 'rost': 'ROST',
        'lvmh': 'LVMUY', 'lvmuy': 'LVMUY', 'hermes': 'HESAY', 'hesay': 'HESAY',
        'kering': 'PPRUY', 'ppruy': 'PPRUY',
        
        # CONSUMER - Food & Beverage
        'coca cola': 'KO', 'ko': 'KO', 'coke': 'KO', 'pepsi': 'PEP', 'pep': 'PEP', 'pepsico': 'PEP',
        'mcdonalds': 'MCD', 'mcd': 'MCD', 'starbucks': 'SBUX', 'sbux': 'SBUX',
        'chipotle': 'CMG', 'cmg': 'CMG', 'yum brands': 'YUM', 'yum': 'YUM',
        'dominos': 'DPZ', 'dpz': 'DPZ', 'restaurant brands': 'QSR', 'qsr': 'QSR',
        'kraft heinz': 'KHC', 'khc': 'KHC', 'general mills': 'GIS', 'gis': 'GIS',
        'kellogg': 'K', 'k': 'K', 'mondelez': 'MDLZ', 'mdlz': 'MDLZ',
        'hershey': 'HSY', 'hsy': 'HSY',
        
        # CONSUMER - Consumer Goods
        'procter gamble': 'PG', 'pg': 'PG', 'p&g': 'PG', 'unilever': 'UL', 'ul': 'UL',
        'colgate': 'CL', 'cl': 'CL', 'kimberly clark': 'KMB', 'kmb': 'KMB',
        'estee lauder': 'EL', 'el': 'EL',
        
        # HEALTHCARE - Pharma
        'pfizer': 'PFE', 'pfe': 'PFE', 'moderna': 'MRNA', 'mrna': 'MRNA',
        'johnson johnson': 'JNJ', 'jnj': 'JNJ', 'j&j': 'JNJ',
        'merck': 'MRK', 'mrk': 'MRK', 'abbvie': 'ABBV', 'abbv': 'ABBV',
        'eli lilly': 'LLY', 'lly': 'LLY', 'lilly': 'LLY',
        'bristol myers': 'BMY', 'bmy': 'BMY', 'amgen': 'AMGN', 'amgn': 'AMGN',
        'gilead': 'GILD', 'gild': 'GILD', 'regeneron': 'REGN', 'regn': 'REGN',
        'biogen': 'BIIB', 'biib': 'BIIB', 'vertex': 'VRTX', 'vrtx': 'VRTX',
        
        # HEALTHCARE - Medical Devices
        'medtronic': 'MDT', 'mdt': 'MDT', 'abbott': 'ABT', 'abt': 'ABT',
        'boston scientific': 'BSX', 'bsx': 'BSX', 'stryker': 'SYK', 'syk': 'SYK',
        'intuitive surgical': 'ISRG', 'isrg': 'ISRG', 'dexcom': 'DXCM', 'dxcm': 'DXCM',
        'edwards lifesciences': 'EW', 'ew': 'EW',
        
        # HEALTHCARE - Health Insurance/Services
        'unitedhealth': 'UNH', 'unh': 'UNH', 'cvs': 'CVS',
        'cigna': 'CI', 'ci': 'CI', 'humana': 'HUM', 'hum': 'HUM',
        'anthem': 'ANTM', 'antm': 'ANTM', 'centene': 'CNC', 'cnc': 'CNC',
        
        # ENERGY - Oil & Gas
        'exxon': 'XOM', 'xom': 'XOM', 'exxonmobil': 'XOM',
        'chevron': 'CVX', 'cvx': 'CVX', 'conocophillips': 'COP', 'cop': 'COP',
        'shell': 'SHEL', 'shel': 'SHEL', 'bp': 'BP',
        'totalenergies': 'TTE', 'tte': 'TTE', 'marathon': 'MPC', 'mpc': 'MPC',
        'valero': 'VLO', 'vlo': 'VLO', 'phillips 66': 'PSX', 'psx': 'PSX',
        
        # ENERGY - Renewables
        'nextera': 'NEE', 'nee': 'NEE', 'first solar': 'FSLR', 'fslr': 'FSLR',
        'enphase': 'ENPH', 'enph': 'ENPH', 'sunrun': 'RUN', 'run': 'RUN',
        'plug power': 'PLUG', 'plug': 'PLUG', 'bloom energy': 'BE', 'be': 'BE',
        
        # ENERGY - Utilities
        'duke energy': 'DUK', 'duk': 'DUK', 'southern company': 'SO', 'so': 'SO',
        'dominion': 'D', 'd': 'D', 'american electric': 'AEP', 'aep': 'AEP',
        
        # INDUSTRIALS - Aerospace/Defense
        'boeing': 'BA', 'ba': 'BA', 'lockheed martin': 'LMT', 'lmt': 'LMT', 'lockheed': 'LMT',
        'raytheon': 'RTX', 'rtx': 'RTX', 'northrop grumman': 'NOC', 'noc': 'NOC', 'northrop': 'NOC',
        'general dynamics': 'GD', 'gd': 'GD',
        
        # INDUSTRIALS - Automotive
        'ford': 'F', 'f': 'F', 'gm': 'GM', 'general motors': 'GM',
        'stellantis': 'STLA', 'stla': 'STLA', 'ferrari': 'RACE', 'race': 'RACE',
        'rivian': 'RIVN', 'rivn': 'RIVN', 'lucid': 'LCID', 'lcid': 'LCID',
        
        # INDUSTRIALS - Industrial 
        'caterpillar': 'CAT', 'cat': 'CAT', 'deere': 'DE', 'de': 'DE', 'john deere': 'DE',
        '3m': 'MMM', 'mmm': 'MMM', 'honeywell': 'HON', 'hon': 'HON',
        'ge': 'GE', 'general electric': 'GE', 'united rentals': 'URI', 'uri': 'URI',
        'waste management': 'WM', 'wm': 'WM',
        
        # TELECOMMUNICATIONS
        'verizon': 'VZ', 'vz': 'VZ', 'att': 'T', 't': 'T', 'at&t': 'T',
        't-mobile': 'TMUS', 'tmus': 'TMUS', 'tmobile': 'TMUS',
        'comcast': 'CMCSA', 'cmcsa': 'CMCSA', 'charter': 'CHTR', 'chtr': 'CHTR',
        'dish': 'DISH',
        
        # REAL ESTATE
        'american tower': 'AMT', 'amt': 'AMT', 'prologis': 'PLD', 'pld': 'PLD',
        'crown castle': 'CCI', 'cci': 'CCI', 'equinix': 'EQIX', 'eqix': 'EQIX',
        'digital realty': 'DLR', 'dlr': 'DLR', 'simon property': 'SPG', 'spg': 'SPG',
        
        # CRYPTOCURRENCIES (Yahoo Finance format)
        'bitcoin': 'BTC-USD', 'btc': 'BTC-USD', 'ethereum': 'ETH-USD', 'eth': 'ETH-USD',
        'binance coin': 'BNB-USD', 'bnb': 'BNB-USD', 'binance': 'BNB-USD',
        'cardano': 'ADA-USD', 'ada': 'ADA-USD', 'solana': 'SOL-USD', 'sol': 'SOL-USD',
        'ripple': 'XRP-USD', 'xrp': 'XRP-USD', 'polkadot': 'DOT-USD', 'dot': 'DOT-USD',
        'dogecoin': 'DOGE-USD', 'doge': 'DOGE-USD', 'shiba': 'SHIB-USD', 'shib': 'SHIB-USD',
        'shiba inu': 'SHIB-USD', 'avalanche': 'AVAX-USD', 'avax': 'AVAX-USD',
        'polygon': 'MATIC-USD', 'matic': 'MATIC-USD', 'chainlink': 'LINK-USD', 'link': 'LINK-USD',
        'litecoin': 'LTC-USD', 'ltc': 'LTC-USD', 'uniswap': 'UNI-USD', 'uni': 'UNI-USD',
        'cosmos': 'ATOM-USD', 'atom': 'ATOM-USD', 'algorand': 'ALGO-USD', 'algo': 'ALGO-USD',
        'stellar': 'XLM-USD', 'xlm': 'XLM-USD', 'tron': 'TRX-USD', 'trx': 'TRX-USD',
        'monero': 'XMR-USD', 'xmr': 'XMR-USD', 'tezos': 'XTZ-USD', 'xtz': 'XTZ-USD',
        'eos': 'EOS-USD',
        
        # INTERNATIONAL - Chinese
        'tencent': 'TCEHY', 'tcehy': 'TCEHY', 'baidu': 'BIDU', 'bidu': 'BIDU',
        'pinduoduo': 'PDD', 'pdd': 'PDD', 'nio': 'NIO', 'nio': 'NIO',
        'xpeng': 'XPEV', 'xpev': 'XPEV', 'li auto': 'LI', 'li': 'LI',
        'didi': 'DIDI', 'didi': 'DIDI',
        
        # INTERNATIONAL - European
        'asml': 'ASML', 'sap': 'SAP', 'siemens': 'SIEGY', 'siegy': 'SIEGY',
        'airbus': 'EADSY', 'eadsy': 'EADSY', 'volkswagen': 'VWAGY', 'vwagy': 'VWAGY',
        'bmw': 'BMWYY', 'bmwyy': 'BMWYY', 'nestle': 'NSRGY', 'nsrgy': 'NSRGY',
        'roche': 'RHHBY', 'rhhby': 'RHHBY', 'novartis': 'NVS', 'nvs': 'NVS',
        
        # INTERNATIONAL - Japanese
        'toyota': 'TM', 'tm': 'TM', 'sony': 'SONY', 'nintendo': 'NTDOY', 'ntdoy': 'NTDOY',
        'softbank': 'SFTBY', 'sftby': 'SFTBY', 'keyence': 'KYCCF', 'kyccf': 'KYCCF',
        
        # INTERNATIONAL - Korean
        'samsung': 'SSNLF', 'ssnlf': 'SSNLF', 'hyundai': 'HYMTF', 'hymtf': 'HYMTF',
        'lg': 'LPL', 'lpl': 'LPL',
        
        # ETFS
        'spy': 'SPY', 'qqq': 'QQQ', 'dia': 'DIA', 'iwm': 'IWM',
        'voo': 'VOO', 'vti': 'VTI', 'vt': 'VT', 'vxus': 'VXUS',
        'eem': 'EEM', 'vwo': 'VWO', 'iefa': 'IEFA', 'efa': 'EFA',
        'xlk': 'XLK', 'xlf': 'XLF', 'xle': 'XLE', 'xlv': 'XLV',
        'xly': 'XLY', 'xlp': 'XLP', 'xli': 'XLI', 'xlb': 'XLB',
        'xlre': 'XLRE', 'xlu': 'XLU',
        'arkk': 'ARKK', 'arkw': 'ARKW', 'arkg': 'ARKG', 'arkf': 'ARKF', 'arkq': 'ARKQ',
        'gld': 'GLD', 'slv': 'SLV', 'uso': 'USO', 'ung': 'UNG',
        'tlt': 'TLT', 'ief': 'IEF', 'shy': 'SHY',
        'hyg': 'HYG', 'lqd': 'LQD', 'jnk': 'JNK', 'emb': 'EMB', 'mub': 'MUB',
        
        # MEDIA & ENTERTAINMENT
        'disney': 'DIS', 'dis': 'DIS', 'walt disney': 'DIS',
        'warner bros': 'WBD', 'wbd': 'WBD', 'paramount': 'PARA', 'para': 'PARA',
        'fox': 'FOXA', 'foxa': 'FOXA', 'spotify': 'SPOT', 'spot': 'SPOT',
        'live nation': 'LYV', 'lyv': 'LYV',
        
        # TRAVEL & LEISURE
        'booking': 'BKNG', 'bkng': 'BKNG', 'expedia': 'EXPE', 'expe': 'EXPE',
        'airbnb': 'ABNB', 'abnb': 'ABNB', 'marriott': 'MAR', 'mar': 'MAR',
        'hilton': 'HLT', 'hlt': 'HLT', 'hyatt': 'H', 'h': 'H',
        'delta': 'DAL', 'dal': 'DAL', 'united': 'UAL', 'ual': 'UAL',
        'american airlines': 'AAL', 'aal': 'AAL', 'southwest': 'LUV', 'luv': 'LUV',
        'spirit': 'SAVE', 'save': 'SAVE', 'jetblue': 'JBLU', 'jblu': 'JBLU',
        'carnival': 'CCL', 'ccl': 'CCL', 'royal caribbean': 'RCL', 'rcl': 'RCL',
        'norwegian': 'NCLH', 'nclh': 'NCLH',
        
        # GAMING/BETTING
        'draftkings': 'DKNG', 'dkng': 'DKNG', 'fanduel': 'FLUT', 'flutter': 'FLUT',
        'penn': 'PENN', 'caesars': 'CZR', 'czr': 'CZR',
        'mgm': 'MGM', 'wynn': 'WYNN',
        
        # BIOTECH
        'illumina': 'ILMN', 'ilmn': 'ILMN', 'crispr': 'CRSP', 'crsp': 'CRSP',
        'editas': 'EDIT', 'edit': 'EDIT', 'intellia': 'NTLA', 'ntla': 'NTLA',
        'biontech': 'BNTX', 'bntx': 'BNTX', 'novavax': 'NVAX', 'nvax': 'NVAX',
        'alnylam': 'ALNY', 'alny': 'ALNY', 'sarepta': 'SRPT', 'srpt': 'SRPT',
        'bluebird': 'BLUE', 'blue': 'BLUE',
        
        # FINTECH
        'affirm': 'AFRM', 'afrm': 'AFRM', 'sofi': 'SOFI',
        'upstart': 'UPST', 'upst': 'UPST', 'lemonade': 'LMND', 'lmnd': 'LMND',
        'coinbase': 'COIN', 'coin': 'COIN', 'robinhood': 'HOOD', 'hood': 'HOOD',
        'marqeta': 'MQ', 'mq': 'MQ',
    }
    
    # Return the ticker or the original item if not found
    return company_to_ticker.get(item_lower, item.upper())

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
        import yfinance as yf
        from datetime import datetime, timedelta
        
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

# : Typo Corre
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

# EXTRAc

class ActionExtractSecurityName(Action):
    """Extract security name from user message"""
    
    def name(self) -> Text:
        return "action_extract_security_name"
    
    def _extract_company_from_query(self, query: str) -> str:
        """Extract just the company name from a query"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = [
        # ===== QUESTION WORDS =====
        'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how',
        
        # ===== ARTICLES & DETERMINERS =====
        'a', 'an', 'the', 'this', 'that', 'these', 'those',
        
        # ===== PREPOSITIONS =====
        'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
        'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
        'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near',
        'of', 'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to',
        'toward', 'under', 'underneath', 'until', 'up', 'upon', 'with', 'within',
        'without',
        
        # ===== PRONOUNS =====
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers',
        'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself',
        'ourselves', 'yourselves', 'themselves',
        
        # ===== AUXILIARY & MODAL VERBS =====
        'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having',
        'do', 'does', 'did', 'doing',
        'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
        
        # ===== CONJUNCTIONS =====
        'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
        'although', 'because', 'since', 'unless', 'while', 'whereas',
        'if', 'then', 'else', 'whether',
        
        # ===== COMMON ACTION VERBS (in queries) =====
        'show', 'tell', 'give', 'get', 'fetch', 'find', 'search', 'look',
        'see', 'check', 'view', 'display', 'provide', 'retrieve',
        'want', 'need', 'like', 'prefer', 'wish',
        
        # ===== POLITE/CONVERSATIONAL WORDS =====
        'please', 'thanks', 'thank', 'hello', 'hi', 'hey', 'goodbye', 'bye',
        
        # ===== QUANTIFIERS (general) =====
        'some', 'any', 'many', 'much', 'few', 'several', 'all', 'both', 'each',
        'every', 'either', 'neither', 'no', 'none',
        
        # ===== INTENSIFIERS & MODIFIERS =====
        'very', 'really', 'quite', 'rather', 'too', 'so', 'such',
        'just', 'only', 'even', 'still', 'also', 'already',
        
        # ===== DOMAIN-SPECIFIC NOISE (Finance) =====
        # Price queries
        'price', 'cost', 'value', 'worth', 'trading', 'currently',
        
        # Data queries
        'data', 'information', 'details', 'stats', 'statistics',
        
        # News queries
        'news', 'headlines', 'articles', 'updates', 'reports',
        
        # Analysis queries
        'analysis', 'analyze', 'performance', 'metrics',
        
        # Chart queries
        'chart', 'graph', 'plot', 'visualization', 'display',
        
        # Comparison queries
        'compare', 'comparison', 'versus', 'vs', 'difference',
        
        # General finance noise
        'stock', 'stocks', 'share', 'shares', 'ticker', 'symbol',
        'market', 'financial', 'company', 'companies',
    ]
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        if cleaned_words:
            return cleaned_words[0]
        
        return None
    
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
        
        query_lower = query.lower().strip().replace("\\", "")
        
                # Remove noise words
        noise_words = [
                # ===== QUESTION WORDS =====
                'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how',
                
                # ===== ARTICLES & DETERMINERS =====
                'a', 'an', 'the', 'this', 'that', 'these', 'those',
                
                # ===== PREPOSITIONS =====
                'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
                'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
                'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near',
                'of', 'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to',
                'toward', 'under', 'underneath', 'until', 'up', 'upon', 'with', 'within',
                'without',
                
                # ===== PRONOUNS =====
                'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
                'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers',
                'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself',
                'ourselves', 'yourselves', 'themselves',
                
                # ===== AUXILIARY & MODAL VERBS =====
                'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                'have', 'has', 'had', 'having',
                'do', 'does', 'did', 'doing',
                'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
                
                # ===== CONJUNCTIONS =====
                'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
                'although', 'because', 'since', 'unless', 'while', 'whereas',
                'if', 'then', 'else', 'whether',
                
                # ===== COMMON ACTION VERBS (in queries) =====
                'show', 'tell', 'give', 'get', 'fetch', 'find', 'search', 'look',
                'see', 'check', 'view', 'display', 'provide', 'retrieve',
                'want', 'need', 'like', 'prefer', 'wish',
                
                # ===== POLITE/CONVERSATIONAL WORDS =====
                'please', 'thanks', 'thank', 'hello', 'hi', 'hey', 'goodbye', 'bye',
                
                # ===== QUANTIFIERS (general) =====
                'some', 'any', 'many', 'much', 'few', 'several', 'all', 'both', 'each',
                'every', 'either', 'neither', 'no', 'none',
                
                # ===== INTENSIFIERS & MODIFIERS =====
                'very', 'really', 'quite', 'rather', 'too', 'so', 'such',
                'just', 'only', 'even', 'still', 'also', 'already',
                
                # ===== DOMAIN-SPECIFIC NOISE (Finance) =====
                # Price queries
                'price', 'cost', 'value', 'worth', 'trading', 'currently',
                
                # Data queries
                'data', 'information', 'details', 'stats', 'statistics',
                
                # News queries
                'news', 'headlines', 'articles', 'updates', 'reports',
                
                # Analysis queries
                'analysis', 'analyze', 'performance', 'metrics',
                
                # Chart queries
                'chart', 'graph', 'plot', 'visualization', 'display',
                
                # Comparison queries
                'compare', 'comparison', 'versus', 'vs', 'difference',
                
                # General finance noise
                'stock', 'stocks', 'share', 'shares', 'ticker', 'symbol',
                'market', 'financial', 'company', 'companies',
            ]
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        # Rejoin for multi-word indexes
        cleaned_query = " ".join(cleaned_words)
        
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
        
        return cleaned_query if cleaned_query else None
    
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
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = [
        # ===== QUESTION WORDS =====
        'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how',
        
        # ===== ARTICLES & DETERMINERS =====
        'a', 'an', 'the', 'this', 'that', 'these', 'those',
        
        # ===== PREPOSITIONS =====
        'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
        'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
        'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near',
        'of', 'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to',
        'toward', 'under', 'underneath', 'until', 'up', 'upon', 'with', 'within',
        'without',
        
        # ===== PRONOUNS =====
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers',
        'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself',
        'ourselves', 'yourselves', 'themselves',
        
        # ===== AUXILIARY & MODAL VERBS =====
        'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having',
        'do', 'does', 'did', 'doing',
        'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
        
        # ===== CONJUNCTIONS =====
        'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
        'although', 'because', 'since', 'unless', 'while', 'whereas',
        'if', 'then', 'else', 'whether',
        
        # ===== COMMON ACTION VERBS (in queries) =====
        'show', 'tell', 'give', 'get', 'fetch', 'find', 'search', 'look',
        'see', 'check', 'view', 'display', 'provide', 'retrieve',
        'want', 'need', 'like', 'prefer', 'wish',
        
        # ===== POLITE/CONVERSATIONAL WORDS =====
        'please', 'thanks', 'thank', 'hello', 'hi', 'hey', 'goodbye', 'bye',
        
        # ===== QUANTIFIERS (general) =====
        'some', 'any', 'many', 'much', 'few', 'several', 'all', 'both', 'each',
        'every', 'either', 'neither', 'no', 'none',
        
        # ===== INTENSIFIERS & MODIFIERS =====
        'very', 'really', 'quite', 'rather', 'too', 'so', 'such',
        'just', 'only', 'even', 'still', 'also', 'already',
        
        # ===== DOMAIN-SPECIFIC NOISE (Finance) =====
        # Price queries
        'price', 'cost', 'value', 'worth', 'trading', 'currently',
        
        # Data queries
        'data', 'information', 'details', 'stats', 'statistics',
        
        # News queries
        'news', 'headlines', 'articles', 'updates', 'reports',
        
        # Analysis queries
        'analysis', 'analyze', 'performance', 'metrics',
        
        # Chart queries
        'chart', 'graph', 'plot', 'visualization', 'display',
        
        # Comparison queries
        'compare', 'comparison', 'versus', 'vs', 'difference',
        
        # General finance noise
        'stock', 'stocks', 'share', 'shares', 'ticker', 'symbol',
        'market', 'financial', 'company', 'companies',
    ]
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        if cleaned_words:
            return cleaned_words[0]
        
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
        
        topic = self._extract_topic_from_query(query_to_use)
        
        return [SlotSet("news_topic", topic)]

class ActionExtractComparisonItems(Action):
    """Extract comparison items from user message"""
    
    def name(self) -> Text:
        return "action_extract_comparison_items"
    
    def _extract_companies_from_text(self, text: str) -> str:
        """Extract company names from comparison query"""
        if not text:
            return None
        
        text_lower = text.lower().strip()
        
        # Company name to ticker mapping
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
        words = re.findall(r'[a-zA-Z]{2,}', text_lower)
        
        for word in words:
            if word in company_to_ticker:
                ticker = company_to_ticker[word]
                if ticker not in found_tickers:
                    found_tickers.append(ticker)
            elif word.upper() in company_to_ticker.values():
                ticker = word.upper()
                if ticker not in found_tickers:
                    found_tickers.append(ticker)
        
        # Return as comma-separated string
        if len(found_tickers) >= 2:
            return ", ".join(found_tickers[:2])
        
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
        
        return [SlotSet("comparison_items", comparison_items)]

class ActionExtractAnalysisCompany(Action):
    """Extract company name for analysis from user message"""
    
    def name(self) -> Text:
        return "action_extract_analysis_company"
    
    def _extract_company_from_query(self, query: str) -> str:
        """Extract company name from analysis query"""
        if not query:
            return None
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = [
        # ===== QUESTION WORDS =====
        'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how',
        
        # ===== ARTICLES & DETERMINERS =====
        'a', 'an', 'the', 'this', 'that', 'these', 'those',
        
        # ===== PREPOSITIONS =====
        'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
        'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
        'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near',
        'of', 'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to',
        'toward', 'under', 'underneath', 'until', 'up', 'upon', 'with', 'within',
        'without',
        
        # ===== PRONOUNS =====
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers',
        'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself',
        'ourselves', 'yourselves', 'themselves',
        
        # ===== AUXILIARY & MODAL VERBS =====
        'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having',
        'do', 'does', 'did', 'doing',
        'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
        
        # ===== CONJUNCTIONS =====
        'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
        'although', 'because', 'since', 'unless', 'while', 'whereas',
        'if', 'then', 'else', 'whether',
        
        # ===== COMMON ACTION VERBS (in queries) =====
        'show', 'tell', 'give', 'get', 'fetch', 'find', 'search', 'look',
        'see', 'check', 'view', 'display', 'provide', 'retrieve',
        'want', 'need', 'like', 'prefer', 'wish',
        
        # ===== POLITE/CONVERSATIONAL WORDS =====
        'please', 'thanks', 'thank', 'hello', 'hi', 'hey', 'goodbye', 'bye',
        
        # ===== QUANTIFIERS (general) =====
        'some', 'any', 'many', 'much', 'few', 'several', 'all', 'both', 'each',
        'every', 'either', 'neither', 'no', 'none',
        
        # ===== INTENSIFIERS & MODIFIERS =====
        'very', 'really', 'quite', 'rather', 'too', 'so', 'such',
        'just', 'only', 'even', 'still', 'also', 'already',
        
        # ===== DOMAIN-SPECIFIC NOISE (Finance) =====
        # Price queries
        'price', 'cost', 'value', 'worth', 'trading', 'currently',
        
        # Data queries
        'data', 'information', 'details', 'stats', 'statistics',
        
        # News queries
        'news', 'headlines', 'articles', 'updates', 'reports',
        
        # Analysis queries
        'analysis', 'analyze', 'performance', 'metrics',
        
        # Chart queries
        'chart', 'graph', 'plot', 'visualization', 'display',
        
        # Comparison queries
        'compare', 'comparison', 'versus', 'vs', 'difference',
        
        # General finance noise
        'stock', 'stocks', 'share', 'shares', 'ticker', 'symbol',
        'market', 'financial', 'company', 'companies',
    ]
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        if cleaned_words:
            return cleaned_words[0]
        
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
        if not query:
            return None
        
        query_lower = query.lower()
        
        # Remove noise words
        noise_words = [
        # ===== QUESTION WORDS =====
        'what', 'when', 'where', 'which', 'who', 'whom', 'whose', 'why', 'how',
        
        # ===== ARTICLES & DETERMINERS =====
        'a', 'an', 'the', 'this', 'that', 'these', 'those',
        
        # ===== PREPOSITIONS =====
        'about', 'above', 'across', 'after', 'against', 'along', 'among', 'around',
        'at', 'before', 'behind', 'below', 'beneath', 'beside', 'between', 'beyond',
        'by', 'down', 'during', 'for', 'from', 'in', 'inside', 'into', 'near',
        'of', 'off', 'on', 'onto', 'out', 'outside', 'over', 'through', 'to',
        'toward', 'under', 'underneath', 'until', 'up', 'upon', 'with', 'within',
        'without',
        
        # ===== PRONOUNS =====
        'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'my', 'your', 'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers',
        'ours', 'theirs', 'myself', 'yourself', 'himself', 'herself', 'itself',
        'ourselves', 'yourselves', 'themselves',
        
        # ===== AUXILIARY & MODAL VERBS =====
        'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having',
        'do', 'does', 'did', 'doing',
        'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
        
        # ===== CONJUNCTIONS =====
        'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
        'although', 'because', 'since', 'unless', 'while', 'whereas',
        'if', 'then', 'else', 'whether',
        
        # ===== COMMON ACTION VERBS (in queries) =====
        'show', 'tell', 'give', 'get', 'fetch', 'find', 'search', 'look',
        'see', 'check', 'view', 'display', 'provide', 'retrieve',
        'want', 'need', 'like', 'prefer', 'wish',
        
        # ===== POLITE/CONVERSATIONAL WORDS =====
        'please', 'thanks', 'thank', 'hello', 'hi', 'hey', 'goodbye', 'bye',
        
        # ===== QUANTIFIERS (general) =====
        'some', 'any', 'many', 'much', 'few', 'several', 'all', 'both', 'each',
        'every', 'either', 'neither', 'no', 'none',
        
        # ===== INTENSIFIERS & MODIFIERS =====
        'very', 'really', 'quite', 'rather', 'too', 'so', 'such',
        'just', 'only', 'even', 'still', 'also', 'already',
        
        # ===== DOMAIN-SPECIFIC NOISE (Finance) =====
        # Price queries
        'price', 'cost', 'value', 'worth', 'trading', 'currently',
        
        # Data queries
        'data', 'information', 'details', 'stats', 'statistics',
        
        # News queries
        'news', 'headlines', 'articles', 'updates', 'reports',
        
        # Analysis queries
        'analysis', 'analyze', 'performance', 'metrics',
        
        # Chart queries
        'chart', 'graph', 'plot', 'visualization', 'display',
        
        # Comparison queries
        'compare', 'comparison', 'versus', 'vs', 'difference',
        
        # General finance noise
        'stock', 'stocks', 'share', 'shares', 'ticker', 'symbol',
        'market', 'financial', 'company', 'companies',
    ]
        
        words = query_lower.split()
        cleaned_words = [w for w in words if w not in noise_words]
        
        if cleaned_words:
            return " ".join(cleaned_words)
        
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
        
        asset_name = self._extract_asset_from_query(query_to_use)
        
        return [SlotSet("chart_asset", asset_name)]

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
        
        if not security_name or len(security_name) < 2:
            dispatcher.utter_message(
                text="I couldn't identify a valid ticker. Please provide a ticker symbol."
            )
            return [SlotSet("security_name", None)]
        
        # Check if it's a cryptocurrency
        is_crypto = security_name.endswith('-USD') and len(security_name.split('-')[0]) <= 5
        
        if is_crypto:
            # Use yfinance for crypto
            return self._fetch_crypto_data_yfinance(security_name, dispatcher)
        else:
            # Use Alpha Vantage for real-time stock data with key rotation
            return self._fetch_stock_data_alpha_vantage(security_name, dispatcher)
    
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
        
        if not news_topic:
            news_output = "Please specify what topic or company you'd like news about."
            return [SlotSet("news_output", news_output)]
        
        # Convert topic to ticker if it's a company name
        ticker = _clean_ticker(news_topic)
        
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
        
        if not chart_asset:
            dispatcher.utter_message(text="📊 Which asset would you like to see a chart for? Try: 'Bitcoin chart', 'Apple chart', or 'S&P 500 chart'")
            return []
        
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
        """Generate chart for market index"""
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
