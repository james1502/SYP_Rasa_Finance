Framework of Rasa on finance
1.	Frontend (Mobile App)
Platforms: iOS and android
Features:
1.1 chat interface with custom UI
1.2	pre-set question suggestions
1.3	Support English, Traditional and Simplified Chinese

2.	Backend (Rasa, database)
2.1	Rasa:
Intent Classification
	2.1.1 handles Chinese variants, Cantonese,
	2.1.2 Lookup Tables for stock and financial terms
  2.1.3 response selector
Training Data:
  2.1.4 Intents, entities, responses defined in Rasa NLU format
2.1.5 Lookup tables for stock names and financial terms

2.2 database
	Data Stored:
2.2.1	User portfolios (buy/ sell records)
2.2.2	Financial glossary
2.2.3	Cached stock data (real time) 

3.	Data
3.1 real time
3.2 historical

4.	Key Functional
4.1 stock info
4.2 stock analysis
4.3 portfolio management
4.4 financial glossary (explanations of financial terms
5. data flow
 Input  →  moblic app  → api  → rasa  → call api for data  → get data from database  → response constructed  → return to mobile app  →  output
