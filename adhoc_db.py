import yfinance as yf
from app import app, db
from models import Stock
from sqlalchemy import text

def add_address_column():
    """
    Adds an 'address' column to the 'stock' table if it doesn't exist.
    This uses raw SQL for simplicity in a one-off script.
    """
    with app.app_context():
        try:
            # Using a raw text query to add the column.
            # This is a common approach for ad-hoc schema changes.
            # The VARCHAR2(500) is suitable for Oracle. For SQLite, it would be TEXT.
            with db.engine.connect() as connection:
                connection.execute(text("ALTER TABLE stock ADD address VARCHAR2(500)"))
                connection.commit()
            print("Successfully added 'address' column to the stock table.")
        except Exception as e:
            # It's common for this to fail if the column already exists.
            if 'ORA-01430' in str(e) or 'duplicate column name' in str(e).lower():
                print("Column 'address' already exists in the stock table.")
            else:
                print(f"An error occurred while adding column: {e}")

def populate_stock_addresses():
    """
    Fetches the address for each stock from yfinance and updates the database.
    """
    with app.app_context():
        stocks = Stock.query.all()
        print(f"Found {len(stocks)} stocks to process.")

        for stock in stocks:
            if stock.address: # Skip if address is already populated
                continue
            
            try:
                ticker_info = yf.Ticker(stock.tickersymbol).info
                
                # Construct the address string from available parts
                parts = [ticker_info.get(key) for key in ['address1', 'city', 'state', 'zip', 'country'] if ticker_info.get(key)]
                address = ", ".join(parts)

                if address:
                    stock.address = address
                    print(f"Updating address for {stock.tickersymbol}: {address[:50]}...")
                else:
                    print(f"No address found for {stock.tickersymbol}.")
            except Exception as e:
                print(f"Could not fetch info for {stock.tickersymbol}: {e}")
        
        db.session.commit()
        print("\nFinished populating stock addresses.")

if __name__ == "__main__":
    print("--- Ad-hoc DB Operations ---")
    add_address_column()
    populate_stock_addresses()