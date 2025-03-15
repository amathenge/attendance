import sqlite3
from datetime import datetime

db = sqlite3.connect('attendance.db')
db.row_factory = sqlite3.Row
cur = db.cursor()

sql = "select id, firstname || ' ' || lastname as fullname from staff"
cur.execute(sql)
staff = cur.fetchall()

for staff_record in staff:
    staffid = staff_record['id']

    print(f"id={staffid}, {staff_record['fullname']}")
    sql = 'select distinct(att_date) from attendance where staff = ? order by id desc'
    cur.execute(sql, (staffid,))
    records = cur.fetchall()

    for record in records:
        print(f"{record['att_date']}: ", end='')
        sql = 'select id, att_time from attendance where staff = ? and att_date = ? order by id asc'
        cur.execute(sql, (staffid,record['att_date']))
        clocks = cur.fetchall()
        if len(clocks) == 2:
            start_time = clocks[0]['att_time']
            end_time = clocks[1]['att_time']
            print(f"From {start_time} To {end_time} = ", end='')
        else:
            print(f"Inconsistent clocking data - Clocks = {len(clocks)}")

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
            print(f"{difference_hours:02d} H {difference_mins:02d} M {difference_secs:02d} S")

    print('-'*60)
    print()

db.close()