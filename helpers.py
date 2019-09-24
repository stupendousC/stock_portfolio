"""a decorator is a fcn that wraps & replaces another fcn.
Since the original fcn is replaced, you need to remember to copy the original fcn's info to the new fcn, via functools.wraps()"""

import requests
import urllib.parse     # urllib.parse.quote_plus takes program data and makes it safe for use as URL components by quoting special chars and appropriately encoding non-ASCII text

from flask import redirect, render_template, request, session
from functools import wraps     # lets you copy the original fcn's info to the new fcn
from datetime import datetime

# i need this for my own fcns
import math

def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """        Escape special characters.
        https://github.com/jacebrowning/memegen#special-characters        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):  # f is the fcn that's immediately below the @login_required in application.py
    """    Decorate routes to require login.
    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    """Look up quote for symbol, then return info as {"name":nameStr, "price":floatPrice, "symbol":symbolStr}"""

    # Contact API
    try:
        response = requests.get(f"https://api.iextrading.com/1.0/stock/{urllib.parse.quote_plus(symbol)}/quote")
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        quote = response.json()
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"

 ################## EVERYTHING BELOW IS MY OWN, from refactoring and whatnot ##################

def checkPswrdSecurity(password1, password2):
    """ Checks password for:    1. confirmation matches for both
                                2. must have a number
                                3. must have a capital letter
        I didn't bother checking for length b/c don't feel like it
        Returns True if valid, else return apology msg     """

    # check if passwords matc
    if password1 != password2:
        return ("Your password confirmation does not match, please retry")

    # optional extra password checking here (number? case? special char? etc)
    numberCheck = False
    uppercaseCheck = False

    for number in range(0, 10):
        if str(number) in password1:
            #print("OK! you have a number", number)
            numberCheck = True
            break
    if numberCheck == False:
        return ("Password must contain a number, please retry")

    for orderNum in range(65, 91):
        if chr(orderNum) in password1:
            #print("OK! you have an uppercase", chr(orderNum))
            uppercaseCheck = True
            break
    if uppercaseCheck == False:
        return ("Password must contain an uppercase letter, please retry")

    return True




def checkPosInt(value): #my own
    # returns True if value is a non-zero pos int.
    # req import math
    try:
        valFloat = float(value)
        valFloor = float(math.floor(valFloat))
    except:
        print("that's not even a numerical argument...")
        return False
    if valFloat > 0:
        if valFloat-valFloor == 0:
            return True
    return False

def string2Int(value): #my own
    # returns a numerical string value as an integer
    # req import math
    value = math.floor(float(value))
    return value


######## THIS SECTION CONTAINS ALL FCNS REFACTORED FOR /BUY & /SELL ########

def processBuyOrSell():       #refactored for /buy & /sell
    """
    Iterates thru all user generated form fields via request.form.get() for user input on symbolName and qtyName
    Both symbolName and qtyName follow matching formats: symbol1, qty1, symbol2, qty2, etc
    Includes error validation for qtys[], all must be positive and integers types
    Error validation for symbols[] are done via lookupList(symbolsList)
    Returns paired lists for existing symbol and lists of non-zero qty integers
    """
    symbols = []
    qtys = []
    # iterate thru form fields and populate lists
    currSymbolNum = 1
    symbolName = "symbol"+str(currSymbolNum)
    currSymbol = request.form.get(symbolName)

    while (currSymbol or currSymbol == ""): #while form field exists, even if blank
        #print("\tcurrSymbol is...", currSymbol)
        if (currSymbol != ""):  #only append non-blank symbols with non-blank qtys
            qtyName = "qty"+str(currSymbolNum)
            currQty = request.form.get(qtyName)
            if (currQty != "" and checkPosInt(currQty) == True):
                symbols.append(currSymbol)
                qtys.append(string2Int(currQty))
        #prepping next iteration
        currSymbolNum += 1
        symbolName = "symbol"+str(currSymbolNum)
        currSymbol = request.form.get(symbolName)
    print("\n\tsymbols =", symbols, "\n\tqtys =", qtys)

    return [symbols, qtys]


def lookupList(symbolsList):       #refactored for /buy & /sell
    # Takes a list of symbols, error validate then lookup() on each item
    # If symbol invalid, return False and the bogus symbol
    # If symbol valid, append lookup() results to destinationList
        #lookup() results are of format {"name":nameStr, "price":floatPrice, "symbol":symbolStr}
        # returns a list of all the quotes, matching indices to the symbolsList
    destinationList = []
    for symbol in symbolsList:
        quote = lookup(symbol)
        if quote == None:   # I also had JS/AJAX try to catch it before this stage, apology page is annoying
            print(f"TURD ALERT!!! {symbol} is not real")
            return (False, symbol)
        else:
            destinationList.append(quote)
            print("\n\tquote is", quote)
    print("quotes masterlist =", destinationList)
    return destinationList

def getCashBalFlt(db):
    # retrieve user cash balance from users table in db, returns as float
    userId = str(session["user_id"])
    result = db.execute("SELECT cash FROM users WHERE id=:userId", userId = userId)
    cash = float(result[0]['cash'])
    print("cash is", cash, type(cash))
    return cash

