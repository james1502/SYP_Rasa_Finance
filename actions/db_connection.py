from pymongo import MongoClient
from pymongo.collection import Collection
from datetime import datetime
from typing import Dict, List, Optional
import re

class MongoDBConnection:
    def __init__(self) -> None:
        self.client: Optional[MongoClient] = None
        self.db: Optional[object] = None
        self.transactions: Optional[Collection] = None
    
    def ensure_connected(self):
        if self.client is None:
            try:
                self.client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
                self.client.admin.command('ping')
                self.db = self.client["transactions_db"]
                self.transactions = self.db["transactions"]
            except Exception as e:
                raise RuntimeError(f"Failed to connect to MongoDB: {e}")
    
    def convert_object_ids(self, transactions: List[Dict]) -> List[Dict]:
        for transaction in transactions:
            transaction["_id"] = str(transaction["_id"])
        return transactions

    def get_transactions_collection(self) -> Collection:
        """Return the connected transactions collection or fail explicitly."""
        self.ensure_connected()
        if self.transactions is None:
            raise RuntimeError("MongoDB connection is not available")
        return self.transactions
    
    def save_transaction(self, transaction_data: Dict) -> str:
        """Save a transaction and return its ID"""
        transactions = self.get_transactions_collection()
        transaction_data["created_at"] = datetime.utcnow()
        result = transactions.insert_one(transaction_data)
        return str(result.inserted_id)
    
    def get_all_transactions(self) -> List[Dict]:
        """Retrieve all transactions"""
        transactions = list(self.get_transactions_collection().find())
        return self.convert_object_ids(transactions)
    
    def get_transactions_by_asset(self, asset: str) -> List[Dict]:
        """Get transactions for a specific asset (case-insensitive)"""
        transactions_collection = self.get_transactions_collection()
        # Use regex for case-insensitive matching
        pattern = re.compile(f"^{re.escape(asset)}$", re.IGNORECASE)
        transactions = list(transactions_collection.find({"asset": pattern}))
        return self.convert_object_ids(transactions)
    
    def get_transactions_by_type(self, transaction_type: str) -> List[Dict]:
        """Get transactions by type (buy, sell, etc.)"""
        transactions = list(self.get_transactions_collection().find({"transaction_type": transaction_type}))
        return self.convert_object_ids(transactions)
    
    def close(self):
        """Close the database connection"""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            self.transactions = None

# Create a global instance (pure - no I/O at import time)
mongo_db = MongoDBConnection()