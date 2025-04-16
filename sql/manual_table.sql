drop table if exists manual;

create table manual (
    id integer primary key autoincrement,
    staff integer not null references staff (id),
    att_date text,
    att_time text,
    manual boolean not null default 1,
    notes text not NULL
);