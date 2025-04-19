drop table if exists manual;

create table manual (
    id integer primary key autoincrement,
    staff integer not null references staff (id),
    att_date text,
    att_time text,
    reason integer not null references reason (id),
    unique(staff, att_date, att_time)
);

drop table if exists reason;

create table reason (
    id integer primary key,
    code varchar(4) not null,
    description varchar(256) not null
);

insert into reason (id, code, description) 
    values (1, 'UCI', 'Update: Clock In'),
        (2, 'UCO', 'Update: Clock Out'),
        (3, 'UCB', 'Update: Both Clock In/Out'),
        (4, 'NCE', 'New Date Entry - Staff Unable to Clock'),
        (5, 'OOF', 'Dummy entries - Staff working out of office'),
        (6, 'MAN', 'Manual Attendance copied to system');