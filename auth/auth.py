from flask import Blueprint, render_template, url_for, g, session, redirect, request
from database import get_db, hashpass, checkpass, onetime, otp_check
from datetime import datetime
from sms import sendSMS
from sendEmail import send_otp_email
import pyotp
import cred

auth = Blueprint("auth", __name__, static_folder="static", template_folder="templates")

DEBUGGING = False

from constants import *

@auth.route('/', methods=['GET', 'POST'])
def login():
    if "user" in session and session["user"]["otp"]:
        return redirect(url_for('home'))
    
    now = datetime.now()
    now_string = now.strftime('%Y-%m-%d %H:%M:%S').upper()
    message = None
# -----------------
# debugging - enable this code
# -----------------
# create a dummy session and go to the home page.
    if DEBUGGING:
        user = {
            'id': 0,
            'firstname': 'debug',
            'lastname': 'debug',
            'email': 'email@debug.com',
            'phone': '254000000000',
            'passauth': None,
            'tfaauth': None,
            'auth': (ADMIN,),
            'locked': False,
            'lastlogin': now_string,
            'otp': 123456
        }
        session['user'] = user
        session.modified = True
        return redirect(url_for('home'))

# END OF DEBUGGING
# ------------------
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db()
        cur = db.cursor()
        sql = '''
            select id, firstname, lastname, email, password, phone, passauth, auth, tfaauth, locked,
                lastlogin from users where email = ?
        '''
        cur.execute(sql, (email,))
        data = cur.fetchone()
        if data is None:
            message = 'Invalid user or password'
            return render_template('auth/login.html', message=message)
        elif data['locked']:
            message = 'Account Locked - see administrator'
            return render_template('auth/login.html', message=message)
        else:
            if checkpass(data['password'], password):
                auth = tuple([int(x) for x in data['auth']])
                user = {
                    'id': data['id'],
                    'firstname': data['firstname'],
                    'lastname': data['lastname'],
                    'email': data['email'],
                    'phone': data['phone'],
                    'passauth': data['passauth'],
                    'tfaauth': data['tfaauth'],
                    'auth': auth,
                    'locked': data['locked'],
                    'lastlogin': data['lastlogin'],
                    'otp': None
                }
                session['user'] = user
                session.modified = True
                if user['tfaauth']:
                    if request.form['authtype'] == "sms":
                        otp = onetime()
                        sql = 'update otp set valid = 0 where userid = ?'
                        cur.execute(sql, (user['id'],))
                        db.commit()
                        now = datetime.now()
                        sql = 'insert into otp (userid, otp, otp_time, valid) values (?, ?, ?, ?)'
                        cur.execute(sql, (user['id'], otp, now, 1))
                        db.commit()
                        message = f"Attendance App: enter the following OTP to login {otp}"
                        sendSMS(message, user['phone'])
                        send_otp_email(message, user['email'])
                        return render_template('auth/otp.html')
                    else:
                        return render_template('auth/google_authenticator.html')
                else:
                    userid = session['user']['id']
                    now = datetime.now()
                    sql = 'update users set lastlogin = ? where id = ?'
                    cur.execute(sql, (now, userid))
                    db.commit()
                    session['user']['otp'] = '000000'
                    session.modified = True
                    return redirect(url_for('home'))
            else:
                message = 'Invalid user or password'
                return render_template('auth/login.html', message=message)
    
    return render_template('auth/login.html', message=message)

@auth.route('/check_otp', methods=['GET', 'POST'])
def check_otp():
    if 'user' in session and session['user']['otp']:
        return redirect(url_for('home'))
    
    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    message = None
    if request.method == "POST":
        otp = request.form['otp']
        userid = session['user']['id']
        db = get_db()
        cur = db.cursor()
        sql = 'select id, userid, userid, otp, otp_time, valid from otp where userid = ? and otp = ? and valid = 1'
        cur.execute(sql, [userid, otp])
        data = cur.fetchone()
        if data is None:
            # otp failed
            message = "Invalid OTP - try again"
        else:
            # remove the milliseconds from the datetime stored in the database
            send_time = data['otp_time']
            ms_offset = send_time.rfind('.')
            send_time = send_time[:ms_offset]
            otp_time = datetime.strptime(send_time, '%Y-%m-%d %H:%M:%S')
            if otp_check(otp_time, now):
                sql = 'update users set lastlogin = ? where id = ?'
                cur.execute(sql, (now, userid))
                db.commit()
                session['user']['otp'] = otp
                session['modified'] = True
                return redirect(url_for('home'))
            else:
                message = 'Timeout... try again'
    return render_template('auth/login.html', message=message)

@auth.route('/check_googleauth', methods=['GET', 'POST'])
def check_googleauth():
    if 'user' in session and session['user']['otp']:
        return redirect(url_for('home'))

    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    message = None

    if request.method == "POST":
        otp = request.form['otp']
        userid = session['user']['id']

        totp = pyotp.TOTP(cred.secret_key)
        if totp.verify(otp):
            db = get_db()
            cur = db.cursor()
            sql = 'update users set lastlogin = ? where id = ?'
            cur.execute(sql, (now, userid))
            db.commit()
            session['user']['otp'] = otp
            session['modified'] = True
            return redirect(url_for('home'))
        else:
            message = "Invalid Authenticator Code. Try again"

    return render_template('auth/login.html', message=message)

@auth.route('/logout', methods=['GET','POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('auth.login'))

@auth.route('/otplogin', methods=['GET', 'POST'])
def otplogin():
    if "user" in session and session["user"]["otp"]:
        return redirect(url_for('home'))

    now = datetime.now()
    now_string = now.strftime('%d%b%Y %H:%M:%S').upper()
    message = None

    if request.method == 'POST':
        email = request.form['email']

        db = get_db()
        cur = db.cursor()
        sql = '''
            select id, firstname, lastname, email, password, phone, passauth, auth, tfaauth, locked,
                lastlogin from users where email = ?
        '''
        cur.execute(sql, (email,))
        data = cur.fetchone()
        if data is None:
            message = 'Invalid user or password'
            return render_template('auth/login.html', message=message)
        elif data['locked']:
            message = 'Account Locked - see administrator'
            return render_template('auth/login.html', message=message)
        else:
            # user exists, set up the data
            auth = tuple([int(x) for x in data['auth']])
            user = {
                'id': data['id'],
                'firstname': data['firstname'],
                'lastname': data['lastname'],
                'email': data['email'],
                'phone': data['phone'],
                'passauth': data['passauth'],
                'tfaauth': data['tfaauth'],
                'auth': auth,
                'locked': data['locked'],
                'lastlogin': data['lastlogin'],
                'otp': None
            }
            session['user'] = user
            session.modified = True
            # go and get the OTP
            if request.form["authtype"] == "sms":
                otp = onetime()
                sql = 'update otp set valid = 0 where userid = ?'
                cur.execute(sql, (user['id'],))
                db.commit()
                now = datetime.now()
                sql = 'insert into otp (userid, otp, otp_time, valid) values (?, ?, ?, ?)'
                cur.execute(sql, (user['id'], otp, now, 1))
                db.commit()
                message = f"Attendance App: enter the following OTP to login {otp}"
                sendSMS(message, user['phone'])
                send_otp_email(message, user['email'])
                return render_template('auth/otp.html')
            else:
                return render_template('auth/google_authenticator.html')
    
    return render_template('auth/otplogin.html', message=message)
