import sys
import yfinance as yf
from app import app, db
from models import Stock, User
from clean_database import clean_all_tables
from werkzeug.security import generate_password_hash

SAMPLE_HIGH_VOLUME_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "PG", "XOM", "HD", "UNH", "MA", "VZ", "DIS", "ADBE",
    "NFLX", "PYPL", "INTC", "CMCSA", "PEP", "KO", "PFE", "MRK", "ABT", "NKE",
    "BAC", "C", "WFC", "GS", "MS", "AMGN", "GILD", "BMY", "CVS", "MDLZ",
    "SBUX", "GM", "F", "GE", "BA", "CAT", "MMM", "HON", "RTX", "LMT",
    "GD", "NOC", "SPG", "PLD", "EQIX", "AMT", "CCI", "DUK", "D", "SO",
    "NEE", "XEL", "PCG", "AEP", "EXC", "PEG", "SRE", "WEC", "ED", "EIX",
    "DTE", "CMS", "ETR", "FE", "CNP", "AES", "NI", "PNW", "PPL", "ATO",
    "LNT", "MGEE", "OGE", "POR", "SJI", "SR", "WTRG", "XELB", "YORW", "ZBRA",
    "CRM", "AMD", "QCOM", "TXN", "AVGO", "CSCO", "ACN", "ORCL", "SAP", "IBM",
    "ADSK", "SNPS", "CDNS", "ANSS", "FTNT", "PANW", "NOW", "WDAY", "SPLK", "OKTA"
]

def populate_initial_stocks():
    print("Populating initial stocks...")
    for ticker_symbol in SAMPLE_HIGH_VOLUME_TICKERS:
        existing_stock = Stock.query.filter_by(tickersymbol=ticker_symbol).first()
        if not existing_stock:
            try:
                # Fetch stock info to get a name, if possible
                ticker_info = yf.Ticker(ticker_symbol).info
                stock_name = ticker_info.get('longName', ticker_symbol)
                exchange = ticker_info.get('exchange', 'N/A')
                sector = ticker_info.get('sector', 'N/A') # Get sector info

                new_stock = Stock(name=stock_name, tickersymbol=ticker_symbol, exchange=exchange, sector=sector)
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

def initialize_database():
    """
    Creates all database tables, populates initial stocks, and creates the admin user.
    """
    with app.app_context():
        print("Creating all database tables...")
        db.create_all()
        print("Tables created successfully.")
        
        populate_initial_stocks()
        create_admin_user()

def reset_database():
    """
    Cleans all tables and then re-initializes the database.
    """
    clean_all_tables()
    initialize_database()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'reset':
        confirmation = input("Are you sure you want to RESET the database? This will delete all existing data. (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            reset_database()
        else:
            print("Database reset cancelled by user.")
    else:
        confirmation = input("Are you sure you want to initialize the database and create tables? (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            initialize_database()
        else:
            print("Database initialization cancelled by user.")