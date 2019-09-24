import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import *
from datetime import datetime
import math

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

# Custom filter, to make it easier to format values as us$
app.jinja_env.filters["usd"] = usd

# Configure session to use local filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    userId = str(session["user_id"])
    print("\n\nLOGGED IN at index\tSESSION['user_id'] is", userId, type(userId))

    # prepping headerRow for display
    headerRow = ["SYMBOL", "NAME", "# SHARES", "CURRENT SHARE PRICE", "TOTAL VALUE"]

    # prepping user's portfolio values & live quotes for display
        # I decided against individual SELECT db queries, it's more elegant to assemble evyerthing here rather than jinja thru it later in html
    portfolio = db.execute("SELECT * FROM :userIdPortfolio", userIdPortfolio = userId+"Portfolio")
    symbols = []
    names = []
    qtyShares = []
    currSharePrices = []
    totalValues = []
    allLists = [symbols, names, qtyShares, currSharePrices, totalValues]
    allStocks = []
    grandTotal = 0
    for row in portfolio:
        symbols.append(row['symbol'])
        names.append(row['name'])
        qtyShares.append(row['qtyShares'])
        liveQuote = lookup(row['symbol'])['price']
        value = liveQuote*row['qtyShares']
        grandTotal += value
        # change values into dollar format
        liveQuote = '${:,.2f}'.format(liveQuote)
        value = '${:,.2f}'.format(value)
        currSharePrices.append(liveQuote)
        totalValues.append(value)
    # compiling table data to facilitate display
    for i in range(len(symbols)):
        tableRow = []
        for j in range(len(allLists)):
            tableRow.append(allLists[j][i])
        print("\ttableRow is", tableRow)
        allStocks.append(tableRow)

    # prepping for cash values for display
    cashQuery = db.execute("SELECT cash FROM users WHERE id=:userId", userId = str(session["user_id"]))
    cashFlt = cashQuery[0]['cash']
    grandTotal += cashFlt
    cash = '${:,.2f}'.format(cashFlt)
    grandTotal = '${:,.2f}'.format(grandTotal)

    #return render_template("portfolioTable.html", portfolio = portfolio, cash = cash, headerRow = headerRow, currSharePrice = currSharePrice, totalValue = totalValue)
    return render_template("portfolioTable.html",  headerRow=headerRow, allStocks=allStocks, cash=cash, grandTotal=grandTotal)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":     #if you came from clicking on "register" in nav bar
        return render_template("register.html")


    if request.method == "POST":    #if you came from submitting form on register.html
        # username availability checked on register.html
        username = request.form.get("username")
        #print("new user is", username, type(username))

        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # check password validity & return True or Apology msg
        pswrdValid = checkPswrdSecurity(password, confirmation)
        if pswrdValid != True:
            return apology(pswrdValid)

        #generate hash using generate_password_hash courtesy of werkzueg
        hashedPassword = generate_password_hash(password)
        #print("hashedPassword is", hashedPassword, type(hashedPassword), "\n\tfor password:", password)

        # add the new username & hash of its pswrd to our db
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username = username, hash = hashedPassword)

        # once successfully registered, login automatically by storing their id in session["user_id"]
        userId = db.execute("SELECT id FROM users WHERE username=:username", username = username)
        userId = str(userId[0]['id'])
        print ("NEW USER REGISTERED: userId", userId)
        session["user_id"] = userId

        # add new table for all this user's buy/sell transactions
        userIdHx = userId+"Hx"
        print("BUILDING NEW TABLE for transactional history\t\tnamed", userIdHx)
        db.execute("CREATE TABLE :userIdHx('txn' INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, 'time' time, 'buySell' char(1), 'symbol' varchar(255), 'qtyShares' integer, 'valuePerShare' numeric, 'valueAllShares' numeric)", userIdHx = userIdHx)

        # add new table for info to Portfolio in portfolioTable.html
        userIdPortfolio = userId+"Portfolio"
        print("BUILDING NEW TABLE FOR Portfolio\t\tnamed", userIdPortfolio)
        db.execute("CREATE TABLE :userIdPortfolio('symbol' varchar(255) PRIMARY KEY NOT NULL, 'name' varchar(255), 'qtyShares' integer)", userIdPortfolio = userIdPortfolio)

        return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format""" #In JSON b/c multiplatform
    username = request.args.get("username")
    print("Checking new user:", username, type(username))
    rows= db.execute("SELECT * FROM users WHERE username = :username", username=username)
    if len(rows) != 0:  #username choice unavailable
        return jsonify(False)
    elif len(rows) == 0:
        return jsonify(True)
    else:
        print("this shouldn't be happening! Either you get zero or non-zero matches!")
        return jsonify(False)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username, should've been caught by REQUIRED in html", 403)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password, should've been caught by REQUIRED in htm", 403)
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
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
    # Enter stock quote(s)
    if (request.method == "GET"): # coming from navbar
        return render_template("quote.html")


    """Get stock quote."""
    # in resonse to a POST, /quote can render quoted.html, embedding within it the values from lookup(symbol)
    # lookup(symbol) returns dict {"name": quote["companyName"],"price": float(quote["latestPrice"]),"symbol": quote["symbol"]}
    if (request.method == "POST"):
        symbols = []
        quotes = []
        print("\nLet's see what symbols were submitted:")
        # import all symbols submitted into a list
        currSymbolNum = 1
        symbolName = "symbol"+str(currSymbolNum)
        currSymbol = request.form.get(symbolName)
        while (currSymbol or currSymbol == ""): #while form field exists, even if blank
            print("\tcurrSymbol is...", currSymbol)
            if (currSymbol != ""):  #only append non-blank inputs
                symbols.append(currSymbol)
            #prepping next iteration
            currSymbolNum += 1
            symbolName = "symbol"+str(currSymbolNum)
            currSymbol = request.form.get(symbolName)
        print("symbols are now", symbols)

        # look up the quotes, apology if any symbol invalid, else send to quoted.html for Portfolio
        for symbol in symbols:
            quote = lookup(symbol)
            if quote == None:
                return apology("stock symbol " + symbol + " is invalid!")
            else:
                quotes.append(quote)
                print("\n\tquote is", quote)

        # saving a copy in session for use in /fastBuy
        session['quotes'] = quotes

        # prepping other variables to enable buying in quoted.html
        headerRow = ["SYMBOL", "NAME", "PRICE", "QTY TO BUY", "TOTAL COST"]
        qtyNames = []   # names for request.form.get
        priceIds = []       # Id fields are for innerHTML changes
        totalCostIds = []   # Id fields are for innerHTML changes
        for i in range(1,len(quotes)+1):
            qtyNames.append("qtyName"+str(i))
            priceIds.append("priceId"+str(i))
            totalCostIds.append("totalCostId"+str(i))
        cash = usd(getCashBalFlt(db))
        return render_template("quoted.html", quotes=quotes, headerRow=headerRow, priceIds=priceIds, qtyNames=qtyNames, totalCostIds=totalCostIds, cash=cash)



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""               # excmpt from race conditions
    # require text field named "symbol", apology if blank or symbol invalid, per return value of lookup()
    # require input pos integer of shares, in text field named "shares". apology if error validation caught.
    # SELECT user's cash value in db, apology if can't afford

    if (request.method == "GET"): #coming from navbar
        tableHeader = ["SYMBOL", "COMPANY", "PRICE per share", "QUANTITY to buy"]
        cash = usd(getCashBalFlt(db))
        return render_template("buy.html", tableHeader=tableHeader, cash=cash)

    if (request.method == "POST"): #from submitting form on buy.html
        #scroll thru all [symbol, qty] fields into a big list, keep only those with both fields filled out
            # screen for qty validity                   #also done in JS/HTML
            # screen for symbol validity via lookup()   #also done in JS/HTML
        # check $ avail, make the purchases & update all affected tables
        print("\nPROCESSING BUY ORDER")

        # iterate thru form fields, error validate qtys[] and screen for missing info
        [symbols, qtys] = processBuyOrSell()
        if len(symbols) == 0:
            return apology("Missing symbols and/or quantities...")

        # screen for symbol validity, via lookupList(symbolsList)
            # if any symbols invalid, quotes = (False, invalidSymbol)
            # if all symbols valid, quotes = a list of {"name":nameStr, "price":floatPrice, "symbol":symbolStr}
        quotes = lookupList(symbols)
        if quotes[0] == False:
            return apology(f"{quotes[1]} is not a real stock symbol")

        # Takes the list of error-validated qtys[] and its corresponding quotes[], place the orders
        # Updates the user's own hx table and portfolio table, as well as user's final cash in master table of all users
        finalizeBuys(qtys, quotes, db)

        # redirect back to "/" where portfolio will be displayed via portfolioTable.html
        return redirect("/")

@app.route("/checkSymbol", methods=["GET"])
def checkSymbol():              # my own
    """Return lookup() quote if lookup(symbol) is valid in JSON format, else False""" # JSON b/c multiplatform
    symbol = request.args.get("symbol")
    quote = lookup(symbol)
    print("lookup(" + symbol +") returns", quote)
    if (quote):
        return jsonify(quote)
    return jsonify(False)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""      # exempt from race conditions

    if (request.method == "GET"):   # coming from nav bar
        tableHeader = ["SYMBOL", "COMPANY", "PRICE per share", "QUANTITY to sell", "QUANTITY in portfolio"]
        portfolio = db.execute("SELECT symbol FROM :userIdPortfolio", userIdPortfolio=str(session["user_id"])+"Portfolio")
        cash = usd(getCashBalFlt(db))
        return render_template("sell.html", tableHeader=tableHeader, portfolio=portfolio, cash=cash)

    if (request.method == "POST"): # after submitting form on sell.html
        print("\nPROCESSING SELL ORDER")

        # iterate thru form fields, error validate qtys[] and screen for missing info
        [symbols, qtys] = processBuyOrSell()
        if len(symbols) == 0:
            return apology("Missing symbols and/or quantities...")
        # consolidate qtys for any repeating rows of symbols
        [symbols, qtys] = consolidateLists(symbols, qtys)

        # lookupList(symbols) for all the quotes
            # screen for symbol validity... not needed b/c only viable options given in select drag-down menu
            # if all symbols valid, quotes = a list of {"name":nameStr, "price":floatPrice, "symbol":symbolStr}
        quotes = lookupList(symbols)
        if quotes[0] == False:  # this should not trigger b/c already pre-screened client-side
            return apology(f"{quotes[1]} is not a real stock symbol, this should not trigger b/c already pre-screened client-side")

        # retrieve user cash balance
        cash = getCashBalFlt(db)

        # set up table names for SQL query
        userId = str(session["user_id"])
        userIdPortfolio = userId+"Portfolio"
        userIdHx = userId+"Hx"

        # iterate thru qtys[] and quotes[]
        for i in range(len(qtys)):
            # make sure quotes are stocks that user owns
            try:
                qtyOwned = db.execute("SELECT qtyShares from :userIdPortfolio WHERE symbol LIKE :symbol", userIdPortfolio=userIdPortfolio, symbol = symbols[i])
                if qtyOwned == []:  #this shouldn't be triggered, already error proofed earlier by consolidateList()
                    return apology("you don't own any shares of" + symbols[i])
            except:
                return apology("why is this happening?")

            print("\nLOOKING AT qtyOwned", qtyOwned)
            qtyOwned = int(qtyOwned[0]['qtyShares'])
            if qtyOwned < qtys[i]:
                return apology("You don't have enough shares to sell...")

            pricePerShare = quotes[i]["price"]
            priceAllShares = qtys[i] * pricePerShare
            print("\tSELLING", qtys[i], "shares at $" + str(pricePerShare), "each... total = $" + str(priceAllShares))

            # update cash here
            cash = cash + priceAllShares

            # record timestamp of purchase
            now = datetime.now()

            # prepping for database
            symbol = quotes[i]["symbol"]
            name = quotes[i]["name"]
            qty = qtys[i]

            # update portfolio w/ new stock count, delete row if sold out
            newQty = qtyOwned - qty
            if newQty >= 0:
                print(f"\tSELLING #{qty} of #{qtyOwned} owned --> #{newQty} left in portfolio")
                db.execute("UPDATE :userIdPortfolio SET qtyShares = :newQty WHERE symbol = :symbol", userIdPortfolio=userIdPortfolio, symbol=symbol, newQty=newQty)
                if newQty == 0:
                    db.execute("DELETE FROM :userIdPortfolio WHERE symbol = :symbol", userIdPortfolio=userIdPortfolio, symbol=symbol)
            else:
                return apology("wtf, this shouldn't happen")

            # save info for each txn hx under user's own id#Hx table in db
            userIdHx = userId+"Hx"
            db.execute("INSERT INTO :userIdHx ('time', 'buySell','symbol','qtyShares','valuePerShare','valueAllShares') VALUES (:now,'S',:symbol,:qty,:pricePerShare,:priceAllShares)", userIdHx=userIdHx, now=now, symbol=symbol, qty=qty, pricePerShare=pricePerShare, priceAllShares=priceAllShares)

        # after all purchases made, update cash in db
        db.execute("UPDATE users SET cash=:cash WHERE id=:userId", userId=userId, cash=cash)

        # redirect back to "/" where portfolio will be displayed via portfolioTable.html
        return redirect("/")

@app.route("/checkQtyPortfolio", methods=["GET"])
def checkQtyPortfolio():              # my own
    """Return qtyShares of given symbol in user's portfolio table in db, else False""" # JSON b/c multiplatform
    symbol = request.args.get("symbol")
    userIdPortfolio = str(session["user_id"]) + "Portfolio"
    qtyShares = db.execute("SELECT qtyShares FROM :userIdPortfolio where symbol LIKE :symbol", userIdPortfolio=userIdPortfolio, symbol=symbol)
    qtyShares = qtyShares[0]['qtyShares']
    print("qtyShares is", qtyShares, type(qtyShares))
    if (qtyShares):
        return jsonify(qtyShares)
    return jsonify(False)

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    userId = str(session["user_id"])
    headerRow = ["Txn", "TIME", "BUY/SELL", "SYMBOL", "# SHARES", "VALUE PER SHARE", "TOTAL VALUE"]
    history = db.execute("SELECT * FROM :userIdHx", userIdHx = userId+"Hx")
    # modify dollar amounts in history to $xx.xx format
    for row in history:
        if row['valuePerShare']:
            valuePerShare = '${:,.2f}'.format(row['valuePerShare'])
            row['valuePerShare'] = valuePerShare
        if row['valueAllShares']:
            totalValue = '${:,.2f}'.format(row['valueAllShares'])
            row['valueAllShares'] = totalValue
    return render_template("history.html", history=history, headerRow=headerRow)

