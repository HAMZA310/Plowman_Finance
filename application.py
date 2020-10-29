import os
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

# for getting current time.
from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

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
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL not found on config file")
    
# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not found on config file")

psql_heroku_URI = os.environ.get("DATABASE_URL")
db = SQL(psql_heroku_URI)

def create_transactions_table_in_DB():
    db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                user_id INTEGER NOT NULL,
                stock_symbol TEXT NOT NULL,
                stock_name TEXT NOT NULL,
                n_shares INTEGER NOT NULL,
                price_per_share NUMERIC NOT NULL,
                transaction_time TEXT NOT NULL UNIQUE
                )
                """
                )
create_transactions_table_in_DB()



@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Select by default will return list of dicts. Each dict is a transaction to be displayed.
    this_user_id = session['user_id']

    # transactions_rows is list of dicts. Where each dict is a row to dispaly i.e. symbol, .., total_shares,..
    transactions_rows = db.execute("SELECT stock_symbol, stock_name, SUM(n_shares), price_per_share FROM transactions WHERE user_id=? GROUP BY stock_symbol;", this_user_id)

    _all_stocks_worth = sum(map(lambda transaction: transaction['SUM(n_shares)'] \
                                                    * transaction['price_per_share'], transactions_rows))
    "TO DO: transactions_rows will have negative shares (after selling). Handle it before rendering such that only net shares are displayed"
    return render_template("index.html", transactions=transactions_rows, all_stocks_worth=_all_stocks_worth)

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

        # verify number of shares are passed and valid.
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
        total_price_for_n_shares_for_this_stock = _n_shares * this_stock_price_per_share # no need to store this in database.

        this_user_id = session["user_id"] # this is a primary key in this table and 'foreign key'
        rows_for_available_cash_for_this_user = db.execute("SELECT cash FROM users WHERE id=?", this_user_id)
        cash_this_user_currently_has = rows_for_available_cash_for_this_user[0]['cash']
        # Not enough cash left for this user to make this transaction.
        if total_price_for_n_shares_for_this_stock > cash_this_user_currently_has:
            return apology("You do not have sufficient balance to complete this transaction!", 403)

        # deduct transaction money from the users account.
        cash_left_after_transaction = cash_this_user_currently_has - total_price_for_n_shares_for_this_stock
        db.execute("UPDATE users SET cash=? WHERE id=?", cash_left_after_transaction, this_user_id)

        # Get current time in string- right format.
        time_now = now.strftime("%d/%m/%Y %H:%M:%S")    # dd/mm/YY H:M:S
        _transaction_time = time_now

        # Save this transaction information into databse. Each transaction is unique based on timestamps.
        db.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
            this_user_id,
            this_stock_symbol,
            this_stock_name,
            _n_shares,
            this_stock_price_per_share,
            _transaction_time
            )
        # redirect the user to home page.
        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    this_user_id = session['user_id']
    _history = db.execute("SELECT stock_symbol, n_shares, price_per_share, transaction_time FROM transactions WHERE user_id=?;", this_user_id)
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
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=_username)
        # Ensure username exists and password is correct
        username_exits = len(rows) > 0
        if username_exits:
            return apology("Username already exists", 403)

        # OK. Store this new user into database.
        else:
            # generate hash of the password
            password_hash = generate_password_hash(_password)
            # insert username and hash of this user into database.
            this_user_id = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                        _username, password_hash)
            # keep the user logged in when registered.
            session["user_id"] = this_user_id

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
    rows_with_tentative_symbols = db.execute("SELECT DISTINCT stock_symbol FROM transactions WHERE user_id=?", this_user_id)
    _tentative_symbols = list(map(lambda row: row['stock_symbol'], rows_with_tentative_symbols)) # stocks with 0, positive shares etc.

    # "For display", keep only those stock symbols for which the user has positive number (>0) of shares.
    _available_symbols = []
    for idx, symb in enumerate(_tentative_symbols):
        rows_for_net_shares_for_this_stock = db.execute("SELECT SUM(n_shares) FROM transactions WHERE stock_symbol=?", symb)
        net_shares_for_this_stock = rows_for_net_shares_for_this_stock[0]['SUM(n_shares)']
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

        rows_for_n_shares_bought = db.execute("SELECT SUM(n_shares) FROM transactions WHERE user_id=? AND stock_symbol=?",
                                                        this_user_id, this_stock_symbol)
        n_shares_bought = rows_for_n_shares_bought[0]['SUM(n_shares)'] # Number of shares the user has to sell.
        n_shares_will_be_left_on_selling = n_shares_bought - n_shares_to_be_sold

        if n_shares_will_be_left_on_selling < 0:
            return apology("You don't have enough shares to sell.", 403)

        this_stock_quote = lookup(this_stock_symbol) # a dict with keys [name, price, symbol]
        this_stock_name = this_stock_quote['name']
        this_stock_price_per_share = this_stock_quote['price']

        # money earned by selling those shares at current price.
        money_earned = n_shares_to_be_sold * this_stock_price_per_share
        rows_for_cash_already_in_account = db.execute("SELECT cash FROM users WHERE id=?", this_user_id)
        cash_already_in_account = rows_for_cash_already_in_account[0]['cash']
        new_cash_after_selling_shares = cash_already_in_account + money_earned
        db.execute("UPDATE users SET cash=? WHERE id=?", new_cash_after_selling_shares, this_user_id)

        "Update transactions table"
        # Get current time in string- right format.
        time_now = now.strftime("%d/%m/%Y %H:%M:%S")    # dd/mm/YY H:M:S
        _transaction_time = time_now
        db.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
            this_user_id,
            this_stock_symbol,
            this_stock_name,
            -n_shares_to_be_sold, # negative sign signifies 'sold'.
            this_stock_price_per_share,
            _transaction_time
            )
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
