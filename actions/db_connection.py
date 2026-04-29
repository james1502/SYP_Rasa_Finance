from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Optional

class MongoDBConnection:
    def __init__(self):
        self.client = MongoClient("mongodb://localhost:27017/")
        self.db = self.client["transactions_db"]
        self.transactions = self.db["transactions"]
    
    def save_transaction(self, transaction_data: Dict) -> str:
        """Save a transaction and return its ID"""
        transaction_data["created_at"] = datetime.utcnow()
        result = self.transactions.insert_one(transaction_data)
        return str(result.inserted_id)
    
    def get_all_transactions(self) -> List[Dict]:
        """Retrieve all transactions"""
        transactions = list(self.transactions.find())
        # Convert ObjectId to string for each transaction
        for transaction in transactions:
            transaction["_id"] = str(transaction["_id"])
        return transactions
    
    def get_transactions_by_asset(self, asset: str) -> List[Dict]:
        """Get transactions for a specific asset (case-insensitive)"""
        # Use regex for case-insensitive matching
        import re
        pattern = re.compile(f"^{re.escape(asset)}$", re.IGNORECASE)
        transactions = list(self.transactions.find({"asset": pattern}))
        for transaction in transactions:
            transaction["_id"] = str(transaction["_id"])
        return transactions
    
    def get_transactions_by_type(self, transaction_type: str) -> List[Dict]:
        """Get transactions by type (buy, sell, etc.)"""
        transactions = list(self.transactions.find({"transaction_type": transaction_type}))
        for transaction in transactions:
            transaction["_id"] = str(transaction["_id"])
        return transactions
    
    def close(self):
        """Close the database connection"""
        self.client.close()

# Create a global instance
mongo_db = MongoDBConnection()