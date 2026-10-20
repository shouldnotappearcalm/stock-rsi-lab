"""Source-only pre2026 minute requirements and restart-safe bounded capture."""
from datetime import date
import json
import re
from pathlib import Path
from scripts.fundamental_query_journal import digest,file_sha
from stock_rsi.lifecycle_source_rows import source_rows_on


def prefix_minute_requirements(targets,bars,lifecycles):
    active=[];skipped=[];seen=set()
    for day,target in sorted(targets.items()):
        parsed=date.fromisoformat(day)
        if parsed.isoformat()!=day or not '2024-01-02'<=day<='2025-12-31' or not target['as_of']<day:
            raise ValueError('frozen pre2026 source request clock required')
        seen.update(target['weights'])
        if not seen<=set(bars):raise ValueError('source universe excludes frozen target')
        rows,exceptions=source_rows_on({c:bars[c] for c in seen},parsed,target['weights'],
            {c:p for c,p in lifecycles.items() if c in seen})
        absent={r['instrument']:r for r in exceptions}
        for code in sorted(seen):
            if code in absent:
                skipped.append({'instrument':code,'day':day,'reason':absent[code]['reason'],
                    'primary_document_sha256':absent[code]['primary_document_sha256'],
                    'actual_inventory_proven_zero':False,'synthetic_price_created':False})
            elif rows[code]['tradestatus']=='0':
                skipped.append({'instrument':code,'day':day,'reason':'SOURCE_HALT',
                    'actual_inventory_proven_zero':False,'synthetic_price_created':False})
            elif rows[code]['tradestatus']=='1':active.append([code,day])
            else:raise ValueError('unknown source session trading state')
    return active,skipped


def query_minute_packet(journal,code,day,host,fetch):
    if journal.max_attempts!=1:raise ValueError("minute query requires exactly one reserved attempt")
    parsed=date.fromisoformat(day)
    if (parsed.isoformat()!=day or not '2024-01-02'<=day<='2025-12-31'
            or not re.fullmatch('(SH|SZ)[0-9]{6}',code)):
        raise ValueError('canonical pre2026 minute source request required')
    identity={'method':'minutes.history','instrument':code,'requested_day':day,'host':host,'include_raw':True}
    folder=journal.root/'queries'/digest(identity)
    try:
        payload,receipt=journal.query(identity,lambda:(['response'],[fetch()]))
    except ValueError as exc:
        if str(exc)!='source query attempts exhausted: '+digest(identity):raise
        if json.loads((folder/'request.json').read_text())!=identity:raise ValueError('minute request identity changed')
        response=folder/'response-1.json';reservation=folder/'reserved-1.json'
        if not response.exists() or not reservation.exists():raise
        record=json.loads(response.read_text())
        reserved=json.loads(reservation.read_text())
        if (reserved['identity_sha256']!=digest(identity) or reserved['attempt']!=1
                or record['status']!='SOURCE_ERROR' or record['identity_sha256']!=digest(identity)
                or record['reservation_sha256']!=file_sha(reservation)):raise
        return {'instrument':code,'requested_day':day,'status':'REQUEST_FAILED',
            'error_type':record['error_type'],'error':record['error'],
            'query_response_sha256':file_sha(response),'query_reservation_sha256':file_sha(reservation)}
    if payload['fields']!=['response'] or len(payload['rows'])!=1:raise ValueError('minute query envelope changed')
    return {'instrument':code,'requested_day':day,'status':'RESPONSE_CAPTURED',
        'response':payload['rows'][0],'observed_at':payload['captured_at_utc'],
        'query_response_sha256':receipt['response_sha256'],'query_reservation_sha256':receipt['reserved_sha256']}


def authenticate_reused_minutes(base,index,active):
    authenticated={}
    for code,day in active:
        name=code+'-'+day+'.json'
        if name not in index:continue
        origin=index[name];path=Path(base)/origin['root']/'sessions'/name
        if file_sha(path)!=origin['sha256']:raise ValueError('reused minute source bytes changed')
        packet=json.loads(path.read_text());record=packet.get('methods',{}).get('minutes.history',packet)
        if (packet['instrument']!=code or packet['requested_day']!=day
                or record['status'] not in ('RESPONSE_CAPTURED','REQUEST_FAILED')):
            raise ValueError('reused minute source identity or method changed')
        authenticated[name]=origin
    return authenticated
