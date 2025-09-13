from flask import Flask, render_template, request, redirect, url_for, jsonify
from models import db, Stock, Transaction, Portfolio, Price
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

app = Flask(__name__)

# Configure the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stocks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Sample list of high-volume tickers (for demonstration)
# In a real application, this would be fetched dynamically from a reliable source.
SAMPLE_HIGH_VOLUME_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "PG", "XOM", "HD", "UNH", "MA", "VZ", "DIS", "ADBE",
    "NFLX", "PYPL", "INTC", "CMCSA", "PEP", "KO", "PFE", "MRK", "ABT", "NKE",
    "BAC", "C", "WFC", "GS", "MS", "AMGN", "GILD", "BMY", "CVS", "MDLZ",
    "SBUX", "GM", "ORCL"
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
                exchange = ticker_info.get('exchange', 'N/A') # Default to N/A if not found

                new_stock = Stock(name=stock_name, tickersymbol=ticker_symbol, exchange=exchange)
                db.session.add(new_stock)
                print(f"Added new stock: {ticker_symbol} - {stock_name}")
            except Exception as e:
                print(f"Could not add stock {ticker_symbol}: {e}")
    db.session.commit()
    print("Initial stock population complete.")

# Create the database tables
with app.app_context():
    db.create_all()
    populate_initial_stocks() # Call the function here

@app.route('/')
def index():
    portfolio_items = Portfolio.query.all()
    portfolio_data = []
    total_portfolio_value = 0.0

    for item in portfolio_items:
        # Get latest price from Price table for display in portfolio
        price_entry = Price.query.filter_by(tickersymbol=item.tickersymbol).order_by(Price.date.desc()).first()
        latest_price = price_entry.price if price_entry else 0.0
        item_value = item.quantity * latest_price
        total_portfolio_value += item_value

        # Prepare data for XIRR calculation
        cash_flows = []
        dates = []

        # Get all transactions for the current stock
        transactions = Transaction.query.filter_by(tickersymbol=item.tickersymbol).order_by(Transaction.date).all()

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

        xirr_value = None
        if len(cash_flows) > 1: # XIRR requires at least two cash flows
            try:
                xirr_value = calculate_xirr(cash_flows, dates)
            except Exception as e:
                print(f"Error calculating XIRR for {item.tickersymbol}: {e}")

        portfolio_data.append({
            'tickersymbol': item.tickersymbol,
            'quantity': item.quantity,
            'latest_price': latest_price,
            'value': item_value,
            'percentage': 0.0, # Placeholder, will be calculated later
            'xirr': xirr_value
        })
    
    # Calculate percentage of portfolio for each item
    if total_portfolio_value > 0:
        for item in portfolio_data:
            item['percentage'] = (item['value'] / total_portfolio_value) * 100

    return render_template('index.html', portfolio_data=portfolio_data, total_portfolio_value=total_portfolio_value)

@app.route('/add', methods=['GET', 'POST'])
def add_stock():
    if request.method == 'POST':
        name = request.form['name']
        tickersymbol = request.form['tickersymbol'].upper() # Convert to uppercase
        exchange = request.form['exchange']

        # Validate ticker symbol using yfinance
        try:
            ticker = yf.Ticker(tickersymbol)
            info = ticker.info # Attempt to get info to validate existence
            if 'regularMarketPrice' not in info: # A common key that indicates valid stock data
                return f"Ticker symbol '{tickersymbol}' not found or no market data available.", 400
        except Exception as e:
            return f"Error validating ticker symbol '{tickersymbol}': {e}", 400

        if not exchange:
            exchange = 'NYSE'

        new_stock = Stock(name=name, tickersymbol=tickersymbol, exchange=exchange)
        db.session.add(new_stock)
        db.session.commit()
        return redirect(url_for('stocks_list')) # Redirect to stocks_list after adding
    return redirect(url_for('stocks_list')) # Redirect GET requests to the stocks list

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_stock(id):
    stock = Stock.query.get_or_404(id)
    if request.method == 'POST':
        stock.name = request.form['name']
        stock.tickersymbol = request.form['tickersymbol'].upper() # Convert to uppercase
        stock.exchange = request.form['exchange']

        # Validate ticker symbol using yfinance
        try:
            ticker = yf.Ticker(stock.tickersymbol)
            info = ticker.info
            if 'regularMarketPrice' not in info:
                return f"Ticker symbol '{stock.tickersymbol}' not found or no market data available.", 400
        except Exception as e:
            return f"Error validating ticker symbol '{stock.tickersymbol}': {e}", 400

        if not stock.exchange:
            stock.exchange = 'NYSE'

        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit_stock.html', stock=stock)

@app.route('/delete/<int:id>')
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
def stocks_list():
    stocks = Stock.query.all()
    return render_template('stocks.html', stocks=stocks)

def get_current_stock_quantity(tickersymbol, transaction_date, exclude_transaction_id=None):
    buy_query = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Buy',
        Transaction.date <= transaction_date # Filter by date
    )
    sell_query = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Sell',
        Transaction.date <= transaction_date # Filter by date
    )

    if exclude_transaction_id:
        buy_query = buy_query.filter(Transaction.id != exclude_transaction_id)
        sell_query = sell_query.filter(Transaction.id != exclude_transaction_id)

    buy_quantity = buy_query.scalar() or 0
    sell_quantity = sell_query.scalar() or 0

    return buy_quantity - sell_quantity

