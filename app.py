from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from functools import wraps
from models import db, Stock, Transaction, Portfolio, Price, User
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
import random
import datetime
import yfinance as yf
from sqlalchemy import or_

def _xnpv(rate, cash_flows, dates):
    """
    Calculate the Net Present Value (NPV) for a series of cash flows
    occurring at irregular intervals.
    """
    if rate <= -1.0:
        return float('inf')
    
    min_date = min(dates)
    npv = 0
    for i in range(len(cash_flows)):
        days = (dates[i] - min_date).days
        npv += cash_flows[i] / (1 + rate)**(days / 365.0)
    return npv

def calculate_xirr(cash_flows, dates, guess=0.1):
    """
    Calculate the Extended Internal Rate of Return (XIRR).
    Uses Newton-Raphson method.
    """
    if not cash_flows or len(cash_flows) != len(dates):
        return None # Or raise an error

    # Sort cash flows and dates by date
    sorted_data = sorted(zip(dates, cash_flows))
    dates = [d for d, cf in sorted_data]
    cash_flows = [cf for d, cf in sorted_data]

    # Newton-Raphson method
    for i in range(100): # Max 100 iterations
        if 1 + guess <= 0: # Ensure (1 + rate) is positive for real number calculations
            return None
        npv = _xnpv(guess, cash_flows, dates)
        
        # Calculate derivative of NPV
        deriv_npv = 0
        min_date = min(dates)
        for j in range(len(cash_flows)):            
            days = (dates[j] - min_date).days
            if days == 0: # Avoid division by zero for the first cash flow
                continue
            deriv_npv -= cash_flows[j] * days / 365.0 * (1 + guess)**(-days / 365.0 - 1)
        
        if abs(npv) < 0.000001: # Convergence check
            return guess
        if deriv_npv == 0: # Avoid division by zero
            return None # Or handle as an error
        
        guess = guess - npv / deriv_npv
    
    return None # Did not converge

load_dotenv() # Load environment variables from .env file

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key' # Replace with a strong secret key

# Configure the database
# Database configuration from environment variables
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DSN = os.getenv('DB_DSN')
WALLET_PASSWORD = os.getenv('WALLET_PASSWORD')
WALLET_LOCATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wallet')

# Use this for SQLite
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stocks.db'

# Use this for Oracle Autonomous Database

app.config['SQLALCHEMY_DATABASE_URI'] = f'oracle+oracledb://{DB_USER}:{DB_PASSWORD}@{DB_DSN}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'config_dir': WALLET_LOCATION,
        'wallet_location': WALLET_LOCATION,
        'wallet_password': WALLET_PASSWORD
    }
}

# Autonomous DB Config Ends
db.init_app(app)

