-- foreign key constraint. need to drop this first.
drop table if exists otp;
drop table if exists users;

CREATE TABLE users (
    id integer primary key,
    firstname varchar(32) not null, 
    lastname varchar(32) not null,
    email varchar(128) not null,
    password varchar(256) not null,
    phone varchar(32) not null,
    auth varchar(8) not null default '6',
    passauth boolean not null default 1,    -- should we use password auth?
    tfaauth boolean not null default 1,     -- should we use 2FA (sms + email)
    locked boolean not null default 0,
    lastlogin datetime not null default current_timestamp
);

drop table if exists otp;

create table otp (
    id integer primary key,
    userid integer not null references users (id),
    otp varchar(6) not null,
    otp_time datetime not null,
    valid boolean not null default 0
);

-- add some sample data (assume we are running this from application home)

.read sql/sampledata.sql