def update_portfolio(tickersymbol):
    # Calculate total quantity
    buy_quantity = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Buy'
    ).scalar() or 0

    sell_quantity = db.session.query(db.func.sum(Transaction.quantity)).filter(
        Transaction.tickersymbol == tickersymbol,
        Transaction.operation == 'Sell'
    ).scalar() or 0

    total_quantity = buy_quantity - sell_quantity

    # Get latest price from Price table
    # Order by date descending to get the most recent price
    price_entry = Price.query.filter_by(tickersymbol=tickersymbol).order_by(Price.date.desc()).first()
    latest_price = price_entry.price if price_entry else 0.0

    # Calculate value
    current_value = total_quantity * latest_price

    # Update or create Portfolio entry
    portfolio_entry = Portfolio.query.filter_by(tickersymbol=tickersymbol).first()
    if portfolio_entry:
        if total_quantity == 0:
            db.session.delete(portfolio_entry)
        else:
            portfolio_entry.quantity = total_quantity
            portfolio_entry.value = current_value
    else:
        if total_quantity > 0: # Only add if there's a positive quantity
            new_portfolio_entry = Portfolio(tickersymbol=tickersymbol, quantity=total_quantity, value=current_value)
            db.session.add(new_portfolio_entry)
    db.session.commit()

@app.route('/transactions')
def transactions():
    transactions = Transaction.query.all()
    stocks = Stock.query.order_by(Stock.tickersymbol).all() # Fetch all stocks, ordered alphabetically
    # Determine the latest ticker symbol for defaulting. Assuming latest means last alphabetically.
    latest_tickersymbol = stocks[-1].tickersymbol if stocks else ''
    return render_template('transactions.html', transactions=transactions, stocks=stocks, latest_tickersymbol=latest_tickersymbol)

@app.route('/prices')
def prices():
    prices = Price.query.all()
    stocks = Stock.query.all() # Fetch all stocks for the modal dropdown
    return render_template('prices.html', prices=prices, stocks=stocks)

@app.route('/add_price', methods=['GET', 'POST'])
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
def delete_price(id):
    price_entry = Price.query.get_or_404(id)
    db.session.delete(price_entry)
    db.session.commit()
    return redirect(url_for('prices'))

@app.route('/update_prices_from_google')
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
def add_transaction():
    if request.method == 'POST':
        tickersymbol = request.form['tickersymbol']
        operation = request.form['operation']
        quantity = request.form['quantity']
        date = request.form['date']
        price = request.form['price']

        stock = Stock.query.filter_by(tickersymbol=tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        if operation == 'Sell':
            available_quantity = get_current_stock_quantity(tickersymbol, date)
            if int(quantity) > available_quantity:
                return "Insufficient quantity to sell.", 400 # Bad Request

        new_transaction = Transaction(tickersymbol=tickersymbol, operation=operation, quantity=int(quantity), date=date, price=float(price))
        db.session.add(new_transaction)
        db.session.commit()

        # Update Price table based on transaction
        price_entry = Price.query.filter_by(tickersymbol=tickersymbol, date=date).first()
        if price_entry:
            price_entry.price = float(price)
        else:
            new_price_entry = Price(tickersymbol=tickersymbol, date=date, price=float(price))
            db.session.add(new_price_entry)
        db.session.commit() # Commit the price change

        update_portfolio(tickersymbol)
        return redirect(url_for('transactions'))
    
    stocks = Stock.query.all()
    return render_template('add_transaction.html', stocks=stocks)

@app.route('/edit_transaction/<int:id>', methods=['GET', 'POST'])
def edit_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    if request.method == 'POST':
        transaction.tickersymbol = request.form['tickersymbol']
        transaction.operation = request.form['operation']
        transaction.quantity = int(request.form['quantity'])
        transaction.date = request.form['date']
        transaction.price = float(request.form['price'])

        stock = Stock.query.filter_by(tickersymbol=transaction.tickersymbol).first()
        if not stock:
            return "Stock not found", 404

        if transaction.operation == 'Sell':
            available_quantity = get_current_stock_quantity(transaction.tickersymbol, transaction.date, exclude_transaction_id=transaction.id)
            if transaction.quantity > available_quantity:
                return "Insufficient quantity to sell after considering other transactions.", 400 # Bad Request

        db.session.commit()

        # Update Price table based on transaction
        price_entry = Price.query.filter_by(tickersymbol=transaction.tickersymbol, date=transaction.date).first()
        if price_entry:
            price_entry.price = float(transaction.price)
        else:
            new_price_entry = Price(tickersymbol=transaction.tickersymbol, date=transaction.date, price=float(transaction.price))
            db.session.add(new_price_entry)
        db.session.commit() # Commit the price change

        update_portfolio(transaction.tickersymbol)
        return redirect(url_for('transactions'))
    
    stocks = Stock.query.all()
    return render_template('edit_transaction.html', transaction=transaction, stocks=stocks)

@app.route('/delete_transaction/<int:id>')
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    update_portfolio(transaction.tickersymbol)
    return redirect(url_for('transactions'))

@app.route('/search_tickers')
def search_tickers():
    query = request.args.get('q', '').upper()
    if query:
        # Search for ticker symbols or names that start with the query
        stocks = Stock.query.filter(or_(
            Stock.tickersymbol.ilike(f'{query}%'),
            Stock.name.ilike(f'{query}%')
        )).order_by(Stock.tickersymbol).limit(10).all()
        results = [{'tickersymbol': stock.tickersymbol, 'name': stock.name} for stock in stocks]
    else:
        results = []
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