####################################### OPTIONAL ################################################################
@app.route("/addMoney", methods = ["POST", "GET"])
@login_required
def addMoney():
    """Add money to account"""
    if request.method == "GET":
        return render_template("addMoney.html")

    if request.method == "POST":
        moneySource = request.form.get("moneySource")
        dollars = request.form.get("dollars")
        if not moneySource or not dollars:
            return apology("Missing info, can't add $ to your account!")

        userId = str(session["user_id"])
        currCash = db.execute("SELECT cash FROM users WHERE id=:userId", userId=userId)
        newCash = currCash[0]['cash'] + float(dollars)
        db.execute("UPDATE users SET cash=:cash WHERE id = :userId", cash=newCash, userId=userId)

        #log transaction in history
        now=datetime.now()
        db.execute("INSERT INTO :userIdHx ('time', 'buySell', 'ValueAllShares') VALUES (:now,'$', :dollars)", userIdHx=userId+"Hx", now=now, dollars=dollars)
        return redirect("/")


@app.route("/chgPswrd", methods = ["POST", "GET"])
@login_required
def chgPswrd():
    if request.method == "GET":
        return render_template("chgPswrd.html")

    if request.method == "POST":
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # check password validity & return T or Apology msg
        pswrdValid = checkPswrdSecurity(password, confirmation)
        if pswrdValid != True:
            return apology(pswrdValid)

        # generate hash using generate_password_hash courtesy of werkzueg
        hashedPassword = generate_password_hash(password)
        print("\nhashedPassword is", hashedPassword, type(hashedPassword), "for password:", password)

        # update hashed password in user table in db
        userId = str(session["user_id"])
        print("\nuserId is", userId, session["user_id"])
        db.execute("UPDATE users SET hash=:hashed WHERE id = :userId", hashed=hashedPassword, userId=userId)

        return redirect("/")

