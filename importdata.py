import sqlite3

conn = sqlite3.connect('attendance.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

f = open('attendance.dat', 'r')
sql = '''
    insert into attendance (staff, att_date, att_time, att_type, att_dir, att_status) 
    values (?, ?, ?, ?, ?, ?)    
'''
sqlValues = []
for line in f:
    sqlValues.clear()
    data = line.strip()
    if len(data) > 0:
        data = data.split()
        sqlValues.append(int(data[0]))
        sqlValues.append(data[1])
        sqlValues.append(data[2])
        sqlValues.append(int(data[3]))
        sqlValues.append(int(data[4]))
        sqlValues.append(int(data[5]))

        cur.execute(sql, sqlValues)
        conn.commit()

f.close()
