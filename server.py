# AKPsi Voting Server Hi

from __future__ import division
import os
import eventlet
eventlet.monkey_patch()

import time
import csv

from collections import defaultdict
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

BID_THRESHOLD = 0.75

ADMINS = set()
ADMINS.add('anjali17')
ADMINS.add('rtiwari1')
ADMINS.add('dnejad')
ADMINS.add('abagchi')
ADMINS.add('mathur')
# Add VP membership, VP finance, and President IDs to ADMINS

has_voted = set()
not_voted = set()
clients = set()
clients_count = defaultdict(int)

votes = defaultdict(lambda: defaultdict(int)) # 2D defaultdict, where votes[choice][rush_name] = count
current_name = ""
current_abstain = ""
is_voting = False
custom_vote = False
custom_counts = defaultdict(int)
custom_opts = []
custom = ""
custom_topic = ""

#
# Initialization
#

def make_id_map():
    temp = defaultdict(str)
    SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
    map_path = os.path.join(SITE_ROOT, 'static', 'ids.csv')
    with open(map_path) as csvfile:
        reader = csv.reader(open(map_path, "rt"))
        for row in reader:
            temp[row[0].strip()] = row[1]
    return temp

id_map = make_id_map()

#
# Utility functions
#

def generate_vote_report():
    if custom_vote:
        total = 0
        for key in custom_counts:
            total += custom_counts[key]

        report = ""
        for key in custom_counts:
            report += key + ": " + str(custom_counts[key]) + " votes | " + str(custom_counts[key]*100/total) + "%<br>"

        return report
    else:
        report_fmt = ("<b>Vote Report: {}</b><br>"
            "Yes: {:.2f}%<br>"
            "No: {:.2f}%<br>"
            "Abstain: {:.2f}%<br>"
            "Bid? {}<br>")
        yes = votes['yes'][current_name]
        no = votes['no'][current_name]
        abstain = votes['abstain'][current_name]
        total  = yes + no + abstain
        bid = ""
        if (yes/total) >= BID_THRESHOLD:
            bid = "YES"
        else:
            bid = "NO"
        report = report_fmt.format(current_name, yes * 100/total, no * 100/total, abstain * 100/total, bid)
        return report


#
# Route definition
#

@app.route('/')
@login_required
def index():
        if cas.username not in id_map:
            return render_template('error.html', error = "denied")
        else:
            return render_template('index.html', username = cas.username)

@app.route('/admin')
@login_required
def admin_panel():
    if cas.username not in ADMINS:
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
    if cas.username in ADMINS:
        has_voted.clear()
        not_voted.clear()
        global is_voting
        global current_name
        global current_abstain
        global votes
        global custom_opts
        global custom_vote
        global custom
        global custom_topic

        print("received: " + str(msg))

        is_voting = True
        if msg['custom'] == "true":
            custom_vote = True
            custom_topic = msg['topic']
            custom_opts = msg['options'].splitlines()
            custom = msg['custom']

            emit('vote_start', {'custom': custom, 'options': custom_opts, 'topic': custom_topic}, namespace='/vote', broadcast=True)

            for key in custom_opts:
                custom_counts[key] = 0;

        else:
            current_name = msg['name']
            current_abstain = msg['abstain']
            print("name is " + current_name)
            print("abstain is " + current_abstain)
            print("is_voting is " + str(is_voting))
            for key in votes:
                votes[key][current_name] = 0
            emit('vote_start', {'custom': msg['custom'], 'name': current_name, 'abstain': current_abstain}, namespace='/vote', broadcast=True)

@socketio.on('end_vote', namespace='/admin')
def end_vote():
    if cas.username in ADMINS:
        global is_voting
        if is_voting:
            print("ending vote...")
            is_voting = False
            report = generate_vote_report()
            print("Report is: " + report)
            emit('vote_report', {'report': report}, namespace='/admin', broadcast=True)
            emit('vote_end', namespace='/vote', broadcast=True)

@socketio.on('get_not_voted', namespace='/admin')
def query_not_voted():
    global not_voted
    if has_voted:
        not_voted = clients - has_voted
    else:
        not_voted = clients
    names = ', '.join([id_map[n] for n in not_voted])
    print("not voted names: " + names)
    emit('receive_not_voted', {'names': names}, namespace='/admin', broadcast=True)

#
# Socket context functions
#

@socketio.on('submit_vote', namespace='/vote')
def function(vote):
    global votes
    global has_voted
    global not_voted

    print("Msg sub_vote is: " + str(vote))
    print("has_voted = ", has_voted)

    if cas.username in has_voted:
        return

    votes_cast = 0
    votes_left = 0

    if custom_vote:
        print("votes is ", custom_vote)
        custom_counts[vote['bid']] += 1
        for key in custom_counts:
            votes_cast += custom_counts[key]
        print("counts is ", custom_counts)
    else:
        print("votes is ", votes)
        print("current_name = " + current_name)
        print("current_abstain = " + current_abstain)
        votes[vote['bid']][current_name] += 1
        for key in votes:
            votes_cast += votes[key][current_name]

    votes_left = len(clients) - votes_cast
    has_voted.add(cas.username)

    if has_voted:
        not_voted = clients - has_voted
    else:
        not_voted = clients
    names = ', '.join([id_map[n] for n in not_voted])

    emit('vote_submitted', {'name':id_map[cas.username], 'votes_cast': votes_cast, 'votes_left': votes_left, 'names': names}, namespace='/admin', broadcast=True)

@socketio.on('connect', namespace='/vote')
def socket_attach():
    clients.add(cas.username)
    clients_count[cas.username] += 1
    print('Clients is: ' + str(clients))
    print('Client count: ' + str(clients_count))
    print('Socket attached: ' + cas.username)
    print('is_voting = ' + str(is_voting))
    if is_voting:
        print("Emitting vote_start to client connected after voting has started")
        if custom_vote:
            emit('vote_start', {'custom': custom, 'options': custom_opts, 'topic': custom_topic})
        else:
            emit('vote_start', {'name': current_name, 'abstain': current_abstain})

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
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 21697)))
