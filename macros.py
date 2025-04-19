''' This module defines security filters for jinja templates '''

__all__ = ["ADMIN", "HR_MANAGER", "DATA_MANAGER", 
           "USER_MANAGER", "to_date", "nl2br", "isadmin",
           "ishrmgr", "isdatamgr", "isusermgr", "hasauth"]
__author__ = "Andrew Mathenge"
__version__ = 0.1


from app import app
from datetime import datetime
#
# the following are the roles
# 1 = admin (administrator, super user)
# 2 = hrmgr (human resources manager) can run reports - and extract/save and download reports
#     can also modify records (add and change attendance data)
# 3 = datamgr (data manager) can upload information into the system.
# 4 = usermgr (user manager) can manage the user table (add/remove users and assign privileges
#     except the super user privilege or data manager
#
from constants import *

@app.template_filter('to_date')
def to_date(item, fmt):
    if isinstance(item, str):
        return datetime.strptime(item, '%Y-%m-%d').strftime(fmt)
    elif isinstance(item, datetime):
        return item.strftime(fmt)

    return item

@app.template_filter('nl2br')
def nl2br(item):
    if isinstance(item, str):
        return item.replace('\n','<br>')
    return item

@app.template_filter('isadmin')
def isadmin(item):
    if isinstance(item, tuple):
        return ADMIN in item
    return False

@app.template_filter('ishrmgr')
def ishrmgr(item):
    if isinstance(item, tuple):
        return HR_MANAGER in item
    return False

@app.template_filter('isdatamgr')
def isdatamgr(item):
    if isinstance(item, tuple):
        return DATA_MANAGER in item
    return False

@app.template_filter('isusermgr')
def isusermgr(item):
    if isinstance(item, tuple):
        return USER_MANAGER in item
    return False

@app.template_filter('hasauth')
def hasauth(item, check):
    # "item" and "check" are lists. The correct authorization categories are in "check"
    # if an item in "item" corresponds to an item in "check" then return True
    # example item=(3,4) and check=(2,4) --> return True
    # example item=(2,4,5) and check=(3,6) --> return False
    # example item=(1,) and check=(2,3) --> return True (because 1=admin)
    if 1 in item:
        return True
    auth = False
    for element in item:
        if element in check:
            auth = True
    return auth