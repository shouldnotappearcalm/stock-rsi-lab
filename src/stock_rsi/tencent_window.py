"""Date-only prefix quarantine; original kept rows remain byte-identical."""
from datetime import date
import hashlib
import json
import re
from stock_rsi.tencent_history import JsonSlices,START,END,need

def digest(b):return hashlib.sha256(b).hexdigest()


def source_rows(body,code):
    need(re.fullmatch(r'(?:SH|SZ)[0-9]{6}',code) is not None,'explicit issuer identifier')
    s=JsonSlices(body);need(s.path(('code',))==b'0','successful historical envelope')
    return s.items(s.path(('data',code.lower(),'day')))


def entry(raw,index,previous,sessions):
    parts=JsonSlices.items(raw);need(parts and parts[0].startswith(b'"'),'date string before any other row value');day=json.loads(parts[0])
    need(type(day) is str and date.fromisoformat(day).isoformat()==day,'canonical source date')
    need(previous is None or day>previous,'all source dates strictly increasing')
    need(day<=END,'later/future row cannot enter window adapter')
    classification='EARLIER_QUARANTINE' if day<START else 'KEEP'
    need(classification=='EARLIER_QUARANTINE' or day in sessions,'in-window row must be an explicit session')
    return {'source_index':index,'date':day,'row_sha256':digest(raw),'classification':classification}


def prepare(body,code,sessions):
    records=[]
    try:
        need(sessions==sorted(set(sessions)) and all(START<=d<=END and date.fromisoformat(d).isoformat()==d for d in sessions),'fixed explicit window sessions')
        rows=source_rows(body,code);kept=[];previous=None
        for index,raw in enumerate(rows):
            item=entry(raw,index,previous,sessions);previous=item['date'];records.append(item)
            if item['classification']=='KEEP':kept.append(raw)
        prepared=b'{"code":0,"data":{'+json.dumps(code.lower()).encode()+b':{"day":['+b','.join(kept)+b']}}}'
        receipt={'instrument':code,'window':[START,END],'original_body_sha256':digest(body),'prepared_body_sha256':digest(prepared),
            'source_rows':len(rows),'kept_count':len(kept),'earlier_count':len(rows)-len(kept),'records':records,
            'numeric_or_ignored_values_decoded':False,'kept_row_bytes_modified':False,'source_or_account_admitted':False}
        return prepared,receipt
    except BaseException as exc:
        exc.window_records=records;exc.window_code=code;exc.window_failed_index=len(records)
        raise


def verify_records(body,code,sessions,records,complete):
    if not records and not complete:return
    rows=source_rows(body,code);need(len(records)<=len(rows) and (not complete or len(records)==len(rows)),'all recorded source indices covered')
    previous=None
    for i,want in enumerate(records):
        actual=entry(rows[i],i,previous,sessions);need(actual==want,'exact date/hash/classification record');previous=actual['date']
