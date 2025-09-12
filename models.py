from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), nullable=False)
    operation = db.Column(db.String(4), nullable=False, default='Buy')
    quantity = db.Column(db.Integer, nullable=False)
    date = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Transaction {self.id}>'

class Portfolio(db.Model):
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    value = db.Column(db.Float, nullable=False, default=0.0)

    def __repr__(self):
        return f'<Portfolio {self.tickersymbol}>'

class Price(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tickersymbol = db.Column(db.String(20), db.ForeignKey('stock.tickersymbol'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f'<Price {self.tickersymbol} on {self.date}>'
