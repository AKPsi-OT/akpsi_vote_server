import os
import eventlet
eventlet.monkey_patch()

import time
from collections import defaultdict
from threading import Thread
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, disconnect
from flask_cas import CAS, login, logout, login_required

app = Flask(__name__)

socketio = SocketIO(app)
cas = CAS(app)

app.debug = True
app.config['SECRET_KEY'] = 'secret!'
app.config['CAS_SERVER'] = 'https://login.umd.edu'
app.config['CAS_LOGIN_ROUTE'] = '/cas/login'
app.config['CAS_AFTER_LOGIN'] = 'index'

admins = set()
admins.add('cgonza1')

clients = set()
clients_count = defaultdict(int)

votes = defaultdict(lambda: defaultdict(int)) # 2D defaultdict, where votes[choice][rush_name] = count
current_name = None
current_abstain = None
is_voting = False

thread = None

def background_thread():
    """Example of how to send server generated events to clients."""
    count = 0
    while True:
        time.sleep(10)
        count += 1

# socketio.emit('my response',
#               {'data': 'Server generated event', 'count': count},
#               namespace='/vote')

# global thread
# if thread is None:
#     thread = Thread(target=background_thread)
#     thread.start()

#
# Route definition
#

@app.route('/')
@login_required
def index():
    # Check if already connected, only admins are allowed to do this
    if cas.username not in admins and cas.username in clients:
        return render_template('error.html', error="duplicate")
    else:
        return render_template('index.html', username = cas.username)

@app.route('/admin')
@login_required
def admin_panel():
    if cas.username not in admins:
        return render_template('error.html', error="denied")
    else:
        return render_template('admin.html')

#
# Admin socket context functions
#

@socketio.on('connect', namespace='/admin')
def admin_connect():
    print("Admin connected: " + cas.username)

@socketio.on('disconnect', namespace='/admin')
def admin_disconnect():
    print("Admin disconnected: " + cas.username)

@socketio.on('start_vote', namespace='/admin')
def start_vote(msg):
    if cas.username in admins:
        is_voting = True
        print("name is " + msg['name'])
        print("abstain is " + msg['abstain'])
        current_name = msg['name']
        current_abstain = msg['abstain']
        for key in votes:
            votes[key][current_name] = 0
        emit('vote_start', {'name': current_name, 'abstain': current_abstain}, namespace='/vote', broadcast=True)

@socketio.on('end_vote', namespace='/admin')
def end_vote():
    if cas.username in admins:
        is_voting = False
        emit('vote_end', namespace='/vote', broadcast=True)

#
# Socket context functions
#

@socketio.on('submit_vote', namespace='/vote')
def function(vote):
    votes[vote['bid']][current_name] += 1
    votes_cast = 0
    votes_left = 0

    for key in votes:
        votes_cast += votes[key][current_name]

    votes_left = len(clients) - votes_cast
    print("votes is ", votes)
    print("current_name = " + current_name)
    print("current_abstain = " + current_abstain)
    emit('vote_submitted', {'name':current_name, 'votes_cast': votes_cast, 'votes_left': votes_left}, namespace='/admin', broadcast=True)

@socketio.on('connect', namespace='/vote')
def socket_attach():
    clients.add(cas.username)
    clients_count[cas.username] += 1
    print('Clients is: ' + str(clients))
    print('Client count: ' + str(clients_count))
    print('Socket attached: ' + cas.username)
    print('is_voting = ' + is_voting)
    if is_voting == True:
        print("Emitting vote_start to client connected after voting has started")
        emit('vote_start', {'name': msg['name'], 'abstain': msg['abstain']})

@socketio.on('disconnect', namespace='/vote')
def socket_detach():
    print('Socket disconnected from user: ' + cas.username)
    clients_count[cas.username] -= 1
    print('Client count: ' + str(clients_count))
    if cas.username in clients and clients_count[cas.username] == 0:
        print('Removing: ' + cas.username)
        clients.remove(cas.username)
    print('Clients is: ' + str(clients))

if __name__ == "__main__":
    # Fetch the environment variable (so it works on Heroku):
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
