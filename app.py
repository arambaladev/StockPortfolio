from flask import Flask, render_template, request, redirect, url_for
from models import db, Stock, Transaction, Portfolio, Price
import os
import random
import datetime
import yfinance as yf

app = Flask(__name__)

# Configure the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stocks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create the database tables
with app.app_context():
    db.create_all()

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
        portfolio_data.append({
            'tickersymbol': item.tickersymbol,
            'quantity': item.quantity,
            'latest_price': latest_price,
            'value': item_value
        })
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
        return redirect(url_for('index'))
    return render_template('add_stock.html')

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
    return render_template('transactions.html', transactions=transactions)

@app.route('/prices')
def prices():
    prices = Price.query.all()
    return render_template('prices.html', prices=prices)

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
    
    stocks = Stock.query.all() # To populate dropdown
    return render_template('add_price.html', stocks=stocks)

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

if __name__ == '__main__':
    app.run(debug=True)
