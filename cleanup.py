# each person should only have two rows for a single day in the database.
# the start time of work
# the end time of work
#
# for each person, collect all the dates the person was at work.
# select distinct(att_date) att_date from attendance where staff = ?
# 
# for each date get all the rows from the attendance table
# select id, staff, att_date, att_time from attendance where att_date = ?
#
# if there are more than 2 rows, keep the max(id) and the min(id) - this represents
# the earliest clock for that day and the last clock for the day
# select max(id) mx, min(id) mi from attendance where staff = ? and att_date = ?
# delete from attendance where staff = ? and att_date = ? and id not in (mx, mi);
# 
# check that the mx and mi are at least 1 hour apart
# select d1 from attendance where id = mx;
# select d2 from attendance where id = mi
# select (strftime('%s', d1) - strftime('%s', d2))/(60*60);
# result of the query above should give an answer. If that number is less than 1, 
# delete mx -> the max(id) since the person did not stay longer than 1 hour.

from database import get_db

def cleanup_import():
    db = get_db()
    cur = db.cursor()

    # staff list
    sql = "select id, firstname || ' ' || lastname fullname from staff"
    # the script below will run for each person.
    cur.execute(sql)
    allstaff = cur.fetchall()

    for staffmember in allstaff:
        staffid = staffmember['id']
        staffname = staffmember['fullname']

        sql = 'select distinct(att_date) from attendance where staff = ?'
        cur.execute(sql, (staffid,))
        data = cur.fetchall()
        # print(f'dates that id={staffid} name={staffname} clocked')
        # for row in data:
        #     print(row['att_date'])

        # save this for later
        dates_clocked = data.copy()

        # get the rows clocked in for each of the dates.
        sql = 'select att_date, count(att_date) c_dates from attendance where staff = ? group by att_date'
        cur.execute(sql, (staffid,))
        data = cur.fetchall()
        # print('Number of clocks for each date')
        # for row in data:
        #     print(f"on {row['att_date']} clocks={row['c_dates']}")

        # get the id's in attendance for each of the dates clocked.
        clocking_data = {}
        for row in dates_clocked:
            sql = 'select id, att_time from attendance where staff = ? and att_date = ?'
            cur.execute(sql, (staffid, row['att_date']))
            data = cur.fetchall()
            temp = []
            for item in data:
                temp.append([item['id'], item['att_time']])
            clocking_data[row['att_date']] = temp.copy()

        # print out clocking data
        # for item in clocking_data.keys():
        #     clocks = clocking_data[item]
        #     print(f"On {item}: ",end='')
        #     for results in clocks:
        #         print(f"[{results[0]},{results[1]}]", end=' ')
        #     print()

        # delete except the first and last. In a list this is item [0] and item [-1]
        todelete = []
        deleteids = []
        for item in clocking_data.keys():
            clocks = []
            clocks = clocking_data[item]
            if len(clocks) > 2:
                todelete.append(clocks[1:-1].copy())
                temp = [clocks[0],clocks[-1]]
                clocking_data[item] = temp.copy()
                del temp
        # print('Items to be deleted')
        if len(todelete) > 0:
            for item in todelete:
                itemlen = len(item)
                # print(f"Items={itemlen}: ", end='')
                for counter in range(itemlen):
                    deleteids.append(item[counter][0])
                #     print(f"{item[counter]}, ", end='')
                # print()
            # print(f'New clocking list for id={staffid}, name={staffname}')
            for item in clocking_data.keys():
                clocks = clocking_data[item]
                # print(f"On {item}: ", end='')
                # for results in clocks:
                #     print(f"[{results[0]},{results[1]}]", end=' ')
                # print()
            # print(f"The following id's will be deleted")
            # for counter in range(len(deleteids)):
            #     print(f"{deleteids[counter]},", end='')
            # print()
            sql = f'delete from attendance where id in {tuple(deleteids)}'
            # a single element tuple will have a comma at the end.
            sql = sql.replace(',)',')')
            # print('The following sql will run')
            # print(sql)
            # production - run the sql
            cur.execute(sql)
            db.commit()
        # else:
        #     print(f'No deletions for id={staffid}, name={staffname}')


    db.close()