@app.template_filter('format_currency')
def format_currency(value):
    """Format a value as currency with comma separators."""
    return "{:,.2f}".format(value)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index')) # Redirect to index or login
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            update_user_portfolio_prices(user.id)
            return redirect(url_for('index', login_success='true'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
        else:
            hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(username=username, password_hash=hashed_password, is_admin=False)
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    login_success = request.args.get('login_success') == 'true'
    sort_by = request.args.get('sort_by', 'value') # Default sort by value
    order = request.args.get('order', 'desc') # Default order descending
    reverse = (order == 'desc')

    # Fetch the current USD to INR exchange rate
    usdinr_rate = 83.0 # Default fallback rate
    try:
        ticker = yf.Ticker("USDINR=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            usdinr_rate = hist['Close'].iloc[-1]
    except Exception as e:
        print(f"Could not fetch USDINR exchange rate, using default. Error: {e}")

    portfolio_items = Portfolio.query.filter_by(user_id=session['user_id']).all()
    
    # Data structures for multi-currency portfolios
    usd_portfolio_data = []
    inr_portfolio_data = []
    usd_total_value = 0.0
    usd_invested_amount = 0.0
    inr_total_value = 0.0
    inr_invested_amount = 0.0
    usd_sector_data = {} # For USD portfolio
    inr_sector_data = {} # For INR portfolio

    for item in portfolio_items:
        # Get latest price from Price table for display in portfolio
        price_entry = Price.query.filter_by(tickersymbol=item.tickersymbol).order_by(Price.date.desc()).first()
        latest_price = price_entry.price if price_entry else 0.0
        item_value = item.quantity * latest_price

        # Prepare data for XIRR calculation
        cash_flows = []
        dates = []

        # Get all transactions for the current stock for the logged-in user
        transactions = Transaction.query.filter_by(tickersymbol=item.tickersymbol, user_id=session['user_id']).order_by(Transaction.date).all()

        for transaction in transactions:
            if transaction.operation == 'Buy':
                cash_flows.append(-transaction.quantity * transaction.price)
            else: # Sell
                cash_flows.append(transaction.quantity * transaction.price)
            dates.append(datetime.datetime.strptime(transaction.date, '%Y-%m-%d').date())

        # Add current value as a final cash flow
        if item.quantity > 0 and latest_price > 0:
            cash_flows.append(item.quantity * latest_price)
            dates.append(datetime.date.today())

        # Calculate FIFO Cost Basis
        cost_basis = calculate_fifo_cost_basis(item.tickersymbol, session['user_id'], item.quantity)
        stock_info = Stock.query.filter_by(tickersymbol=item.tickersymbol).first()

        xirr_value = None
        if len(cash_flows) > 1: # XIRR requires at least two cash flows
            try:
                xirr_value = calculate_xirr(cash_flows, dates)
            except Exception as e:
                print(f"Error calculating XIRR for {item.tickersymbol}: {e}")

        item_data = {
            'tickersymbol': item.tickersymbol,
            'quantity': item.quantity,
            'latest_price': latest_price,
            'value': item_value,
            'percentage': 0.0, # Placeholder, will be calculated later
            'xirr': xirr_value,
            'cost_basis': cost_basis,
            'currency': stock_info.currency if stock_info else 'USD'
        }

        # Segregate data based on currency
        if item_data['currency'] == 'INR':
            inr_portfolio_data.append(item_data)
            inr_total_value += item_value
            inr_invested_amount += cost_basis
            # Aggregate INR sector data
            sector = stock_info.sector if stock_info and stock_info.sector else 'Uncategorized'
            inr_sector_data[sector] = inr_sector_data.get(sector, 0) + item_value
        else: # Default to USD
            usd_portfolio_data.append(item_data)
            usd_total_value += item_value
            usd_invested_amount += cost_basis
            # Aggregate USD sector data
            sector = stock_info.sector if stock_info and stock_info.sector else 'Uncategorized'
            usd_sector_data[sector] = usd_sector_data.get(sector, 0) + item_value

    # Calculate percentage of portfolio for each item within its currency group
    if usd_total_value > 0:
        for item in usd_portfolio_data:
            item['percentage'] = (item['value'] / usd_total_value) * 100
    if inr_total_value > 0:
        for item in inr_portfolio_data:
            item['percentage'] = (item['value'] / inr_total_value) * 100

    # Sort the portfolio data based on query parameters
    if usd_portfolio_data:
        sort_key = sort_by if sort_by in usd_portfolio_data[0] else 'value'
        usd_portfolio_data.sort(key=lambda x: x[sort_key], reverse=reverse)
    if inr_portfolio_data:
        sort_key = sort_by if sort_by in inr_portfolio_data[0] else 'value'
        inr_portfolio_data.sort(key=lambda x: x[sort_key], reverse=reverse)

    return render_template('index.html', 
                           usd_portfolio_data=usd_portfolio_data,
                           inr_portfolio_data=inr_portfolio_data,
                           usd_total_value=usd_total_value,
                           usd_invested_amount=usd_invested_amount,
                           inr_total_value=inr_total_value,
                           inr_invested_amount=inr_invested_amount,
                           login_success=login_success, usd_sector_data=usd_sector_data,
                           inr_sector_data=inr_sector_data,
                           usdinr_rate=usdinr_rate)

@app.route('/add', methods=['GET', 'POST'])
@admin_required
def add_stock():
    if request.method == 'POST':
        name = request.form['name']
        tickersymbol = request.form['tickersymbol'].upper() # Convert to uppercase
        exchange = request.form['exchange']

        # Validate ticker symbol using yfinance
        try:
            ticker = yf.Ticker(tickersymbol)
            info = ticker.info # Attempt to get info to validate existence
            if not info or 'regularMarketPrice' not in info: # A common key that indicates valid stock data
                return f"Ticker symbol '{tickersymbol}' not found or no market data available.", 400
            
            # Fetch additional details
            sector = info.get('sector', 'N/A')
            market = info.get('market', 'N/A')
            currency = info.get('currency', 'N/A')
        except Exception as e:
            return f"Error validating ticker symbol '{tickersymbol}': {e}", 400

        if not exchange:
            exchange = 'NYSE'

        new_stock = Stock(name=name, tickersymbol=tickersymbol, exchange=exchange, sector=sector, market=market, currency=currency)
        db.session.add(new_stock)
        db.session.commit()
        return redirect(url_for('stocks_list')) # Redirect to stocks_list after adding
    return redirect(url_for('stocks_list')) # Redirect GET requests to the stocks list

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_stock(id):
    stock = Stock.query.get_or_404(id)
    if request.method == 'POST':
        stock.name = request.form['name']
        stock.tickersymbol = request.form['tickersymbol'].upper() # Convert to uppercase
        stock.exchange = request.form['exchange']
        stock.sector = request.form['sector']
        stock.market = request.form['market']
        stock.currency = request.form['currency']

        # Validate ticker symbol using yfinance
        try:
            ticker = yf.Ticker(stock.tickersymbol)
            info = ticker.info
            if not info or 'regularMarketPrice' not in info:
                return f"Ticker symbol '{stock.tickersymbol}' not found or no market data available.", 400
            
            # Update additional details on edit as well
            stock.sector = info.get('sector', stock.sector) # Keep old value if new one not found
            stock.market = info.get('market', 'N/A')
            stock.currency = info.get('currency', 'N/A')
        except Exception as e:
            return f"Error validating ticker symbol '{stock.tickersymbol}': {e}", 400

        if not stock.exchange:
            stock.exchange = 'NYSE'

        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_stock.html', stock=stock)

@app.route('/delete/<int:id>')
@admin_required
def delete_stock(id):
    stock = Stock.query.get_or_404(id)

    # Check for associated transactions
    transactions_count = Transaction.query.filter_by(tickersymbol=stock.tickersymbol).count()
    if transactions_count > 0:
        return f"Cannot delete stock {stock.tickersymbol} because there are {transactions_count} associated transactions.", 400 # Bad Request

    db.session.delete(stock)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/stocks')
@admin_required
def stocks_list():
    stocks = Stock.query.all()
    return render_template('stocks.html', stocks=stocks)

def get_current_stock_quantity(tickersymbol, transaction_date, user_id, exclude_transaction_id=None):
    buy_query = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Buy',
        Transaction.date <= transaction_date,
        Transaction.user_id == user_id
    )
    sell_query = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Sell',
        Transaction.date <= transaction_date,
        Transaction.user_id == user_id
    )

    if exclude_transaction_id:
        buy_query = buy_query.filter(Transaction.id != exclude_transaction_id)
        sell_query = sell_query.filter(Transaction.id != exclude_transaction_id)

    buy_quantity = buy_query.scalar() or 0
    sell_quantity = sell_query.scalar() or 0

    return buy_quantity - sell_quantity

def update_portfolio(tickersymbol, user_id):
    # Calculate total quantity
    buy_quantity = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Buy',
        Transaction.user_id == user_id
    ).scalar() or 0

    sell_quantity = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Sell',
        Transaction.user_id == user_id
    ).scalar() or 0

    total_quantity = buy_quantity - sell_quantity

    # Get latest price from Price table
    # Order by date descending to get the most recent price
    price_entry = Price.query.filter_by(tickersymbol=tickersymbol).order_by(Price.date.desc()).first()
    latest_price = price_entry.price if price_entry else 0.0

    # Calculate value
    current_value = total_quantity * latest_price

    # Update or create Portfolio entry
    portfolio_entry = Portfolio.query.filter_by(tickersymbol=tickersymbol, user_id=user_id).first()
    if portfolio_entry:
        if total_quantity == 0:
            db.session.delete(portfolio_entry)
        else:
            portfolio_entry.quantity = total_quantity
            portfolio_entry.value = current_value
    else:
        if total_quantity > 0: # Only add if there's a positive quantity
            new_portfolio_entry = Portfolio(tickersymbol=tickersymbol, quantity=total_quantity, value=current_value, user_id=user_id)
            db.session.add(new_portfolio_entry)
    db.session.commit()

