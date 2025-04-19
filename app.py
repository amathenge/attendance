from flask import Flask, render_template, url_for, g, request, redirect, Blueprint, session, send_file
from database import get_db
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import math
import os
import re
from cleanup import cleanup_import
from auth.auth import auth

app = Flask(__name__)
app.register_blueprint(auth, url_prefix="/auth")
app.config['SECRET_KEY'] = os.urandom(24)
upload_folder = 'files'
app.config['UPLOAD_FOLDER'] = upload_folder
report_folder = 'reports'
app.config['REPORT_FOLDER'] = report_folder
# max file size to upload is 10 MB
app.config['MAX_CONTENT_PATH'] = 10 * 1024 * 1024

from macros import *

@app.teardown_appcontext
def close_db(error):
    db = g.pop('attendance_db', None)
    if db:
        db.close()

def logged_in():
    if 'user' not in session or not session['user']['otp']:
        return False

    return True


def n10(item):
    if int(item[-1]) in (0, 1, 2):
        return f"{item[0]}0"
    elif int(item[-1]) in (3, 4, 5, 6, 7):
        return f"{item[0]}5"
    else:
        return f"{int(item[0])+1}0"

@app.route('/')
def home():
    if not logged_in():
        return redirect(url_for('auth.login'))
    
    now = datetime.now()

    db = get_db()
    cur = db.cursor()
    # elapsed_days is the days since 'now' when the report is run - so to get a 
    # week old report, get only 7 days.
    sql = '''
        select s.id id, s.firstname, s.lastname, a.att_date att_date, a.att_time,
        (julianday(date('now'))-julianday(date(a.att_date))) elapsed_days
        from attendance a left join staff s on a.staff = s.id
        where (julianday(date('now'))-julianday(date(a.att_date))) < 10
        and a.att_date not in (select distinct(att_date) from manual where staff = s.id)
        union
        select d.id id, d.firstname, d.lastname, c.att_date att_date, c.att_time,
        (julianday(date('now'))-julianday(date(c.att_date))) elapsed_days
        from manual c left join staff d on c.staff = d.id
        where (julianday(date('now'))-julianday(date(c.att_date))) < 10
        order by att_date desc, id asc
    '''
    cur.execute(sql)
    data = cur.fetchall()
    if len(data) == 0:
        data = None
    return render_template('index.html', data=data)


@app.route('/lookup', methods=['GET', 'POST'])
def lookup():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, DATA_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

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
            sql = '''
                select id, att_date, att_time, 0 as manual_flag
                from attendance where staff = ?
                and att_date not in 
                (select distinct(att_date) from manual where staff = ?)
                union
                select id, att_date, att_time, 1 as manual_flag
                from manual where staff = ?
                order by att_date desc, id asc
            '''
            # sql = '''select 
            #     case cast (strftime('%m', att_date) as integer) 
            #         when 1 then 'January'
            #         when 2 then 'February'
            #         when 3 then 'March'
            #         when 4 then 'April'
            #         when 5 then 'May'
            #         when 6 then 'June'
            #         when 7 then 'July'
            #         when 8 then 'August'
            #         when 9 then 'September'
            #         when 10 then 'October'
            #         when 11 then 'November'
            #         else 'December' 
            #     end as themonth,
            #     case cast (strftime('%w', att_date) as integer) 
            #         when 0 then 'Sunday'
            #         when 1 then 'Monday'
            #         when 2 then 'Tuesday'
            #         when 3 then 'Wednesday'
            #         when 4 then 'Thursday'
            #         when 5 then 'Friday'
            #         else 'Saturday' 
            #     end as day,
            #     strftime('%d', att_date) as daynumber,
            #     strftime('%Y', att_date) as theyear,
            #     cast (strftime('%w', att_date) as integer) as weekday,
            #     att_date, att_time, manual_flag from attendance where staff = ?
            #     order by id desc
            # '''
            cur.execute(sql, (staff['id'],staff['id'], staff['id']))
            data = cur.fetchall()                

    sql = '''
        select id, firstname, lastname from staff
    '''
    cur.execute(sql)
    stafflist = cur.fetchall()
    return render_template('lookup.html', stafflist=stafflist, data=data, staff=staff)

