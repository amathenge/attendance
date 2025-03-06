drop table if exists fileuploads;

create table fileuploads (
    id integer primary key autoincrement,
    filedate datetime not null,
    filename varchar(64) not null,
    totallines integer,
    validlines integer
);
