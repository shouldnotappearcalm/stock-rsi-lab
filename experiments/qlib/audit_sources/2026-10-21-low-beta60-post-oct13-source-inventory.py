"""Read-only post-Oct13 raw-cache inventory; no strategy or portfolio imports."""
import argparse,hashlib,json
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path

SOURCES=('low-risk-raw-account-data-20261017','szse-value-raw-full-20261017','reversal-raw-full-20261017')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def core(rows):
    return [[r['date'],r['code'],*[str(Decimal(r[k]).normalize()) if r[k] else ''
        for k in ('open','high','low','close','preclose','volume','amount')],r['tradestatus'],r['isST']] for r in rows]


def inventory(base):
    original=base/'low-beta60-raw-extension-20261021';m=read(original/'manifest.json')
    assert sha(original/'manifest.json')=='10f645719228d50c439e166bbfe65959b5ff517668c2ecc8ffc4fca4e1680ea7'
    sessions=read(original/'calendar.json')['sessions'];assert len(sessions)==671
    manifests={n:read(base/n/'manifest.json') for n in SOURCES};calendars={n:read(base/n/'calendar.json')['sessions'] for n in SOURCES}
    for n in SOURCES:assert calendars[n][:671]==sessions and calendars[n][-1]=='2026-10-16'
    items={};conflicts=[];post_events={}
    for code,h in sorted(m['per_code_sha256'].items()):
        f=original/'codes'/(code+'.json');assert sha(f)==h;old=read(f);choices=[]
        for n in SOURCES:
            if code not in manifests[n]['per_code_sha256']:continue
            f=base/n/'codes'/(code+'.json');assert sha(f)==manifests[n]['per_code_sha256'][code];packet=read(f)
            assert packet['instrument']==code and packet['window']==['2023-12-29','2026-10-16']
            assert [r['date'] for r in packet['bars']]==calendars[n]
            matched=core([r for r in packet['bars'] if r['date']<='2026-10-13'])==core(old['bars'])
            matched=matched and all([r for r in packet[field] if r['dividOperateDate']<='2026-10-13']==old[field]
                for field in ('distributions','adjustments'))
            if not matched:conflicts.append([code,n]);continue
            tail=[r for r in packet['bars'] if r['date']>'2026-10-13']
            assert [r['date'] for r in tail]==['2026-10-14','2026-10-15','2026-10-16']
            choices.append({'source_directory':n,'packet_sha256':sha(f),'tail_dates':[r['date'] for r in tail],
                'tail_core_sha256':hashlib.sha256(json.dumps(core(tail),separators=(',',':')).encode()).hexdigest()})
            for row in packet['distributions']:
                if row['dividOperateDate']>'2026-10-13':
                    key=code+'|'+row['dividOperateDate']
                    if key in post_events:assert row==post_events[key]['vendor_row']
                    else:post_events[key]={'instrument':code,'ex_day':row['dividOperateDate'],'vendor_row':row}
        if len({c['tail_core_sha256'] for c in choices})>1:conflicts.append([code,'TAIL_CORE_CONFLICT'])
        route=choices[0] if choices else None
        items[code]={'original_packet_sha256':h,'choices':choices,'priority_route':route,
            'new_daily_query_start_calendar_day':'2026-10-17' if route else '2026-10-14',
            'new_daily_query_end':'2026-10-20'}
    return {'status':'AUTHENTICATED_PARTIAL_RAW_CACHE_TAIL_INVENTORY_NO_CAPTURE_OR_ROI',
        'audit_code_sha256':sha(__file__),'original_manifest_sha256':sha(original/'manifest.json'),
        'unconditional_interim_observation_end':'2026-10-20','required_names':79,
        'source_priority':list(SOURCES),'source_manifest_sha256':{n:sha(base/n/'manifest.json') for n in SOURCES},
        'source_calendar_sha256':{n:sha(base/n/'calendar.json') for n in SOURCES},
        'cached_three_day_tail_names':sum(i['priority_route'] is not None for i in items.values()),
        'uncached_three_day_tail_names':sum(i['priority_route'] is None for i in items.values()),
        'all_names_still_need_later_daily_data':79,'conflicts':conflicts,'items':items,
        'cached_post_Oct13_dividend_rows':list(post_events.values()),
        'calendar_after_Oct16_not_invented':True,'request_start_is_calendar_day_not_assumed_trading_day':True,
        'new_network_requests':0,'source_inputs_modified':False,'portfolio_returns_computed':False,
        'historical_arrival_verified':False,'full_requested_October_complete':False,'objective_achieved':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=inventory(a.source_root)
    with a.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print('cached tail names',result['cached_three_day_tail_names'],'uncached',result['uncached_three_day_tail_names'],'conflicts',len(result['conflicts']))