@app.route("/fastBuy", methods=["GET", "POST"])
@login_required
def fastBuy():
    """Buy shares of stock"""

    if (request.method == "GET"):
        return apology("Impossible!  This isn't even in nav bar!")

    if (request.method == "POST"): #from submitting form on quoted.html
        print("\nPROCESSING BUY ORDER")

        # get quotes from session, which is same quotes sent to /quoted
        quotes = session['quotes']

        # get data sent from quoted.html
        allQtys = []
        rows = len(quotes)
        for i in range(rows):
            currQty = request.form.get("qtyName"+str(i+1))
            allQtys.append(currQty)

        # allQtys is the qty to order, indices corresp to quotes
        print("allQtys is", allQtys)
        print("quotes is", quotes)

        # server-side error checking: order qtys must be pos integer, and must have a non-zero qty input
        anyOrder = False    #gets toggled to T as soon as a non-zero qty encountered
        for qty in allQtys:
            print("\tchecking qty...", qty, type(qty), checkPosInt(qty))
            if checkPosInt(qty):
                anyOrder = True
            elif qty != '0':  # a zero order is acceptable inside allQtys[]
                return apology("order quantity " + qty + " is invalid!")
        if anyOrder == False:
            return apology("you didn't place any orders...")
        # convert allQtys to integer types, req'd for finalizeBuys() later
        for i in range(len(allQtys)):
            allQtys[i] = int(allQtys[i])
        print("allQtys is now", allQtys, type(allQtys[0]))


        # will recalc grandTotal here instead of importing (can't figure out how anyway) from quoted.html in case JS turned off or messed with
        grandTotal = 0
        for i in range(len(allQtys)):
            grandTotal += allQtys[i] * quotes[i]['price']
        print("grandTotal is", grandTotal)

        # server-side error checking order's grandTotal is non-zero, and <= cash on hand
        cash = getCashBalFlt(db)
        print(grandTotal, type(grandTotal)) #convert type if needed
        if grandTotal > cash:
            return apology("you need more money!")
        if grandTotal == 0:
           return apology("you didn't actually order anything...")

        #Takes the list of error-validated allQtys[] and its corresponding quotes[], place the orders
            #Updates the user's own hx table and portfolio table, as well as user's final cash in master table of all users
        finalizeBuys(allQtys, quotes, db)

        # redirect back to "/" where portfolio will be displayed via portfolioTable.html
        return redirect("/")

####################################### OPTIONAL ################################################################



def errorhandler(e):
    """Handle error"""
    print("\n\n\nWHEN DOES THIS ERRORHANDLER(E) SHOW UP???")
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

####################################### NOTES TO SELF ################################################################
"""
### BUGS!!!
None found so far


### MORE OPTIONAL SPECS

# Allow users to buy more shares or sell shares of stocks they already own via index itself, without having to type stocks' symbols manually.
    #I would incorporate a numerical field for BUY and another for SELL (pre-maxed at qtyShares) in each of the portfolio rows, then send to /fastBuy and /fastSell
# Add a widget? to make it easy to look up stock symbols by company name, in quote.html
# hoverable table rows

What I added...
1. automatic lookup of quotes in buy.html and sell.html
2. automatic look up of #shares on hand in sell.html
3. bunch of client-side error validations
4. allowing user generated fields for multiple requests
    4a. error validate to ignore blank fields
    4b. first row must always be populated
5. reset buttons
6. Allow users to change their passwords.
7. Allow users to add additional cash to their account.
8. Show cash balance in the buy & sell screens, and quoted.html
9. Allow users to buy stocks right after looking up quotes, in quoted.html... it's kinda redundant to have both /buy & /quote by this point though...

"""