drop table if exists importdata;

-- att_type: 1=Fingerprint (F), 
-- att_dir: 0=Check-In or 1=Check-Out
-- att_status: 0=Failed or not_0=Success

create table importdata (
    id integer primary key autoincrement,
    fileid integer not null references fileuploads (id),
    staff integer not null,
    att_date text not null,
    att_time text not null,
    att_type varchar(1) not null default 'F',
    att_dir int not null,
    att_status int not null default 0,
    valid boolean
);
