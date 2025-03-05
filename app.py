from flask import Flask, render_template, url_for, g, request
from database import get_db
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
upload_folder = 'files'
app.config['UPLOAD_FOLDER'] = upload_folder
# max file size to upload is 10 MB
app.config['MAX_CONTENT_PATH'] = 10 * 1024 * 1024

@app.teardown_appcontext
def close_db(error):
    db = g.pop('attendance_db', None)
    if db:
        db.close()

def get_menu():
    menuitems = [
        { 'anchor': url_for('home'), 'title': 'HOME' },
        { 'anchor': url_for('lookup'), 'title': 'LOOKUP' },
        { 'anchor': url_for('importfile'), 'title': 'IMPORT FILE' }
    ]

    return menuitems

@app.route('/')
def home():
    now = datetime.now()

    db = get_db()
    cur = db.cursor()
    # elapsed_days is the days since 'now' when the report is run - so to get a 
    # week old report, get only 7 days.
    sql = '''
        select s.id, s.firstname, s.lastname, a.att_date, a.att_time,
        (julianday(date('now'))-julianday(date(a.att_date))) elapsed_days
        from attendance a left join staff s on a.staff = s.id
        where (julianday(date('now'))-julianday(date(a.att_date))) < 10
        order by a.id desc
    '''
    cur.execute(sql)
    data = cur.fetchall()
    if len(data) == 0:
        data = None
    return render_template('index.html', data=data, menuitems=get_menu())


@app.route('/lookup', methods=['GET', 'POST'])
def lookup():
    staff = None
    data = None
    stafflist = None
    db = get_db()
    cur = db.cursor()
    if request.method == 'POST':
        staff = request.form['selectstaff']
        sql = 'select id, firstname, lastname from staff where id = ?'
        cur.execute(sql, (staff,))
        staff = cur.fetchone()
        if staff:
            sql = '''select 
                case cast (strftime('%m', att_date) as integer) 
                    when 1 then 'January'
                    when 2 then 'February'
                    when 3 then 'March'
                    when 4 then 'April'
                    when 5 then 'May'
                    when 6 then 'June'
                    when 7 then 'July'
                    when 8 then 'August'
                    when 9 then 'September'
                    when 10 then 'October'
                    when 11 then 'November'
                    else 'December' 
                end as themonth,
                case cast (strftime('%w', att_date) as integer) 
                    when 0 then 'Sunday'
                    when 1 then 'Monday'
                    when 2 then 'Tuesday'
                    when 3 then 'Wednesday'
                    when 4 then 'Thursday'
                    when 5 then 'Friday'
                    else 'Saturday' 
                end as day,
                strftime('%d', att_date) as daynumber,
                strftime('%Y', att_date) as theyear,
                cast (strftime('%w', att_date) as integer) as weekday,
                att_date, att_time from attendance where staff = ?
                order by id desc
            '''
            cur.execute(sql, (staff['id'],))
            data = cur.fetchall()                

    sql = '''
        select id, firstname, lastname from staff
    '''
    cur.execute(sql)
    stafflist = cur.fetchall()
    return render_template('lookup.html', stafflist=stafflist, data=data, menuitems=get_menu(), staff=staff)

@app.route('/importfile', methods=['GET', 'POST'])
def importfile():
    message = None
    now = datetime.now()
    if request.method == "POST":
        file = request.files['file']
        filename = secure_filename(file.filename)
        db = get_db()
        cur = db.cursor()
        sql = 'insert into fileuploads (filedate, filename) values (?, ?)'
        cur.execute(sql, [now, os.path.join(app.config['UPLOAD_FOLDER'], filename)])
        db.commit()
        fileid = cur.lastrowid
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        message = f'File {filename} uploaded. ID = {fileid}'

    return render_template('importfile.html', menuitems=get_menu(), message=message)

