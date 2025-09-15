import sys
import yfinance as yf
from app import app, db
from models import Stock, User
from werkzeug.security import generate_password_hash

SAMPLE_HIGH_VOLUME_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "V",
    "ORCL","INFY.NS"
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
                market = ticker_info.get('market', 'N/A')
                currency = ticker_info.get('currency', 'N/A')

                new_stock = Stock(name=stock_name, tickersymbol=ticker_symbol, exchange=exchange, sector=sector, market=market, currency=currency)
                db.session.add(new_stock)
                db.session.commit() # Commit inside loop to make each stock visible immediately
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
        print("Connecting to the database to drop all tables...")
        # This command introspects the database and drops all known tables.
        db.drop_all()
        print("All tables have been dropped successfully.")

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
    command = None
    if len(sys.argv) > 1:
        command = sys.argv[1]

    if command == 'reset':
        confirmation = input("Are you sure you want to RESET the database? This will drop all tables and recreate them. (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            reset_database()
        else:
            print("Database reset cancelled.")
    elif command == 'clean':
        confirmation = input("Are you sure you want to CLEAN (DROP) all database tables? This is irreversible. (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            clean_all_tables()
        else:
            print("Database clean cancelled.")
    elif command == 'init':
        confirmation = input("Are you sure you want to initialize the database and create tables? (Y/N): ")
        if confirmation.strip().upper() == 'Y':
            initialize_database()
        else:
            print("Database initialization cancelled.")
    else:
        print("Usage: python manage_db.py [init|reset|clean]")