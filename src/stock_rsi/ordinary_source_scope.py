"""Fail closed on account dependencies on a nonordinary source state.

The caller supplies every owned/pending share, pending order and decision
price dependency. This evaluator audit must not enter decision snapshots.
Original source rows remain unchanged; no rejected minute tape is admitted.
"""
from stock_rsi.lifecycle_source_rows import source_rows_on


def ordinary_source_rows_on(bars, day, required, lifecycles):
    required = set(required)
    rows, exceptions = source_rows_on(bars, day, required, lifecycles)
    ordinary = {}
    for code, row in rows.items():
        state = row.get('isST')
        if type(state) is not str or state not in ('0', '1'):
            raise ValueError('explicit ordinary/nonordinary source state required')
        if state == '0':
            ordinary[code] = row
            continue
        if code in required:
            raise ValueError('required nonordinary source state: ' + code + ' ' + day.isoformat())
        exceptions.append({
            'instrument': code, 'session': day.isoformat(),
            'reason': 'NONORDINARY_SOURCE_NOT_REQUIRED_BY_ACCOUNT',
            'original_row_present': True, 'source_isST': '1',
            'required_by_account': False, 'synthetic_price_created': False,
        })
    return ordinary, exceptions
