import sys
import yfinance as yf
import io
import pandas as pd
from app import app, db
from models import Stock, User
from werkzeug.security import generate_password_hash
from urllib.request import Request, urlopen
from sqlalchemy import text

def get_sp500_tickers():
    """Fetches S&P 500 tickers from Wikipedia."""
    print("Fetching S&P 500 tickers...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    # Add a User-Agent header to mimic a browser request
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    webpage = urlopen(req).read()
    tables = pd.read_html(webpage)
    sp500_table = tables[0]
    # The ticker symbol is in the 'Symbol' column
    return sp500_table['Symbol'].tolist()

def get_nifty500_tickers():
    """Fetches NIFTY 500 tickers from Wikipedia."""
    print("Fetching NIFTY 500 tickers...")
    # This URL points to the CSV for all equity stocks on NSE.
    url = 'https://archives.nseindia.com/content/equities/EQUITY_L.csv'
    # Add a User-Agent header to mimic a browser request
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        # Use pandas to read the CSV data directly from the downloaded content
        all_stocks_df = pd.read_csv(io.StringIO(webpage.decode('utf-8')))
        # Filter for stocks in the 'EQ' series, which represents regular equity.
        # The ticker symbol is in the 'Symbol' column
        # We need to append '.NS' for yfinance to recognize them as NSE stocks
        return [f"{ticker}.NS" for ticker in all_stocks_df['SYMBOL'].tolist()]
    except Exception as e:
        print(f"Could not fetch NIFTY 500 page: {e}")
        return []

def populate_initial_stocks():
    print("Populating initial stocks...")
    
    # Combine tickers from both indices
    all_tickers = get_sp500_tickers() + get_nifty500_tickers()
    
    for ticker_symbol in all_tickers:
        existing_stock = Stock.query.filter_by(tickersymbol=ticker_symbol).first()
        if not existing_stock:
            try:
                # Fetch stock info to get a name, if possible
                ticker_info = yf.Ticker(ticker_symbol).info
                stock_name = ticker_info.get('longName', ticker_symbol)
                sector = ticker_info.get('sector', 'N/A') # Get sector info
                market = ticker_info.get('market', 'N/A')
                currency = ticker_info.get('currency', 'N/A')
                address = ticker_info.get('address', 'N/A')
                # Exchange can be derived from market or currency, or fetched directly
                exchange = ticker_info.get('exchange', 'NSE' if '.NS' in ticker_symbol else 'NMS')
                
                new_stock = Stock(name=stock_name, tickersymbol=ticker_symbol, exchange=exchange, sector=sector, market=market, currency=currency)
                db.session.add(new_stock)
                db.session.commit() # Commit inside loop to make each stock visible immediately
                print(f"Added new stock: {ticker_symbol} - {stock_name}")
            except Exception as e:
                print(f"Could not add stock {ticker_symbol}: {e}")
    print("Initial stock population complete.")

def create_admin_user():
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            hashed_password = generate_password_hash('passwd', method='pbkdf2:sha256')
            new_admin = User(username='admin', password_hash=hashed_password, is_admin=True)
            db.session.add(new_admin)
            db.session.commit()
            print("Admin user 'admin' created.")

def clean_all_tables():
    """
    Connects to the database and drops all tables.
    """
    # Use the application context to ensure everything is configured correctly
    with app.app_context():
        print("Connecting to the database to drop all tables in a specific order...")
        try:
            # Drop tables in reverse order of creation to respect foreign key constraints.
            # We wrap each drop in its own try/except to handle cases where a table might not exist.
            tables_to_drop = ['portfolio', 'transaction', 'stock', 'users'] # 'price' table is already removed
            for table_name in tables_to_drop:
                try:
                    db.session.execute(text(f'DROP TABLE {table_name}'))
                    print(f"Dropped table {table_name}.")
                except Exception as e:
                    # ORA-00942: table or view does not exist. This is safe to ignore.
                    if 'ORA-00942' in str(e):
                        print(f"Table {table_name} does not exist, skipping.")
                    else:
                        raise # Re-raise other errors
            db.session.commit()
            print("Finished dropping tables.")
        except Exception as e:
            print(f"An error occurred while dropping tables: {e}")

def initialize_database():
    """
    Creates all database tables, populates initial stocks, and creates the admin user.
    """
    with app.app_context():
        print("Creating all database tables...")
        db.create_all()
        print("Tables created successfully.")        
        create_admin_user()

def reset_database():
    """
    Cleans all tables and then re-initializes the database.
    """
    clean_all_tables()
    initialize_database()

if __name__ == "__main__":
    print("\n--- Database Management Menu ---")
    print("1. Initialize Database (Create tables and admin user)")
    print("2. Reset Database (Drop all tables and re-initialize)")
    print("3. Clean Database (Drop all tables)")
    print("4. Populate Initial Stocks (S&P 500 & NIFTY 500)")
    print("5. Exit")
    
    choice = input("Please select an option (1-5): ")

    if choice == '1':
        print("\nOperation: Initialize Database.")
        print("This will create all tables and populate them with initial stocks and the admin user.")
        confirmation = input("Are you sure you want to proceed? (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            initialize_database()
        else:
            print("Operation cancelled.")
    elif choice == '2':
        print("\nOperation: Reset Database.")
        print("This will permanently DROP all tables and then recreate them with initial data.")
        confirmation = input("Are you sure you want to proceed? This is irreversible. (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            reset_database()
        else:
            print("Operation cancelled.")
    elif choice == '3':
        print("\nOperation: Clean Database.")
        print("This will permanently DROP all tables and delete all data.")
        confirmation = input("Are you sure you want to proceed? This is irreversible. (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            clean_all_tables()
        else:
            print("Operation cancelled.")
    elif choice == '4':
        print("\nOperation: Populate Initial Stocks.")
        print("This will fetch and add stocks from S&P 500 and NIFTY 500 if they don't already exist.")
        confirmation = input("Are you sure you want to proceed? (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            with app.app_context():
                populate_initial_stocks()
        else:
            print("Operation cancelled.")
    elif choice == '5':
        print("Exiting.")
    else:
        print("Invalid option. Please choose a number between 1 and 5.")