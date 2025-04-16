from app import app
from datetime import datetime

@app.template_filter('to_date')
def to_date(item, fmt):
    if isinstance(item, str):
        return datetime.strptime(item, '%Y-%m-%d').strftime(fmt)
    elif isinstance(item, datetime):
        return item.strftime(item, fmt)

    return item

