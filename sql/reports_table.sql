drop table if exists reports;

create table reports (
    id integer primary key autoincrement,
    staff integer references staff (id) not null,
    att_date varchar(32),
    dayofweek varchar(32),
    start_time varchar(32),
    end_time varchar(32),
    work_hours varchar(32),
    message varchar(64)
);

drop table if exists reportlist;

create table reportlist (
    id integer primary key autoincrement,
    staff integer references staff (id) not null,
    filedate varchar(32),
    filename varchar(64)
);


