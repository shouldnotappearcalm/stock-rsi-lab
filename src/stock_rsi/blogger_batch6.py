"""Calendar targets for the scheduled execution session, independent of quotes."""
from bisect import bisect_left
from datetime import date

CODE = 'SH510050'
NAMES = ('monthturn4', 'halloween6')


def evaluate(name, calendar, session):
    if name not in NAMES or type(session) is not date:
        raise ValueError('declared strategy and execution date required')
    i = bisect_left(calendar, session)
    if not 0 < i < len(calendar)-1 or calendar[i] != session:
        raise ValueError('actual session and adjacent calendar dates required')
    month = session.replace(day=1)
    rank = i - bisect_left(calendar, month) + 1
    last = calendar[i+1].replace(day=1) != month
    target = (last or rank <= 3) if name == 'monthturn4' else (session.month >= 11 or session.month <= 4)
    return {'leader': CODE if target else None, 'details': {'month_session_rank': rank, 'last_session_of_month': last}}
