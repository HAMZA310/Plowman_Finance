from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# There is no relation defined between these two tables.
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True) # autoincrement needed, and is true by default
    username = db.Column(db.String, nullable=False)
    hash = db.Column(db.String, nullable=False)
    cash = db.Column(db.Numeric, nullable=False, default=10000)

class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer) # id will be provided eachtime- no autoincrement needed.
    stock_symbol = db.Column(db.String, nullable=False)
    stock_name = db.Column(db.String, nullable=False)
    n_shares = db.Column(db.Integer, nullable=False)
    price_per_share = db.Column(db.Numeric, nullable=False)
    transaction_time = db.Column(db.String, nullable=False, primary_key=True)

