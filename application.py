import os
import csv
import decimal # for putting in right formats.

from flask import Flask, flash, jsonify, redirect, render_template, request, session
from sqlalchemy import distinct, func, and_
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd
from datetime import datetime # for getting current time.
from models import * # tables defined for DB

# Make sure Databse URL key is set
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL not found on config file")

# Configure application
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

db.init_app(app) # sqlalchemy db init.  

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not found on config file")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks
    Notes:
    IN Group By below, technically, grouping by symbol is equivalent 
    to grouping by symbol, name, price_per_share collectively. PSQL (not mySQL)
    forces you to put all three in group by clause or in an aggregate function (SUM etc).
    PSQL doesn't know that exactly one name is associated with one symbol, for example.
    """

    # Select by default will return list of dicts. Each dict is a transaction to be displayed.
    this_user_id = session['user_id']
    transactions = Transaction.query.with_entities(
        Transaction.stock_symbol,
        Transaction.stock_name,
        func.sum(Transaction.n_shares).label('total_shares_for_this_symbol'),
        Transaction.price_per_share
        ).filter_by(id=this_user_id).group_by(Transaction.stock_symbol,
        Transaction.stock_name, Transaction.price_per_share).all()
  
    _all_stocks_worth = sum(map(lambda transaction: transaction.total_shares_for_this_symbol \
                                                    * transaction.price_per_share, transactions))
    return render_template("index.html", transactions=transactions, all_stocks_worth=_all_stocks_worth)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # get current time
        now = datetime.now()
        # verify a symbol is passed
        this_stock_symbol = request.form.get("symbol")
        if not this_stock_symbol:
            return apology("Must provide symbol", 403)

        # verify the number of shares is passed and valid.
        _n_shares = int(request.form.get("shares"))
        if not _n_shares:
            return apology("Must provide shares", 403)
        if _n_shares < 1:
            return apology("Number of shares must be a positive integer", 403)

        this_stock_quote = lookup(this_stock_symbol) # a dict with keys [name, price, symbol]
        if this_stock_quote:
            this_stock_name = this_stock_quote['name']
            this_stock_price_per_share = this_stock_quote['price']
        else:
            return apology("Symbol Error", 403)
        total_price_for_n_shares_for_this_stock = _n_shares \
                                            * this_stock_price_per_share # no need to store this in database.

        this_user_id = session["user_id"] # this is a primary key in this table and 'foreign key'
        this_user = User.query.filter_by(id=this_user_id).one_or_none()
   
        cash_this_user_currently_has = this_user.cash
        if not cash_this_user_currently_has:
            raise Exception("Finding cash_this_user_currently_has is problematic")
        # Not enough cash left for this user to make this transaction.
        if total_price_for_n_shares_for_this_stock > cash_this_user_currently_has:
            return apology("You do not have sufficient balance to complete this transaction!", 403)

        # deduct transaction money from the users account.
        total_price_for_n_shares_for_this_stock = decimal.Decimal(
            total_price_for_n_shares_for_this_stock) # decimal format
        cash_left_after_transaction = cash_this_user_currently_has \
                                    - total_price_for_n_shares_for_this_stock
        # Update cash in DB
        this_user.cash = cash_left_after_transaction
        db.session.add(this_user)

        # Get current time in string- right format.
        time_now = now.strftime("%d/%m/%Y %H:%M:%S")    # dd/mm/YY H:M:S
        _transaction_time = time_now
        # Save this transaction information into databse. Each transaction is unique based on timestamps.
        new_transaction = Transaction(
            id=this_user_id,
            stock_symbol=this_stock_symbol,
            stock_name=this_stock_name,
            n_shares=_n_shares,
            price_per_share=this_stock_price_per_share,
            transaction_time=_transaction_time
            )
        db.session.add(new_transaction)
        db.session.commit() # commit all changes (adds) at once.
        # redirect the user to home page.
        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    this_user_id = session['user_id']
    _history = Transaction.query.with_entities(
        Transaction.stock_symbol,
        Transaction.n_shares,
        Transaction.price_per_share,
        Transaction.transaction_time,
    ).filter_by(id=this_user_id).all()

    return render_template("history.html", history=_history)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()
    # User reached route via POST (as by submitting a form via POST)

    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        this_user_data = User.query.filter_by(username=request.form.get("username")).one_or_none()
      
        # Ensure username exists and password is correct
        if not this_user_data or not check_password_hash(this_user_data.hash, request.form.get("password")):
            return apology("invalid username and/or password", 403)
  
        # Remember which user has logged in
        session["user_id"] = this_user_data.id

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/")

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        _symbol = request.form.get('symbol')
        if not _symbol:
            return apology("Must provide symbol", 403)
        else:
            _quote = lookup(_symbol) # a dict with keys [name, price, symbol]
            _name = _quote['name']
            _price = usd(_quote['price']) # in proper usd format.
            return render_template("quoted.html", name=_name, symbol=_symbol, price=_price)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        _username = request.form.get("username")
        if not _username:
            return apology("Must provide username", 403)

        # Ensure password was submitted
        _password = request.form.get("password")
        if not _password:
            return apology("Must provide password", 403)

        _password_confirmation = request.form.get("confirmation")
        if not _password_confirmation:
            return apology("Must provide confirmation password", 403)

        if _password != _password_confirmation:
            return apology("Passwords do not match", 403)

        # Check if username already exists. Query database for username
        username_exits = User.query.filter_by(username=request.form.get("username")).one_or_none()
        if username_exits:
            return apology("Username already exists", 403)
        # OK. Store this new user into database.
        else:
            # generate hash of the password
            password_hash = generate_password_hash(_password)
            # insert username and hash of this user into database.
            new_user = User(username=_username, hash=password_hash)
            db.session.add(new_user)
            db.session.commit()
            # keep the user logged in when registered.
            session["user_id"] = new_user.id
            # Redirect user to home page
            return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    this_user_id = session['user_id']
    _tentative_symbols_unclean = Transaction.query.with_entities(distinct(Transaction.stock_symbol))\
        .filter_by(id=this_user_id).all()
    _tentative_symbols = list(map(lambda elm: elm[0], _tentative_symbols_unclean)) # remove commas etc
    # "For display", keep only those stock symbols for which the user has positive number (>0) of shares.
    _available_symbols = []
    for idx, symb in enumerate(_tentative_symbols):
        net_shares_for_this_stock = Transaction.query.with_entities(
            func.sum(Transaction.n_shares)
            ).filter_by(stock_symbol=symb).scalar()
        if net_shares_for_this_stock > 0:
            this_symbol = _tentative_symbols[idx]
            _available_symbols.append(this_symbol)

    if request.method == "POST":
        # Get current time.
        now = datetime.now()
        this_stock_symbol = request.form.get('symbol')
        if not this_stock_symbol:
            return apology("Must provide Symbol", 403)

        n_shares_to_be_sold = int(request.form.get("shares"))
        if not n_shares_to_be_sold:
            return apology("Must provide Shares", 403)

        if n_shares_to_be_sold < 1:
            return apology("Shares must be a postive integer.", 403)

        # Get number of shares of this stock symbol, this user has bought so far.
        n_shares_bought = Transaction.query.with_entities(func.sum(Transaction.n_shares)).filter(
            and_(
                Transaction.id == this_user_id), (Transaction.stock_symbol == this_stock_symbol)
            ).scalar()
      
        n_shares_will_be_left_on_selling = n_shares_bought - n_shares_to_be_sold

        if n_shares_will_be_left_on_selling < 0:
            return apology("You don't have enough shares to sell.", 403)

        this_stock_quote = lookup(this_stock_symbol) # a dict with keys [name, price, symbol]
        this_stock_name = this_stock_quote['name']
        this_stock_price_per_share = this_stock_quote['price']

        # money earned by selling those shares at current price.
        money_earned = n_shares_to_be_sold * this_stock_price_per_share
        # This user object- as per DB.
        this_user = User.query.filter_by(id=this_user_id).one_or_none()
        cash_already_in_account = this_user.cash

        money_earned = decimal.Decimal(money_earned) # put in right format for addition next.
        new_cash_after_selling_shares = cash_already_in_account + money_earned
        this_user.cash = new_cash_after_selling_shares # update cash of the user
        db.session.add(this_user) # Add now. Commit all changes once later.

        # Get current time in string- right format.
        time_now = now.strftime("%d/%m/%Y %H:%M:%S")    # dd/mm/YY H:M:S
        _transaction_time = time_now
        # Save this new transaction in DB.
        with_neg_sign_n_shares_to_be_sold = -n_shares_to_be_sold
        new_transaction = Transaction(
            id=this_user_id,
            stock_symbol=this_stock_symbol,
            stock_name=this_stock_name,
            n_shares=with_neg_sign_n_shares_to_be_sold,
            price_per_share=this_stock_price_per_share,
            transaction_time=_transaction_time
            )
        db.session.add(new_transaction)
        db.session.commit()
        return redirect("/")
    else:
        return render_template("sell.html", symbols=_available_symbols)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)

# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
