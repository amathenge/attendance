from flask import Flask, render_template, url_for, g, request, redirect
from database import get_db
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import re
from cleanup import cleanup_import

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
        { 'anchor': url_for('timereport'), 'title': 'TIME REPORT' },
        { 'anchor': url_for('importfile'), 'title': 'IMPORT FILE' },
        { 'anchor': url_for('listfiles'), 'title': 'LIST FILES' },
        { 'anchor': url_for('lookup_original'), 'title': 'RAW DATA' }
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
    valid = []
    statussummary = { 'validlines': 0, 'totallines': 0 }
    if request.method == "POST":
        file = request.files['file']
        filename = secure_filename(file.filename)
        db = get_db()
        cur = db.cursor()
        # if the file exists, don't add it again
        sql = 'select filename from fileuploads where filename = ?'
        cur.execute(sql, (os.path.join(app.config['UPLOAD_FOLDER'], filename),))
        data = cur.fetchone()
        if data is not None:
            message = 'File exists - not uploaded'
            valid = None
        else:
            sql = 'insert into fileuploads (filedate, filename) values (?, ?)'
            cur.execute(sql, [now, os.path.join(app.config['UPLOAD_FOLDER'], filename)])
            db.commit()
            fileid = cur.lastrowid
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            message = f'File {filename} uploaded. ID = {fileid}'
            # check data in file
            f = open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'r')
            lineOK = True
            linecount = 0
            validlines = 0
            # clear the importdata table
            # sql = 'delete from importdata'
            # cur.execute(sql)
            # db.commit()
            # --------------------------
            sql = '''
                insert into importdata (fileid, staff, att_date, att_time, att_type, att_dir, att_status, valid) 
                values (?, ?, ?, ?, ?, ?, ?, ?)    
            '''
            sqlValues = []
            for line in f:
                sqlValues.clear()
                lineOK = True
                linecount += 1
                line = line.strip().split()
                if len(line) < 7:
                    lineOK = False
                else:
                    if line[0] not in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']:
                        lineOK = False
                    dateStr = r'^\d{4}-\d{2}-\d{2}$'
                    if not re.match(dateStr, line[1]):
                        lineOK = False
                    timeStr = r'^\d{2}:\d{2}:\d{2}$'
                    if not re.match(timeStr, line[2]):
                        lineOK = False
                    if line[3] not in ['0', '1', '2']:
                        lineOK = False
                    if line[4] not in ['0', '1', '2']:
                        lineOK = False
                    if line[5] not in ['0', '1', '2']:
                        lineOK = False
                    if line[6] not in ['0', '1', '2']:
                        lineOK = False
                valid.append({'line': linecount, 'valid': lineOK})
                sqlValues.append(fileid)
                sqlValues.append(int(line[0]))
                sqlValues.append(line[1])
                sqlValues.append(line[2])
                sqlValues.append(int(line[3]))
                sqlValues.append(int(line[4]))
                sqlValues.append(int(line[5]))
                sqlValues.append(lineOK)
                
                cur.execute(sql, sqlValues)
                db.commit()

            f.close()

            if len(valid) == 0:
                valid = None
            else:
                for item in valid:
                    if item['valid']:
                        validlines += 1
                statussummary = { 'validlines': validlines, 'totallines': linecount }
            sql = 'update fileuploads set totallines = ?, validlines = ? where id = ?'
            cur.execute(sql, (linecount, validlines, fileid))
            db.commit()

            # insert lines from importdata to attendance where valid
            if valid:
                sql = '''
                    insert or ignore into attendance (staff, att_date, att_time, att_type, att_dir, att_status)
                    select staff, att_date, att_time, att_type, att_dir, att_status from importdata
                    where valid = 1 and fileid = ?
                '''
                cur.execute(sql, (fileid,))
                db.commit()

                sql = '''
                    insert or ignore into original_data (staff, att_date, att_time, att_type, att_dir, att_status)
                    select staff, att_date, att_time, att_type, att_dir, att_status from importdata
                    where valid = 1 and fileid = ?
                '''
                cur.execute(sql, (fileid,))
                db.commit()
                

            # call the cleanup module to get rid of duplicates.
            cleanup_import()

    return render_template('importfile.html', menuitems=get_menu(), message=message, status=valid, statussummary=statussummary)


@app.route('/listfiles', methods=['GET', 'POST'])
def listfiles():
    db = get_db()
    cur = db.cursor()
    sql = 'select id, filedate, filename from fileuploads order by id desc'
    cur.execute(sql)
    data= cur.fetchall()
    if len(data) == 0:
        data = None
    # facility to delete....
    return render_template('listfiles.html', menuitems=get_menu(), files=data)