def finalizeBuys(qtys, quotes, db):
    """ qtys = list of integers, index of which corresponds to quotes.
        quotes = list of lookup(symbol) results
        Takes the list of error-validated qtys[] and its corresponding quotes[], place the orders
        Updates the user's own hx table and portfolio table, as well as user's final cash in master table of all users
    """
    # retrieve user cash balance
    cash = getCashBalFlt(db)

    # set up table names for SQL query
    userId = str(session["user_id"])
    userIdPortfolio = userId+"Portfolio"
    userIdHx = userId+"Hx"

    # iterate thru qtys[] and quotes[], confirm $ enough to buy
    for i in range(len(qtys)):
        qty = qtys[i]
        if qty == 0:        # in cases where qtys include inputs of zero orders are acceptable
            print("\tskipping this qty order of ZERO")
            continue
        pricePerShare = quotes[i]["price"]
        priceAllShares = qty * pricePerShare
        print("\nBUYING", qty, "shares at $" + str(pricePerShare), "each... total = $" + str(priceAllShares))
        if cash < priceAllShares:
            return apology("You don't have enough $ for " + quotes[i]["name"])

        # update cash here
        cash = cash - priceAllShares

        # record timestamp of purchase
        now = datetime.now()

        # prepping for database
        symbol = quotes[i]["symbol"]
        name = quotes[i]["name"]

        # save info for Portfolio under user's own id#Portfolio table in db
            # insert if new stocks, update if existing stocks
        existingQty = db.execute("SELECT qtyShares FROM :userIdPortfolio WHERE symbol = :symbol", userIdPortfolio=userIdPortfolio, symbol=symbol)
        #print(f"Does {symbol} already have shares in Portfolio table??\t", existingQty)
        if not existingQty:     # if empty list returned
            print("\tADDING NEW STOCK")
            db.execute('INSERT INTO :userIdPortfolio (symbol, name, qtyShares) VALUES (:symbol, :name, :qty)', userIdPortfolio=userIdPortfolio, symbol=symbol, name=name, qty=qty)
        elif len(existingQty) > 1:
            return apology("Impossible! Symbol is a primary key!")
        else:
            print("\tUPDATING EXISTING STOCK")
            newQty = existingQty[0]['qtyShares'] + qty
            #print("\texistingQty is", existingQty[0]['qtyShares'], "\tneed to add to qty", qty, "\tnewQty =", newQty)
            db.execute("UPDATE :userIdPortfolio SET qtyShares = :newQty WHERE symbol = :symbol", userIdPortfolio=userIdPortfolio, symbol=symbol, newQty=newQty)

        # save info for each txn hx under user's own id#Hx table in db
        db.execute("INSERT INTO :userIdHx ('time', 'buySell','symbol','qtyShares','valuePerShare','valueAllShares') VALUES (:now,'B',:symbol,:qty,:pricePerShare,:priceAllShares)", userIdHx=userIdHx, now=now, symbol=symbol, qty=qty, pricePerShare=pricePerShare, priceAllShares=priceAllShares)

    # after all purchases made, update cash in db
    db.execute("UPDATE users SET cash=:cash WHERE id=:userId", userId=userId, cash=cash)
    return

def checkRepeats(symbolsList):  # I can't opt out of this b/c can't trust user to not turn off JS error checking, and since class specs ask for drag down menu, i can't just prepopulate all rows to be unique symbols
    # returns dict of the index positions of first Occurrences, and their corresponding repeats' indices
    results = {}
    repeats = []
    for i in range(len(symbolsList)):
        if i in repeats:
            continue
        entity = symbolsList[i]
        results[i] = []
        #print("ENTITY is...", entity)
        for j in range(i+1, len(symbolsList)):
            possibleTwin = symbolsList[j]
            #print("\tcomparing to...", possibleTwin)
            if entity == possibleTwin:
                repeats.append(j)
                results[i].append(j)
    return results

def consolidateLists(testListUnique, testListQtys):
    # takes in 2 lists needed to test on: testListUnique (symbols list) & corresponding testListQty (qty list)
    # returns as a consolidated lists of unique symbols and its corresp qtys
    # example: symbols = ['a', 'b', 'c', 'a', 'b'] and qtys = [1,1,1,1,1] will return as (['a', 'b', 'c'], [2,2,1])
    results = checkRepeats(testListUnique)
    listUnique = []
    listQtys = []
    for indexAsKey in results:
        indexAsValue = results[indexAsKey]
        if indexAsValue == []: # single occurrence
            listUnique.append(testListUnique[indexAsKey])
            listQtys.append(testListQtys[indexAsKey])
        if indexAsValue != []:
            print("found repeats of index",indexAsKey, "at indices:", indexAsValue)
            listUnique.append(testListUnique[indexAsKey]) # unique symbol, only done once
            runningTotal = testListQtys[indexAsKey]     # initial qty from first occurrence
            for meToo in indexAsValue:      # adding up all the repeating row's qtys
                runningTotal += testListQtys[meToo]
            listQtys.append(runningTotal)
    print("listUnique is now", listUnique)
    print("listQtys is now", listQtys)
    return [listUnique, listQtys]


######## THIS SECTION ABOVE ARE ALL FCNS REFACTORED FOR /BUY & /SELL ########




""" MEH...
def scrollThru(originList, destinationList):   #My own
    for item in originList:
        if item == None:
            return
"""