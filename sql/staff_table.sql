drop table if exists staff;

create table staff (
    id integer not null,
    firstname varchar(32) not null,
    lastname varchar(32) not null
);

.read sql/staff_data.sql