@app.route('/filedelete/<fid>')
def filedelete(fid):
    db = get_db()
    cur = db.cursor()
    # check if file actually exists
    sql = 'select id, filedate, filename from fileuploads where id = ?'
    cur.execute(sql, (fid,))
    data = cur.fetchone()
    if data is None:
        return redirect(request.referrer)
    sql = 'delete from importdata where fileid = ?'
    cur.execute(sql, (fid,))
    db.commit()
    # delete file from filesystem
    if os.path.exists(data['filename']):
        os.remove(data['filename'])
    # delete file from entry
    sql = 'delete from fileuploads where id = ?'
    cur.execute(sql, (fid,))
    db.commit()

    return redirect(request.referrer)


@app.route('/showimportdata/<fid>')
def showimportdata(fid):
    db = get_db()
    cur = db.cursor()
    sql = 'select filename from fileuploads where id = ?'
    cur.execute(sql, (fid,))
    filename = cur.fetchone()
    if filename is None:
        return redirect(request.referrer)
    filename = filename['filename']
    sql = '''
        select f.id, f.fileid, f.staff, s.firstname || ' ' || s.lastname as fullname, f.att_date, f.att_time, 
        f.att_type, f.att_dir, f.att_status, f.valid
        from importdata f join staff s on (f.staff = s.id) where fileid = ?
    '''
    cur.execute(sql, (fid,))
    data = cur.fetchall()
    if len(data) == 0:
        data = None

    return render_template('showimportdata.html', menuitems=get_menu(), data=data, filename=filename)

@app.route('/timereport', methods=['GET', 'POST'])
def timereport():
    staff = None
    data = None
    stafflist = None
    message = None
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        data = []
        staff = request.form['selectstaff']
        sql = "select id, firstname || ' ' || lastname as fullname from staff where id = ?"
        cur.execute(sql, (staff,))
        staff = cur.fetchone()

        staffid = staff['id']

        # print(f"id={staffid}, {staff['fullname']}")
        sql = 'select distinct(att_date) from attendance where staff = ? order by id desc'
        cur.execute(sql, (staffid,))
        records = cur.fetchall()

        for record in records:
            temp = {'att_date': record['att_date']}
            # print(f"{record['att_date']}: ", end='')
            sql = 'select id, att_time from attendance where staff = ? and att_date = ? order by id asc'
            cur.execute(sql, (staffid,record['att_date']))
            clocks = cur.fetchall()
            
            if len(clocks) == 2:
                start_time = clocks[0]['att_time']
                end_time = clocks[1]['att_time']
                temp['start_time'] = start_time
                temp['end_time'] = end_time
                # print(f"From {start_time} To {end_time} = ", end='')
            elif len(clocks) == 1:
                temp['start_time'] = clocks[0]['att_time']
                temp['end_time'] = '-'
                message = 'Inconsistent data'
            else:
                temp['start_time'] = '-'
                temp['end_time'] = '-'
                message = 'Inconsistent data'

            #     print(f"Inconsistent clocking data - Clocks = {len(clocks)}")

            if len(clocks) == 2:
                clock_start = datetime.strptime(start_time, '%H:%M:%S')
                clock_end = datetime.strptime(end_time, '%H:%M:%S')
                difference = clock_end - clock_start
                difference_secs = difference.total_seconds()
                if difference_secs >= 60:
                    difference_mins = (difference_secs - (difference_secs % 60)) / 60
                    difference_secs = difference_secs % 60
                else:
                    difference_mins = 0
                if difference_mins >= 60:
                    difference_hours = (difference_mins - (difference_mins % 60)) / 60
                    difference_mins = difference_mins % 60
                else:
                    difference_hours = 0
                difference_secs = int(difference_secs)
                difference_mins = int(difference_mins)
                difference_hours = int(difference_hours)
                temp['work_hours'] = f"{difference_hours:02d}H {difference_mins:02d}M {difference_secs:02d}S"
                # print(f"{difference_hours:02d} H {difference_mins:02d} M {difference_secs:02d} S")
            else:
                temp['work_hours'] = '-'
                message = 'Inconsistent data'
            if message:
                temp['message'] = message
            else:
                temp['message'] = ''
            # data goes here
            data.append(temp.copy())
            temp = {}
            message = None

    sql = '''
        select id, firstname, lastname from staff
    '''
    cur.execute(sql)
    stafflist = cur.fetchall()
    return render_template('timereport.html', stafflist=stafflist, data=data, menuitems=get_menu(), staff=staff, message=message)

@app.route('/lookup_original', methods=['GET', 'POST'])
def lookup_original():
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
                att_date, att_time from original_data where staff = ?
                order by id desc
            '''
            cur.execute(sql, (staff['id'],))
            data = cur.fetchall()                

    sql = '''
        select id, firstname, lastname from staff
    '''
    cur.execute(sql)
    stafflist = cur.fetchall()
    return render_template('original_data.html', stafflist=stafflist, data=data, menuitems=get_menu(), staff=staff)
