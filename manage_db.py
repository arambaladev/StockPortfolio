import sys
from app import app, db, populate_initial_stocks, create_admin_user
from clean_database import clean_all_tables

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