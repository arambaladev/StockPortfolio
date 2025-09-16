from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Sequence

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, Sequence('user_id_seq'), primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<User {self.username}>'

class Stock(db.Model):
    id = db.Column(db.Integer, Sequence('stock_id_seq'), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tickersymbol = db.Column(db.String(20), nullable=False, unique=True)
    exchange = db.Column(db.String(50), nullable=False, default='NMS')
    sector = db.Column(db.String(100), nullable=True) # Added sector column
    market = db.Column(db.String(50), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    address = db.Column(db.String(500), nullable=True)
    transactions = db.relationship('Transaction', backref='stock', lazy=True)

    def __repr__(self):
        return f'<Stock {self.tickersymbol}>'

class Transaction(db.Model):
    id = db.Column(db.Integer, Sequence('transaction_id_seq'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), nullable=False)
    operation = db.Column(db.String(4), nullable=False, default='Buy')
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    inrprice = db.Column(db.Float, nullable=True)
    usdprice = db.Column(db.Float, nullable=True)
    market = db.Column(db.String(50), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    user = db.relationship('User', backref='transactions', lazy=True)

    def __repr__(self):
        return f'<Transaction {self.id}>'

class Portfolio(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    value = db.Column(db.Float, nullable=False, default=0.0)
    user = db.relationship('User', backref='portfolios', lazy=True)

    def __repr__(self):
        return f'<Portfolio {self.tickersymbol}>'