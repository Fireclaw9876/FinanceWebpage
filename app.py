import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timezone

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Create Order table
db.execute("CREATE TABLE IF NOT EXISTS stockOrders (id INTEGER, user_id NUMERIC NOT NULL, transaction_type TEXT NOT NULL, timestamp TEXT, symbol TEXT NOT NULL, shares NUMERIC NOT NULL, price NUMERIC NOT NULL, PRIMARY KEY(id), FOREIGN KEY(user_id) REFERENCES users(id))")
db.execute("CREATE INDEX IF NOT EXISTS stockOrders_by_user_id_index ON stockOrders(user_id)")

# Create History Table
db.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER, user_id NUMERIC NOT NULL, transaction_type TEXT NOT NULL, timestamp TEXT, symbol TEXT NOT NULL, shares NUMERIC NOT NULL, price NUMERIC NOT NULL, PRIMARY KEY(id), FOREIGN KEY(user_id) REFERENCES users(id))")
db.execute("CREATE INDEX IF NOT EXISTS history_by_user_id_index ON history(user_id)")


# Filter your Inputs
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    query = db.execute("SELECT symbol, price, SUM(shares) as totalShares FROM stockOrders WHERE user_id = ? GROUP BY symbol", user_id)
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)

    # get cash value float
    cash = cash[0]['cash']

    # Calculate Total
    for q in query:
        result = lookup(q["symbol"])
        q["price"] = result["price"]
        q["purchase"] = q["totalShares"] * q["price"]

        # convert total to usd format
        q["price"] = usd(q["price"])
        q["purchase"] = usd(q["purchase"])

    return render_template("index.html", query=query, cash=usd(cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)

        # Validate symbol and shares
        if not symbol:
            return apology("Missing symbol", 400)  # Return an error message if symbol is missing
        if not shares:
            return apology("Missing shares", 400)  # Return an error message if shares is missing
        if not shares.isdigit():
            return apology("Shares must be a positive integer", 400)  # Return an error message if shares is not a positive integer

        if quote == None:
            return apology("Invalid Stock Symbol", 400)

        shares = int(shares)  # Convert shares to an integer value

        if shares <= 0:
            return apology("Shares must be a positive integer", 400)  # Return an error message if shares is non-positive

        timeNow = currentTime()

        # Update Share in Order Table
        db.execute("INSERT INTO stockOrders (user_id, symbol, shares, price, transaction_type , timestamp) VALUES (:id, :symbol, :shares, :price, :transaction, :timestamp)",
                   id=session["user_id"], symbol=symbol, shares=request.form.get("shares"), price=quote['price'], transaction='BUY', timestamp=timeNow)

        # Update Share in History Table
        db.execute("INSERT INTO history (user_id, symbol, shares, price, transaction_type , timestamp) VALUES (:id, :symbol, :shares, :price, :transaction, :timestamp)",
                   id=session["user_id"], symbol=symbol, shares=request.form.get("shares"), price=quote['price'], transaction="BUY", timestamp=timeNow)

        # Calculate Purchase Price
        purchase = quote['price'] * int(shares)

        # How much cash the user currently has
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        userCash = cash[0]["cash"]
        boughtCash = userCash - purchase

        if boughtCash < 0:
            return apology("cannot afford the number of shares at the current price", 400)

        # Update Cash Balance
        db.execute("UPDATE users SET cash=:boughtCash WHERE id=:id", boughtCash=boughtCash, id=session["user_id"])

        # Redirect user to home page
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id = session["user_id"]

    query = db.execute("SELECT * FROM history WHERE user_id = ?", user_id)

    return render_template("history.html", query=query)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

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

        # Look up the stock and then display the results
        symbol = request.form.get("symbol")

        if not symbol:
            return apology("missing symbol", 400)

        quote = lookup(symbol)

        if quote == None:
            return apology("stock symbol doesn't exist", 400)

        # Change quote price to USD
        quote["price"] = usd(quote["price"])

        # Render Quoted Page
        return render_template("quoted.html", quote=quote)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached to register via Post
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide confirmation", 400)

        # Ensure password and confirmation work
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmation do not match", 400)

        # Register database for username
        # Get the username and password from the form
        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        # Query database to ensure username isn't already taken
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=username)
        if len(rows) != 0:
            return apology("username is already taken", 400)

        # insert username and hash into database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                   username=username, hash=hash)

        # Redirect user to home page
        return redirect("/")
    # Requested page VIA get
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        # Require that a user input a stock’s symbol, implemented as a text field whose name is symbol.
        symbol = request.form.get("symbol")
        # Require that a user input a number of shares, implemented as a text field whose name is shares.
        shares = request.form.get("shares")
        quote = lookup(symbol)

        if quote == None:
            return apology("Invalid Stock Symbol", 400)

        # Validate symbol and shares
        if not symbol:
            return apology("Missing symbol", 400)

        if not shares:
            return apology("Missing shares", 400)

        # Return an error message if shares is not a positive integer
        if not shares.isdigit():
            return apology("Shares must be a positive integer", 400)

        shares = int(shares)  # Convert shares to an integer value

        if shares <= 0:
            return apology("Shares must be a positive integer", 400)

        # Save in a new form
        rows = db.execute("SELECT * FROM stockOrders WHERE user_id = :id AND symbol = :symbol",
                          id=session["user_id"], symbol=symbol)

        # Finds Amount for Old Shares
        if (len(rows) == 0):
            return apology("haven't bought anything from this company yet", 400)

        oldshares = rows[0]['shares']

        # Update New Shares
        newshares = oldshares - shares

        timeNow = currentTime()

        # Check if enough Shares
        if newshares < 0:
            return apology("shares sold exceeds shares owned", 400)
        elif newshares > 0:
            db.execute("UPDATE stockOrders SET shares = :newshares, transaction_type = :transaction, timestamp = :timestamp WHERE user_id = :id AND symbol = :symbol",
                       newshares=newshares, id=session["user_id"], symbol=symbol, transaction="SELL", timestamp=timeNow)

            # Update Share in History Table
            db.execute("INSERT INTO history (user_id, symbol, shares, price, transaction_type , timestamp) VALUES (:id, :symbol, :shares, :price, :transaction, :timestamp)",
                       id=session["user_id"], symbol=symbol, shares=request.form.get("shares"), price=quote['price'], transaction="SELL", timestamp=timeNow)

        # otherwise delete stock row because no shares remain
        else:
            db.execute("DELETE FROM stockOrders WHERE symbol = :symbol AND user_id = :id",
                       symbol=symbol, id=session["user_id"])

        # get current value of stock price times shares
        sold = quote['price'] * shares

        # Return back the value of sold stocks to previous cash balance
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session['user_id'])
        cash = cash[0]['cash']
        cash = cash + sold

        # Update new Cash Balance
        db.execute("UPDATE users SET cash = :cash WHERE id = :id",
                   cash=cash, id=session["user_id"])

        # Redirect user to home page
        return redirect("/")
    else:
        # Select all the different stock as options
        stockNames = db.execute("SELECT DISTINCT symbol FROM stockOrders")

        return render_template("sell.html", stockNames=stockNames)


def currentTime():
    # Help from Stack Overflow
    now_utc = datetime.now(timezone.utc)
    return str(now_utc.date()) + ' @time ' + now_utc.time().strftime("%H:%M:%S")