def update_user_portfolio_prices(user_id):
    # Get all unique ticker symbols from the user's portfolio
    portfolio_tickers = db.session.query(Portfolio.tickersymbol).filter_by(user_id=user_id).distinct().all()
    portfolio_tickers = [ticker[0] for ticker in portfolio_tickers] # Extract ticker symbols from tuples

    today = datetime.date.today().isoformat()

    for tickersymbol in portfolio_tickers:
        try:
            ticker = yf.Ticker(tickersymbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest_price = round(hist['Close'].iloc[-1], 2)

                # Check if a price for today already exists for this stock
                price_entry = Price.query.filter_by(tickersymbol=tickersymbol, date=today).first()
                if price_entry:
                    price_entry.price = latest_price
                else:
                    new_price = Price(tickersymbol=tickersymbol, date=today, price=latest_price)
                    db.session.add(new_price)
            else:
                print(f"No historical data found for {tickersymbol} for today.")
        except Exception as e:
            print(f"Error updating price for {tickersymbol}: {e}")
    
    db.session.commit() # Commit all price changes at once


def calculate_fifo_cost_basis(tickersymbol, user_id, current_quantity):
    transactions = Transaction.query.filter_by(tickersymbol= tickersymbol, user_id=user_id).order_by(Transaction.date, Transaction.id).all() 
    
    # List of (quantity, cost_per_share) for each lot purchased
    lots = []
    
    for transaction in transactions:
        if transaction.operation == 'Buy':
            lots.append({'quantity': transaction.quantity, 'cost_per_share': transaction.price})
        elif transaction.operation == 'Sell':
            sell_quantity = transaction.quantity
            while sell_quantity > 0 and lots:
                oldest_lot = lots[0]
                if oldest_lot['quantity'] <= sell_quantity:
                    sell_quantity -= oldest_lot['quantity']
                    lots.pop(0) # Remove the entire lot
                else:
                    oldest_lot['quantity'] -= sell_quantity
                    sell_quantity = 0 # All sold quantity accounted for
    
    # Calculate cost basis for remaining lots
    cost_basis = 0.0
    for lot in lots:
        cost_basis += lot['quantity'] * lot['cost_per_share']
        
    return cost_basis


@app.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    per_page = 15 # You can adjust this number
    pagination = Transaction.query.filter_by(user_id=session['user_id']).order_by(Transaction.date.desc(), Transaction.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    transactions = pagination.items
    stocks = Stock.query.order_by(Stock.tickersymbol).all() # Fetch all stocks, ordered alphabetically
    # Determine the latest ticker symbol for defaulting. Assuming latest means last alphabetically.
    latest_tickersymbol = stocks[-1].tickersymbol if stocks else ''
    return render_template('transactions.html', transactions=transactions, stocks=stocks, latest_tickersymbol=latest_tickersymbol, pagination=pagination)

@app.route('/prices')
@admin_required
def prices():
    prices = Price.query.all()
    stocks = Stock.query.all() # Fetch all stocks for the modal dropdown
    return render_template('prices.html', prices=prices, stocks=stocks)

@app.route('/add_price', methods=['GET', 'POST'])
@admin_required
def add_price():
    if request.method == 'POST':
        tickersymbol = request.form['tickersymbol']
        date = request.form['date']
        price = request.form['price']

        # Check if the stock exists
        stock = Stock.query.filter_by(tickersymbol=tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        new_price = Price(tickersymbol=tickersymbol, date=date, price=float(price))
        db.session.add(new_price)
        db.session.commit()
        return redirect(url_for('prices'))
    
    return redirect(url_for('prices')) # Redirect GET requests to the prices list

@app.route('/edit_price/<int:id>', methods=['GET', 'POST'])
@admin_required
def edit_price(id):
    price_entry = Price.query.get_or_404(id)
    if request.method == 'POST':
        price_entry.tickersymbol = request.form['tickersymbol']
        price_entry.date = request.form['date']
        price_entry.price = float(request.form['price'])

        # Check if the stock exists
        stock = Stock.query.filter_by(tickersymbol=price_entry.tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        db.session.commit()
        return redirect(url_for('prices'))
    
    stocks = Stock.query.all() # To populate dropdown
    return render_template('edit_price.html', price_entry=price_entry, stocks=stocks)

@app.route('/delete_price/<int:id>')
@admin_required
def delete_price(id):
    price_entry = Price.query.get_or_404(id)
    db.session.delete(price_entry)
    db.session.commit()
    return redirect(url_for('prices'))

@app.route('/update_prices_from_google')
@admin_required
def update_prices_from_google():
    stocks = Stock.query.all()
    today = datetime.date.today().isoformat()

    for stock in stocks:
        try:
            ticker = yf.Ticker(stock.tickersymbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest_price = round(hist['Close'].iloc[-1], 2)
            else:
                latest_price = 0.0 # Default if no data found

            # Check if a price for today already exists for this stock
            price_entry = Price.query.filter_by(tickersymbol=stock.tickersymbol, date=today).first()
            if price_entry:
                price_entry.price = latest_price
            else:
                new_price = Price(tickersymbol=stock.tickersymbol, date=today, price=latest_price)
                db.session.add(new_price)
        except Exception as e:
            # Optionally, add a placeholder price or skip this stock
            pass # Continue to next stock even if one fails
    
    db.session.commit()
    return redirect(url_for('prices'))

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        tickersymbol = request.form['tickersymbol']
        operation = request.form['operation']
        quantity = request.form['quantity']
        date = request.form['date']
        price = request.form['price']
        market = request.form.get('market', 'us_market') # Default to us_market if not provided
        currency = request.form.get('currency', 'USD') # Default to USD

        stock = Stock.query.filter_by(tickersymbol= tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        if operation == 'Sell':
            available_quantity = get_current_stock_quantity(tickersymbol, date, session['user_id'])
            if int(quantity) > available_quantity:
                return jsonify({'error': 'Insufficient quantity to sell.'}), 400

        new_transaction = Transaction(tickersymbol=tickersymbol, operation=operation, quantity=int(quantity), date=date, price=float(price), market=market, currency=currency, user_id=session['user_id'])
        db.session.add(new_transaction)
        db.session.commit()

        # Update Price table with transaction price
        price_entry = Price.query.filter_by(tickersymbol=tickersymbol, date=date).first()
        if price_entry:
            price_entry.price = float(price)
        else:
            new_price_entry = Price(tickersymbol=tickersymbol, date=date, price=float(price))
            db.session.add(new_price_entry)
        
        # Fetch and add the latest price
        try:
            today = datetime.date.today().isoformat()
            ticker = yf.Ticker(tickersymbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest_price = round(hist['Close'].iloc[-1], 2)
                
                # Check if a price for today already exists
                latest_price_entry = Price.query.filter_by(tickersymbol=tickersymbol, date=today).first()
                if latest_price_entry:
                    latest_price_entry.price = latest_price
                else:
                    new_latest_price_entry = Price(tickersymbol=tickersymbol, date=today, price=latest_price)
                    db.session.add(new_latest_price_entry)
        except Exception as e:
            print(f"Error fetching latest price for {tickersymbol}: {e}")
            # Decide if you want to flash a message to the user
            
        db.session.commit() # Commit all price changes

        update_portfolio(tickersymbol, session['user_id'])
        return jsonify({'success': True, 'redirect_url': url_for('index')})
    
    stocks = Stock.query.all()
    return render_template('add_transaction.html', stocks=stocks)

@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if request.method == 'POST':
        transaction.tickersymbol = request.form['tickersymbol']
        transaction.operation = request.form['operation']
        transaction.quantity = int(request.form['quantity'])
        transaction.date = request.form['date']
        transaction.price = float(request.form['price'])
        transaction.market = request.form.get('market', transaction.market)
        transaction.currency = request.form.get('currency', transaction.currency)

        stock = Stock.query.filter_by(tickersymbol=transaction.tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        if transaction.operation == 'Sell':
            available_quantity = get_current_stock_quantity(transaction.tickersymbol, transaction.date, session['user_id'], exclude_transaction_id=transaction.id)
            if transaction.quantity > available_quantity:
                return "Insufficient quantity to sell after considering other transactions.", 400 # Bad Request

        db.session.commit()

        # Update Price table with transaction price
        price_entry = Price.query.filter_by(tickersymbol=transaction.tickersymbol, date=transaction.date).first()
        if price_entry:
            price_entry.price = float(transaction.price)
        else:
            new_price_entry = Price(tickersymbol=transaction.tickersymbol, date=transaction.date, price=float(transaction.price))
            db.session.add(new_price_entry)

        # Fetch and add the latest price
        try:
            today = datetime.date.today().isoformat()
            ticker = yf.Ticker(transaction.tickersymbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                latest_price = round(hist['Close'].iloc[-1], 2)
                
                # Check if a price for today already exists
                latest_price_entry = Price.query.filter_by(tickersymbol=transaction.tickersymbol, date=today).first()
                if latest_price_entry:
                    latest_price_entry.price = latest_price
                else:
                    new_latest_price_entry = Price(tickersymbol=transaction.tickersymbol, date=today, price=latest_price)
                    db.session.add(new_latest_price_entry)
        except Exception as e:
            print(f"Error fetching latest price for {transaction.tickersymbol}: {e}")

        db.session.commit() # Commit all price changes

        update_portfolio(transaction.tickersymbol, session['user_id'])
        return redirect(url_for('transactions'))
    
    stocks = Stock.query.all()
    return render_template('edit_transaction.html', transaction=transaction, stocks=stocks)

@app.route('/delete_transaction/<int:id>')
@login_required
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    update_portfolio(transaction.tickersymbol, session['user_id'])
    return redirect(url_for('transactions'))

@app.route('/search_tickers')
@login_required
def search_tickers():
    query = request.args.get('q', '').upper()
    market = request.args.get('market', None)

    if query:
        stock_query = Stock.query
        if market:
            stock_query = stock_query.filter(Stock.market == market)

        # Search for ticker symbols or names that start with the query
        stocks = stock_query.filter(or_(Stock.tickersymbol.ilike(f'{query}%'), Stock.name.ilike(f'{query}%'))) \
                            .order_by(Stock.tickersymbol).limit(10).all()
        results = [{'tickersymbol': stock.tickersymbol, 'name': stock.name} for stock in stocks]
    else:
        results = []
    return jsonify(results)

@app.route('/get_historical_prices')
@login_required
def get_historical_prices():
    tickersymbol = request.args.get('tickersymbol', '').upper()
    date_str = request.args.get('date', '')

    if not tickersymbol or not date_str:
        return jsonify({'error': 'Ticker symbol and date are required.'}), 400

    try:
        # Convert date string to datetime object
        selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        # yfinance expects start and end date for history method
        start_date = selected_date
        end_date = selected_date + datetime.timedelta(days=1) # Fetch for a single day

        ticker = yf.Ticker(tickersymbol)
        hist = ticker.history(start=start_date, end=end_date)

        if not hist.empty:
            low_price = round(hist['Low'].iloc[0], 2)
            high_price = round(hist['High'].iloc[0], 2)
            return jsonify({'low': low_price, 'high': high_price})
        else:
            return jsonify({'low': None, 'high': None, 'message': 'No historical data found for this date.'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/transaction_history/<string:tickersymbol>')
@login_required
def transaction_history(tickersymbol):
    page = request.args.get('page', 1, type=int)
    per_page = 5 # Page size of 5 as requested

    pagination = Transaction.query.filter_by(
        user_id=session['user_id'],
        tickersymbol=tickersymbol
    ).order_by(Transaction.date.desc(), Transaction.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    transactions = pagination.items
    # Render a partial template to get the HTML for the transactions and pagination
    history_html = render_template('_transaction_history_content.html', transactions=transactions, pagination=pagination, tickersymbol=tickersymbol)
    return jsonify({'html': history_html})

@app.route('/lot_details/<string:tickersymbol>')
@login_required
def lot_details(tickersymbol):
    transactions = Transaction.query.filter_by(
        user_id=session['user_id'],
        tickersymbol=tickersymbol
    ).order_by(Transaction.date, Transaction.id).all()

    lots = []
    # Get the latest price for the stock once
    price_entry = Price.query.filter_by(tickersymbol=tickersymbol).order_by(Price.date.desc()).first()
    latest_price = price_entry.price if price_entry else 0.0
    stock = Stock.query.filter_by(tickersymbol=tickersymbol).first()
    currency = stock.currency if stock else 'USD'

    open_lots = [] # A queue to manage lots for selling

    for t in transactions:
        if t.operation == 'Buy':
            new_lot = {
                'id': f"lot-{t.date}-{t.id}", # Unique ID for the lot
                'purchased_quantity': t.quantity,
                'balance_quantity': t.quantity, # Initially, balance is the same as purchased
                'price': t.price,
                'date': t.date,
                'sales_from_lot': [] # To track sales from this specific lot
            }
            lots.append(new_lot)
            open_lots.append(new_lot)
        elif t.operation == 'Sell':
            sell_quantity = t.quantity
            sale_price = t.price
            sale_date = t.date # Capture the sale date
            while sell_quantity > 0 and open_lots:
                oldest_lot = open_lots[0]
                
                quantity_from_lot = min(sell_quantity, oldest_lot['balance_quantity'])

                purchase_price = oldest_lot['price']
                realized_gain = (sale_price - purchase_price) * quantity_from_lot

                # Calculate XIRR for this specific sale
                sale_xirr = None
                try:
                    sale_cash_flows = [-(quantity_from_lot * purchase_price), quantity_from_lot * sale_price]
                    sale_dates = [
                        datetime.datetime.strptime(oldest_lot['date'], '%Y-%m-%d').date(),
                        datetime.datetime.strptime(sale_date, '%Y-%m-%d').date()
                    ]
                    sale_xirr = calculate_xirr(sale_cash_flows, sale_dates)
                except Exception as e:
                    print(f"Error calculating XIRR for sale: {e}")

                oldest_lot['sales_from_lot'].append({
                    'sold_quantity': quantity_from_lot,
                    'sale_date': sale_date,
                    'purchase_price': purchase_price,
                    'sale_price': sale_price,
                    'realized_gain': realized_gain,
                    'xirr': sale_xirr
                })

                oldest_lot['balance_quantity'] -= quantity_from_lot
                sell_quantity -= quantity_from_lot

                if oldest_lot['balance_quantity'] == 0:
                    open_lots.pop(0) # Remove the fully sold lot from the open queue

    # Calculate cost basis and unrealized gain for the remaining lots
    for lot in lots:
        lot['cost_basis'] = lot['balance_quantity'] * lot['price']
        lot['current_value'] = lot['balance_quantity'] * latest_price
        lot['unrealized_gain'] = (lot['balance_quantity'] * latest_price) - lot['cost_basis']
        
        # Calculate XIRR for the remaining balance of the lot
        lot['balance_xirr'] = None
        if lot['balance_quantity'] > 0:
            try:
                balance_cash_flows = [-(lot['balance_quantity'] * lot['price']), lot['current_value']]
                balance_dates = [
                    datetime.datetime.strptime(lot['date'], '%Y-%m-%d').date(),
                    datetime.date.today()
                ]
                if balance_dates[0] < balance_dates[1]: # XIRR needs at least two different dates
                    lot['balance_xirr'] = calculate_xirr(balance_cash_flows, balance_dates)
            except Exception as e:
                print(f"Error calculating XIRR for lot balance: {e}")

    # Sort lots by purchase date in descending order as requested
    lots.sort(key=lambda x: x['date'], reverse=True)

    # Render a partial template to get the HTML for the lot details
    lots_html = render_template('_lot_details_content.html', lots=lots, tickersymbol=tickersymbol, latest_price=latest_price, currency=currency)
    return jsonify({'html': lots_html})

if __name__ == "__main__":
    app.run(debug=True, port=5000)