@app.route('/importfile', methods=['GET', 'POST'])
def importfile():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)
    
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
                    insert or ignore into attendance (staff, att_date, att_time)
                    select staff, att_date, att_time from importdata
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

    return render_template('importfile.html', message=message, status=valid, statussummary=statussummary)


@app.route('/listfiles', methods=['GET', 'POST'])
def listfiles():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)
    
    db = get_db()
    cur = db.cursor()
    sql = 'select id, filedate, filename from fileuploads order by id desc'
    cur.execute(sql)
    data= cur.fetchall()
    if len(data) == 0:
        data = None

    return render_template('listfiles.html', files=data)

@app.route('/filedelete/<fid>')
def filedelete(fid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)
    
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

    # this will take you back to the file delete page
    return redirect(request.referrer)


@app.route('/showimportdata/<fid>')
def showimportdata(fid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)
    
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
        order by f.id desc
    '''
    cur.execute(sql, (fid,))
    data = cur.fetchall()
    if len(data) == 0:
        data = None

    return render_template('showimportdata.html', data=data, filename=filename)

@app.route('/timereport', methods=['GET', 'POST'])
def timereport():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)


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
        if staff is None:
            return redirect(request.referrer)
        
        staffid = staff['id']

        # print(f"id={staffid}, {staff['fullname']}")
        # sql = 'select distinct(att_date) from attendance where staff = ? order by id desc'
        sql = '''
            select distinct(att_date), 'A' as source from attendance where staff = ?
            and att_date not in (select distinct(att_date) from manual where staff = ?)
            union
            select distinct(att_date), 'B' as source from manual where staff = ?
            order by att_date desc
        '''
        cur.execute(sql, (staffid, staffid, staffid))
        records = cur.fetchall()

        for record in records:
            temp = {'att_date': record['att_date'], 'source': record['source']}
            dayofweek = datetime.strptime(record['att_date'], '%Y-%m-%d').strftime('%A')
            temp['dayofweek'] = dayofweek
            # print(f"{record['att_date']}: ", end='')
            if temp['source'] == 'A':
                sql = 'select id, att_time from attendance where staff = ? and att_date = ? order by id asc'
            else:
                sql = 'select id, att_time from manual where staff = ? and att_date = ? order by id asc'
            cur.execute(sql, (staffid,record['att_date']))
            clocks = cur.fetchall()
            
            message = ''
            if len(clocks) == 2:
                start_time = clocks[0]['att_time']
                end_time = clocks[1]['att_time']
                temp['start_time'] = start_time
                temp['end_time'] = end_time
                # print(f"From {start_time} To {end_time} = ", end='')
            elif len(clocks) == 1:
                if (datetime.strptime(clocks[0]['att_time'], '%H:%M:%S') < datetime.strptime('10:00:00','%H:%M:%S')):
                    temp['start_time'] = clocks[0]['att_time']
                    temp['end_time'] = '-'
                else:
                    temp['start_time'] = '-'
                    temp['end_time'] = clocks[0]['att_time']
                message = 'Inconsistent data'
            else:
                temp['start_time'] = '-'
                temp['end_time'] = '-'
                message = 'Inconsistent data'

            if temp['source'] == 'B':
                if len(clocks) > 0:
                    sql = 'select code, description from reason where code = (select reason from manual where id = ?)'
                    cur.execute(sql, (clocks[0]['id'],))
                    reason = cur.fetchone()
                    if len(message) > 0:
                        message += f"\n{reason['code']}: {reason['description']}"
                    else:
                        message = f"Manual Data\n{reason['code']}: {reason['description']}"
                else:
                    if len(message) > 0:
                        message += "\nUnknown Error with Manual Table"
                    else:
                        message = "Unknown Error with Manual Table"

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
                if len(message) > 0:
                    message = 'Inconsistent data'+'\n'+message.replace('Inconsistent data', '')
                else:
                    message = 'Inconsistent data'
            if message:
                temp['message'] = message
            else:
                temp['message'] = ''
            # data goes here
            data.append(temp.copy())
            temp = {}
            message = None

        # save to database
        sql = 'delete from reports where staff = ?'
        cur.execute(sql, (staffid,))
        db.commit()
        sql = '''
            insert into reports (staff, att_date, dayofweek, start_time, end_time, work_hours, message)
            values (?, ?, ?, ?, ?, ?, ?)
        '''
        for item in data:
            cur.execute(sql, (staffid, item['att_date'], item['dayofweek'], item['start_time'], item['end_time'],
                              item['work_hours'], item['message']))
            db.commit()


    sql = '''
        select id, firstname, lastname from staff
    '''
    cur.execute(sql)
    stafflist = cur.fetchall()
    return render_template('timereport.html', stafflist=stafflist, data=data, staff=staff, message=message)

@app.route('/lookup_original', methods=['GET', 'POST'])
def lookup_original():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, DATA_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

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
    return render_template('original_data.html', stafflist=stafflist, data=data, staff=staff)

@app.route('/exportdata/<uid>', methods=['GET', 'POST'])
def exportdata(uid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    sql = '''
        select id, staff, att_date, dayofweek, start_time, end_time, work_hours, message
        from reports where staff = ?
    '''
    cur.execute(sql, (uid,))
    data = cur.fetchall()
    if len(data) == 0:
        data = None
    if data:
        sql = "select id, firstname || ' ' || lastname as fullname from staff where id = ?"
        cur.execute(sql, (uid,))
        staff = cur.fetchone()
        now = datetime.now().strftime('%d%b%Y').upper()
        sql = 'insert into reportlist (staff) values (?)'
        cur.execute(sql, (uid,))
        db.commit()
        placeholder = cur.lastrowid
        # should look for an exception here, but will just continue.
        filename = f"Attendance_{staff['fullname']}_{now}_{placeholder}" + ".csv"
        f = open(os.path.join(app.config['REPORT_FOLDER'],filename), 'w')
        for row in data:
            temp = datetime.strptime(row['att_date'],'%Y-%m-%d')
            temp = datetime.strftime(temp, '%d%b%Y').upper()
            output = str(row['id'])+','+str(row['staff'])+','+temp+','+row['dayofweek']
            output += ','+row['start_time']+','+row['end_time']+','+row['work_hours']+','+row['message']
            f.write(output+'\n')
        f.close()
        message = f"Report written to file {filename}"
        sql = 'update reportlist set filedate = ?, filename = ? where id = ?'
        cur.execute(sql, (now, filename, placeholder))
        db.commit()
    else:
        message = f"Unable to create report for staff id={uid}"

    return render_template('reportresult.html', message=message)

@app.route('/listreports')
def listreports():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    sql = 'select id, staff, filedate, filename from reportlist order by id desc'
    cur.execute(sql)
    data = cur.fetchall()
    if len(data) == 0:
        data = None
    
    return render_template('listreports.html', reports=data)


@app.route('/reportdownload/<rid>', methods=['GET', 'POST'])
def reportdownload(rid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from reportlist where id = ?'
    cur.execute(sql, (rid,))
    data = cur.fetchone()
    if data is None:
        return render_template('reportresult.html', message=f"File with id={rid} does not exist")
    if os.path.exists(os.path.join(app.config['REPORT_FOLDER'],data['filename'])):
        return send_file(os.path.join(app.config['REPORT_FOLDER'],data['filename']), as_attachment=True)

    message = f"Download of {data['filename']} completed"
    return render_template('reportresult.html', message=message)

@app.route('/reportdelete/<rid>', methods=['GET', 'POST'])
def reportdelete(rid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']
    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    sql = 'select filename from reportlist where id = ?'
    cur.execute(sql,(rid,))
    data = cur.fetchone()
    if data is None:
        # file does not exist
        return render_template('reportresult.html', message=f"File with id={rid} does not exist")
    # delete file from filesystem
    if os.path.exists(os.path.join(app.config['REPORT_FOLDER'],data['filename'])):
        os.remove(os.path.join(app.config['REPORT_FOLDER'],data['filename']))
    # delete file from entry
    sql = 'delete from reportlist where id = ?'
    cur.execute(sql, (rid,))
    db.commit()
    message = f"File {data['filename']} deleted"
    return render_template('reportresult.html', message=message)
    

@app.route('/edit_attendance', methods=['GET', 'POST'])
def edit_attendance():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    # present list of people and then a form to select the dates to edit
    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        staff = int(request.form.get('selectstaff'))
        if staff == 0:
            return redirect(request.referrer)
        sql = '''select min(id) id, staff, att_date, min(att_time) clock_in, max(att_time) clock_out,
            'A' source, NULL reason from attendance where staff = ?
            and att_date not in (select distinct(att_date) from manual where staff = ?)
            group by staff, att_date
            union
            select min(id) id, staff, att_date, min(att_time) clock_in, max(att_time) clock_out,
            'B' source, reason from manual where staff = ?
            group by staff, att_date
            order by att_date desc
        '''
        cur.execute(sql, (staff,staff, staff))
        data = cur.fetchall()
        staffname = None
        attendance = None
        if len(data) == 0:
            data = None
        else:
            # clean up data - when only one clock, it's both min() and max()
            attendance = []
            temp_row = None
            for row in data:
                temp_row = dict(row)
                if row['clock_in'] == row['clock_out']:
                    dt = datetime.strptime(row['clock_in'], '%H:%M:%S')
                    if dt <= datetime.strptime('10:00:00', '%H:%M:%S'):
                        temp_row['clock_out'] = None
                    else:
                        temp_row['clock_in'] = None
                attendance.append(temp_row.copy()) 
            sql = 'select id, firstname, lastname from staff where id = ?'
            cur.execute(sql, (staff,))
            staffname = cur.fetchone()
        return render_template('edit_attendance.html', attendance=attendance, staffname=staffname)

    sql = 'select id, firstname, lastname from staff'
    cur.execute(sql)
    data = cur.fetchall()
    return render_template('edit_selectstaff.html', staff=data)

@app.route('/edit_item/<sid>/<did>/<tid>')
def edit_item(sid, did, tid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    tablename = None
    if tid == 'A':
        tablename = 'attendance'
    else:
        tablename = 'manual'
    sql = f'''
        select id, staff, att_date, att_time from {tablename} where staff = ?
        and att_date = ?
    '''

    cur.execute(sql, (sid,did))
    # data = cur.fetchone()
    clock_in_hour = "00"
    clock_in_minute = "00"
    clock_out_hour = "00"
    clock_out_minute = "00"
    data = cur.fetchall()
    if len(data) == 0:
        data = None
    elif len(data) == 1:    # if time < 10:00AM, assume clock-in. 
        row = data[0]
        clock_in_hour = row['att_time'].split(':')[0]
        clock_in_minute = row['att_time'][row['att_time'].find(':')+1:row['att_time'].rfind(':')]
        clock_out_hour = "00"
        clock_out_minute = "00"
        if int(clock_in_hour) >= 10:
            clock_out_hour = clock_in_hour
            clock_out_minute = clock_in_minute
            clock_in_hour = "00"
            clock_in_minute = "00"
    elif len(data) == 2:
        row = data[0]
        clock_in_hour = row['att_time'].split(':')[0]
        clock_in_minute = row['att_time'][row['att_time'].find(':')+1:row['att_time'].rfind(':')]
        row = data[1]
        clock_out_hour = row['att_time'].split(':')[0]
        clock_out_minute = row['att_time'][row['att_time'].find(':')+1:row['att_time'].rfind(':')]
    else:
        clock_in_hour = "00"
        clock_in_minute = "00"
        clock_out_hour = "00"
        clock_out_minute = "00"

    staff = None
    clock_data = {
        'tablename': tablename,
        'clock_in_hour': clock_in_hour,
        'clock_in_minute': n10(clock_in_minute),
        'clock_out_hour': clock_out_hour,
        'clock_out_minute': n10(clock_out_minute)
    }
    if data:
        sql = 'select id, firstname, lastname from staff where id = ?'
        cur.execute(sql, (sid,))
        staff = cur.fetchone()
    sql = 'select id, code, description from reason'
    cur.execute(sql)
    reasons = cur.fetchall()

    return render_template('edit_item.html', att_record=data, staff=staff, clock_data=clock_data, reasons=reasons)


@app.route('/save_item', methods=['GET', 'POST'])
def save_item():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    if request.method == "POST":
        if request.form['submit'] == "cancel":
            return redirect(url_for('edit_attendance'))

        # collect form data
        staff = int(request.form['staff'])
        att_date = request.form['att_date']
        # att_date looks like DDMMMYYYY, need to fix it to YYYY-MM-DD
        att_date = datetime.strptime(att_date, '%d%b%Y').strftime('%Y-%m-%d')
        clock_in_hour = request.form.get('clock_in_hour')
        clock_in_minute = request.form.get('clock_in_minute')
        clock_out_hour = request.form.get('clock_out_hour')
        clock_out_minute = request.form.get('clock_out_minute')
        reason = request.form.get('reason')
        tablename = request.form['tablename']

        clock_in = f"{clock_in_hour}:{clock_in_minute}:00"
        clock_out = f"{clock_out_hour}:{clock_out_minute}:00"

        savedata = {
            'staff': staff,
            'att_date': att_date,
            'clock_in': clock_in,
            'clock_out': clock_out,
            'reason': reason,
            'tablename': tablename
        }

        db = get_db()
        cur = db.cursor()
        sql = 'select id, firstname, lastname from staff where id = ?'
        cur.execute(sql, (staff,))
        data = cur.fetchone()
        staff =  {
            'id': staff,
            'firstname': data['firstname'],
            'lastname': data['lastname']
        }

        if request.form['submit'] == 'delete':
            return render_template('delete_confirm.html', att_record=savedata, staff=staff)


        return render_template('save_confirm.html', att_record=savedata, staff=staff)
    
    # if this didn't come from a POST, send it back to where it came from
    return redirect(request.referrer)

@app.route('/save_attendance', methods=['GET', 'POST'])
def save_attendance():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        if 'cancel' not in request.form['submit']:
            staff = int(request.form['staff'])
            att_date = request.form['att_date']
            clock_in = request.form['clock_in']
            clock_out = request.form['clock_out']
            reason = request.form['reason']
            # tablename = request.form['tablename']
            # sql = f"delete from {tablename} where att_date = ?"
            sql = f"delete from manual where att_date = ? and staff = ?"
            cur.execute(sql, (att_date, staff))
            db.commit()
            # all changes should go to the manual table.
            sql = f'''
                insert into manual (staff, att_date, att_time, reason)
                values (?, ?, ?, ?)
            '''
            cur.execute(sql, (staff, att_date, clock_in, reason))
            db.commit()
            cur.execute(sql, (staff, att_date, clock_out, reason))
            db.commit()
        
    return redirect(url_for('home'))

@app.route('/add_new_record/<sid>', methods=['GET', 'POST'])
def add_new_record(sid):
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    # figure out the gaps and only give an option to add where there's a gap.
    # otherwise update/overwrite existing records.
    db = get_db()
    cur = db.cursor()
    # missing dates, including Sundays, from the earliest date, to today.
    # also check the manual table...
    sql = '''
        select min(id) mid, att_date from attendance where staff = ? group by att_date
        union
        select min(id) mid, att_date from manual where staff = ? group by att_date
        order by att_date asc
    '''
    cur.execute(sql, (sid,sid))
    data = cur.fetchall()
    if len(data) == 0:
        data = None

    temp = []
    date_collection = []
    missing_dates = []
    if data:
        for row in data:
            temp.append(row['att_date'][:])

        for item in temp:
            date_collection.append(datetime.strptime(item, '%Y-%m-%d'))

        
        first_date = date_collection[0]
        # can possibly allow to go to the current date...
        # last_date = datetime.now()
        last_date = date_collection[len(date_collection)-1]

        cur_date = first_date + timedelta(days=1)
        while cur_date < last_date:
            if cur_date not in date_collection:
                missing_dates.append({'att_date': cur_date})

            cur_date = cur_date + timedelta(days=1)

    sql = 'select id, firstname, lastname from staff where id = ?'
    cur.execute(sql, (sid,))
    staff = cur.fetchone()
    if staff is None:
        return redirect(request.referrer)

    sql = 'select id, code, description from reason'
    cur.execute(sql)
    reasons = cur.fetchall()
    if len(reasons) == 0:
        reasons = None

    return render_template('add_new_clock.html', missing_dates=missing_dates, staff=staff, reasons=reasons)
        
@app.route('/add_clock', methods=['GET', 'POST'])
def add_clock():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        if 'cancel' not in request.form['submit']:
            sid = int(request.form['staff'])
            att_date = request.form.get('att_date')
            clock_in_hour = request.form.get('clock_in_hour')
            clock_in_minute = request.form.get('clock_in_minute')
            clock_out_hour = request.form.get('clock_out_hour')
            clock_out_minute = request.form.get('clock_out_minute')
            reason = request.form.get('reason')

            sql = 'select id, firstname, lastname from staff where id = ?'
            cur.execute(sql, (sid,))
            staff = cur.fetchone()

            clock_in = f"{clock_in_hour}:{clock_in_minute}:00"
            clock_out = f"{clock_out_hour}:{clock_out_minute}:00"

            savedata = {
                'staff': staff['id'],
                'att_date': att_date,
                'clock_in': clock_in,
                'clock_out': clock_out,
                'reason': reason
            }

            return render_template('add_clock_confirm.html', att_record=savedata, staff=staff)
        else:
            return redirect(url_for('edit_attendance'))
    
    return redirect(url_for('edit_attendance'))

@app.route('/save_clocks', methods=['GET', 'POST'])
def save_clocks():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        if 'cancel' not in request.form['submit']:
            staff = request.form['staff']
            att_date = request.form['att_date']
            clock_in = request.form['clock_in']
            clock_out = request.form['clock_out']
            reason = request.form['reason']

            sql = '''
                insert into manual (staff, att_date, att_time, reason)
                values (?, ?, ?, ?)
            '''

            cur.execute(sql, (staff, att_date, clock_in, reason))
            db.commit()
            cur.execute(sql, (staff, att_date, clock_out, reason))
            db.commit()

    return redirect(url_for('home'))

@app.route('/useradmin', methods=['GET', 'POST'])
def useradmin():
    # db = get_db()
    # cur = db.cursor()

    # if request.method == "POST":
    #     pass

    return render_template('under_construction.html', page="User Admin Module")


@app.route('/staffadmin', methods=['GET', 'POST'])
def staffadmin():
    # db = get_db()
    # cur = db.cursor()

    # if request.method == "POST":
    #     pass

    return render_template('under_construction.html', page="Staff Admin Module")

@app.route('/clockreports', methods=['GET', 'POST'])
def clockreports():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    sql = 'select id, firstname, lastname from staff'
    cur.execute(sql)
    stafflist = cur.fetchall()

    if request.method == "POST":
        staff = int(request.form.get('selectstaff'))
        if staff == 0:
            return redirect(request.referrer)

        # get all records from ATTENDANCE which have an entry in MANUAL
        # get all records in MANUAL that do not exist in ATTENDANCE
        
    return render_template('clockreport.html', stafflist=stafflist)

@app.route('/delete_attendance', methods=['GET', 'POST'])
def delete_attendance():
    if not logged_in():
        return redirect(url_for('auth.login'))

    auth = (DATA_MANAGER, HR_MANAGER, ADMIN)
    user = session['user']

    if not hasauth(user['auth'], auth):
        return redirect(request.referrer)

    db = get_db()
    cur = db.cursor()
    if request.method == "POST":
        if 'cancel' not in request.form['submit']:
            staff = int(request.form['staff'])
            att_date = request.form['att_date']
            clock_in = request.form['clock_in']
            clock_out = request.form['clock_out']
            reason = request.form['reason']
            # tablename = request.form['tablename']
            # sql = f"delete from {tablename} where att_date = ?"
            sql = f"delete from manual where att_date = ? and staff = ?"
            cur.execute(sql, (att_date, staff))
            db.commit()
            sql = 'select id, code, description from reason where code = ?'
            cur.execute(sql, (reason,))
            reason_data = cur.fetchone()
            sql = 'select id, firstname, lastname from staff where id = ?'
            cur.execute(sql, (staff,))
            staff_data = cur.fetchone()
            
            att_data = {
                'id': staff,
                'staff_name': f'{staff_data['firstname']} {staff_data['lastname']}',
                'att_date': att_date,
                'clock_in': clock_in,
                'clock_out': clock_out,
                'reason_code': reason,
                'reason_description': reason_data['description'],
                'table': 'manual'
            }
            message = f'Successfully deleted record for date {att_date}'
            
            return render_template('deleteresult.html', att_data=att_data, message=message)
                                   
        
    return redirect(url_for('home'))