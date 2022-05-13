# Python-based bitcoin miners repair dashboard
# Jacob Townsend
#
# 5/10/2022
from flask import Flask
from flask import Flask, flash, url_for, redirect, render_template, request, session, abort
from passlib.hash import sha256_crypt
from datetime import date, timedelta
import mysql.connector as mariadb
import os
import operator

# initialize Flask and the mariadb connection...
app = Flask(__name__)
def getdb():
    mariadb_connect = mariadb.connect(user='username_here', password='password_here', database='database_here')
    return mariadb_connect

# set a before request to help keep track of user activity
@app.before_request
def before_request():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=20)
    session.modified = True

# define our "home" method. 
# Check if the user is loged in, and if not redirect to the login page
@app.route('/')
def home():
    if not session.get('logged_in'):
        return render_template('/login.html')
    else:
        # query the database for open tickets and display the 10 most recent ones on the index page
        db = getdb()
        cur = db.cursor(dictionary=True)
        tickets = cur.execute('SELECT * FROM tickets EXCEPT SELECT * FROM tickets WHERE status="closed" ORDER BY repair_id DESC LIMIT 10')
        tickets = cur.fetchall()
        cur.close()
        db.close()
        return render_template('/index.html', tickets=tickets)

# Login function
# Check the login table in our database and update the user's session if a match is found
@app.route('/login', methods=['POST', 'GET'])
def do_admin_login():
    if request.method == "GET":
        return home()

    login = request.form
    userName = login['username']
    password = login['password']
    account = False

    if not userName or not password:
        return home()
    try:
        db = getdb()
        cur = db.cursor(buffered=True)
        data = cur.execute("SELECT * FROM Login WHERE username=%s", (userName, ))
        data = cur.fetchone()[2]
        cur.close()
        db.close()

        if sha256_crypt.verify(password, data):
            account = True

        if account:
            session['logged_in'] = True
            session['username'] = userName
        else:
            flash('wrong password!')
        
        return home()
    except:
        flash("User not found!")
        return home()

# Enable the user to sign out...
@app.route('/logout')
def logout():
    session['logged_in'] = False
    return home()

# new ticket function...
@app.route('/new_ticket', methods=['GET', 'POST'])
def new_ticket():
    # check if the user is signed in
    if not session.get('logged_in'):
        return render_template('/login.html')

    # checkf if we're getting a POST request.
    # If we are, insert a new repair ticket into the database
    if request.method == 'POST':
        customer_name = request.form['customer_name']
        machine_model = request.form['machine_model']
        status = request.form['status']
        tdate = date.today()
     
        if not (customer_name and machine_model and status):
            flash("Please fill all fields")
            return redirect(request.referrer)
        else:
            db = getdb()
            cur = db.cursor(dictionary=True)
            cur.execute('INSERT INTO tickets (date, customer_name, status, machine_model, created_by) VALUES (%s, %s, %s, %s, %s)', (tdate, customer_name, status, machine_model, session.get('username')))
            tid = cur.lastrowid
            db.commit()
            cur.close()
            db.close()
            return redirect(url_for('edit', ticket_id = tid))

    db = getdb()
    cur = db.cursor(dictionary=True)
    cur.execute('SELECT * FROM miners')
    miners = cur.fetchall()
    cur.execute('SELECT * FROM statuses')
    statuses=cur.fetchall()
    cur.close()
    db.close()
    return render_template("/ticket.html", miners=miners, statuses=statuses)

# Function for editing existing tickets
@app.route('/<int:ticket_id>', methods = ['GET', 'POST'])
def edit(ticket_id):
    # Check if the user is signed in...
    if not session.get('logged_in'):
        return render_template('/login.html')

  # Check if we are getting a POST request. 
  # If we are, update the ticket that was changed
    if request.method == 'POST':
        machine_model = request.form['machine_model']
        status = request.form['status']

        db = getdb()
        cur = db.cursor(dictionary=True)
        cur.execute('SELECT * FROM tickets WHERE repair_id=%s', (ticket_id,))
        data = cur.fetchone()
        cur.execute('UPDATE tickets SET machine_model=%s, status=%s WHERE repair_id=%s', (machine_model, status, ticket_id))
        db.commit()
        cur.close()
        db.close()
      
        return home()

  # If it's a GET request, pull information from the database
  # and pre-populate the page with that information
    else:
        db = getdb()
        cur = db.cursor(dictionary=True)
        cur.execute('SELECT * FROM tickets WHERE repair_id = %s', (ticket_id,))
        ticket = cur.fetchone()
        cur.execute('SELECT * FROM miners')
        miners = cur.fetchall()
        cur.execute('SELECT * FROM statuses')
        statuses = cur.fetchall()
        cur.execute('SELECT * FROM comments WHERE rid = %s', (ticket_id,))
        notes = cur.fetchall()
        cur.close()
        db.close()

        if ticket is None:
            abort(404)

        return render_template("/edit.html", ticket=ticket, miners=miners, notes=notes, statuses=statuses)

# function to add notes to a repair
@app.route("/<int:ticket_id>/addnote", methods=['POST', 'GET'])
def addnote(ticket_id):
    if not session.get('logged_in') or request.method == 'GET':
        return home()
    note = request.form['note']
    user = session.get('username')
    tdate = date.today()

    db = getdb()
    cur = db.cursor(dictionary=True)
    cur.execute("INSERT INTO comments (note, creator, date, rid) VALUES (%s, %s, %s, %s)", (note, user, tdate, ticket_id))
    db.commit()
    cur.close()
    db.close()
    return redirect(request.referrer)

# function to delete notes from a repair
@app.route("/<int:note_id>/delete", methods=['POST'])
def deletenote(note_id):
    if not session.get('logged_in'):
        return home()

    db = getdb()
    cur = db.cursor(dictionary=True)
    cur.execute("DELETE FROM comments WHERE nid=%s", (note_id,))
    db.commit()
    cur.close()
    db.close()
    return redirect(request.referrer)

# function to create a customer view for a given ticket
@app.route("/customerview/<int:ticket_id>", methods=['GET'])
def customerview(ticket_id):
    db = getdb()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM tickets WHERE repair_id=%s", (ticket_id,))
    ticket = cur.fetchone()
    cur.close()
    db.close()

    return render_template("/customerview.html", ticket=ticket)

# function to search the database
@app.route("/search", methods=['POST'])
def search():
    if not session.get('logged_in'):
        return render_template('/login.html')
    # if the search bar is empty, just return to the home view
    if not request.form["search"]:
        return home()
    # Check the database for matches to the search bar input
    db = getdb()
    cur = db.cursor(dictionary=True)
    search = request.form["search"]
    cur.execute('SELECT * FROM tickets WHERE repair_id = %s OR (customer_name LIKE %s) OR (date = %s)', (search, search, search))
    result = cur.fetchall()
    cur.close()
    db.close()
    return render_template('index.html', tickets=result)


if __name__ == "__main__":
    app.secret_key = os.urandom(12)
    app.run(debug=False,host='0.0.0.0', port=5000)
