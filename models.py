from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<User {self.username}>'

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tickersymbol = db.Column(db.String(20), nullable=False, unique=True)
    exchange = db.Column(db.String(50), nullable=False, default='NYSE')
    transactions = db.relationship('Transaction', backref='stock', lazy=True)

    def __repr__(self):
        return f'<Stock {self.tickersymbol}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), nullable=False)
    operation = db.Column(db.String(4), nullable=False, default='Buy')
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    user = db.relationship('User', backref='transactions', lazy=True)

    def __repr__(self):
        return f'<Transaction {self.id}>'

class Portfolio(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    value = db.Column(db.Float, nullable=False, default=0.0)
    user = db.relationship('User', backref='portfolios', lazy=True)

    def __repr__(self):
        return f'<Portfolio {self.tickersymbol}>'

class Price(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Price {self.tickersymbol} on {self.date}>'