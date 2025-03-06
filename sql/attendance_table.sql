drop table if exists attendance;

-- att_type: 1=Fingerprint (F), 
-- att_dir: 0=Check-In or 1=Check-Out
-- att_status: 0=Failed or not_0=Success

create table attendance (
    id integer primary key autoincrement,
    staff integer not null,
    att_date text not null,
    att_time text not null,
    att_type varchar(1) not null default 'F',
    att_dir int not null,
    att_status int not null default 0,
    unique (staff, att_date, att_time)
);

