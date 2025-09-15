import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

def clean_all_tables():
    """
    Connects to the database and deletes all data from all tables.
    """
    load_dotenv() # Load environment variables from .env file

    # --- Database Configuration (copied from app.py) ---
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_DSN = os.getenv('DB_DSN')
    WALLET_PASSWORD = os.getenv('WALLET_PASSWORD')
    WALLET_LOCATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallet')

    # Construct the database URI and engine options
    db_uri = f'oracle+oracledb://{DB_USER}:{DB_PASSWORD}@{DB_DSN}'
    engine_options = {
        'connect_args': {
            'config_dir': WALLET_LOCATION,
            'wallet_location': WALLET_LOCATION,
            'wallet_password': WALLET_PASSWORD
        }
    }
    
    engine = create_engine(db_uri, **engine_options)

    # --- Table Cleaning Logic ---
    # The order is important to respect foreign key constraints
    # Delete from child tables before parent tables.
    tables_to_clean = ['price', 'portfolio', 'transaction', 'stock', 'users']

    with engine.connect() as connection:
        print("Connecting to the database to clean tables...")
        for table_name in tables_to_clean:
            print(f"Cleaning table: {table_name}...")
            connection.execute(text(f'DELETE FROM {table_name}'))
        connection.commit()
        print("All tables have been cleaned successfully.")

if __name__ == "__main__":
    confirmation = input("Are you sure you want to delete all data from all tables? This cannot be undone. (Y/N): ")
    if confirmation.strip().upper() == 'Y':
        clean_all_tables()
    else:
        print("Operation cancelled by user.")