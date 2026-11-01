"""Thirteen bounded pre2026 source identities, explicit derived engineering view."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import struct
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FUNDS = ('SH518880','SZ159915','SH510050','SH510300','SH510500')
INDEXES = ('SH000016','SH000300','SH000905')
START, END = '2022-12-01', '2025-12-31'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def inventory(root):
    root=Path(root)
    if any(p.is_symlink() for p in root.rglob('*')): raise ValueError('no symlink inputs')
    return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}


def write(path,value):
    with Path(path).open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def url(code,mode):
    if code not in FUNDS+INDEXES or mode not in ('raw','hfq') or code in INDEXES and mode!='raw':raise ValueError('one of13 registered source identities required')
    params={'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt':'101','fqt':'0' if mode=='raw' else '2','beg':START.replace('-',''),'end':END.replace('-',''),
            'secid':('1.' if code.startswith('SH') else '0.')+code[2:]}
    return 'https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params)


def parse(body,code,mode,sessions):
    url(code,mode);d=body.get('data')
    if body.get('rc')!=0 or not isinstance(d,dict) or d.get('code')!=code[2:] or d.get('market')!=(1 if code.startswith('SH') else 0):raise ValueError('source security identity mismatch')
    result=[]
    for row in d.get('klines') or []:
        f=row.split(',')
        if len(f)!=11:raise ValueError('unexpected historical field count')
        day=f[0];op,close,high,low,volume,amount=map(Decimal,f[1:7]);delta=Decimal(f[9])
        if (not START<=day<=END or any(not v.is_finite() for v in (op,close,high,low,volume,amount,delta))
                or min(op,close,high,low,volume,amount)<=0 or low>min(op,close) or high<max(op,close)):
            raise ValueError('invalid date or complete positive OHLC/activity required')
        if mode=='raw' and code in FUNDS and any(v!=v.quantize(Decimal('.001')) for v in (op,close,high,low)):
            raise ValueError('raw ETF prices must have .001 tick')
        result.append({'date':day,'open':f[1],'close':f[2],'high':f[3],'low':f[4],
                       'volume_provider_units':f[5],'amount_provider_units':f[6],'reported_price_change':f[9],
                       'provider_implied_preclose':str(close-delta)})
    if [r['date'] for r in result]!=sessions:raise ValueError('all explicit sessions required, no future/duplicates/gap filling')
    return result


def block_flags(row,code):
    op=Decimal(row['open']);pre=Decimal(row['provider_implied_preclose']);rate=Decimal('.2') if code=='SZ159915' else Decimal('.1')
    if pre<=0:raise ValueError('positive provider-implied reference required')
    low=(pre*(1-rate)).quantize(Decimal('.001'),rounding=ROUND_HALF_UP);high=(pre*(1+rate)).quantize(Decimal('.001'),rounding=ROUND_HALF_UP)
    if not low<=op<=high:raise ValueError('source open contradicts declared provider reference band')
    return int(op>=high),int(op<=low)


def capture(out,sessions):
    out=Path(out)
    if out.exists():raise ValueError('fresh immutable capture required')
    out.mkdir(parents=True);receipts={};packets={};errors={}
    identities=[(c,m) for c in FUNDS for m in ('raw','hfq')]+[(c,'raw') for c in INDEXES]
    for code,mode in identities:
        key=code+'-'+mode;target=url(code,mode)
        try:
            req=Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
            with urlopen(req,timeout=20) as response:
                raw=response.read(4*1024*1024+1);status=response.status
            (out/(key+'-wire.json')).write_bytes(raw)
            if len(raw)>4*1024*1024 or status!=200:raise ValueError('bounded successful HTTP body required')
            bars=parse(json.loads(raw),code,mode,sessions)
            packet={'instrument':code,'mode':mode,'bars':bars,'window':[START,END],'volume_unit_verified':False,'historical_arrival_verified':False}
            write(out/(key+'.json'),packet);packets[key]=packet
            receipts[key]={'url':target,'status':status,'sha256':sha(out/(key+'-wire.json')),'rows':len(bars)}
            print('captured',key,len(bars),flush=True)
        except Exception as exc:errors[key]={'type':type(exc).__name__,'error':str(exc),'url':target}
    manifest={'status':'ALL13_CAPTURED' if not errors else 'SOURCE_CAPTURE_INCOMPLETE','receipts':receipts,'errors':errors,
              'maximum_queries':13,'queries_attempted':len(identities),'2026_price_queries':False,'artifact_sha256':inventory(out)}
    write(out/'manifest.json',manifest)
    if errors:raise ValueError('source failures retained: '+str(sorted(errors)))
    return packets


def build_provider(out,packets,sessions,next_session):
    out=Path(out)
    if out.exists():raise ValueError('fresh provider required')
    if sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=[START,END] or next_session<=END:raise ValueError('explicit actual session boundary required')
    out.mkdir(parents=True);(out/'calendars').mkdir();(out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(sessions)+'\n');(out/'calendars/day_future.txt').write_text('\n'.join(sessions+[next_session])+'\n')
    (out/'instruments/all.txt').write_text(''.join(f'{c}\t{START}\t{END}\n' for c in FUNDS+INDEXES))
    for c in FUNDS+INDEXES:
        raw=packets[c+'-raw']['bars'];adj=packets[c+'-hfq']['bars'] if c in FUNDS else raw
        first=Decimal(adj[0]['close']);values={n:[] for n in ('open','high','low','close','volume','factor','change','buyblock','sellblock')};previous=None
        for r,h in zip(raw,adj):
            if r['date']!=h['date']:raise ValueError('raw and adjusted dates differ')
            norm=Decimal(h['close'])/first;factor=norm/Decimal(r['close'])
            for f in ('open','high','low','close'):values[f].append(float(Decimal(r[f])*factor))
            values['factor'].append(float(factor));values['volume'].append(float(Decimal(r['volume_provider_units'])/factor))
            values['change'].append(float(norm/previous-1) if previous else 0.);previous=norm
            buy,sell=block_flags(r,c) if c in FUNDS else (0,0);values['buyblock'].append(buy);values['sellblock'].append(sell)
        folder=out/'features'/c.lower();folder.mkdir(parents=True)
        for field,v in values.items():(folder/(field+'.day.bin')).write_bytes(struct.pack('<'+str(len(v)+1)+'f',0,*v))
    manifest={'status':'PRE2026_ETF_ADJUSTED_ENGINEERING_PROVIDER','window':[START,END],'next_clock_session':next_session,
              'volume_units':'UNVERIFIED_PROVIDER_UNITS_ONLY_ACTIVITY_NO_SHARE_CAPACITY_CLAIM','impact_cost':0,
              'price_band_reference':'provider implied close minus reported change; not exchange-certified limits',
              'all_output_sha256':inventory(out)}
    write(out/'manifest.json',manifest);return manifest


def main():
    p=argparse.ArgumentParser();p.add_argument('--calendar',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out)
    if out.exists():raise ValueError('fresh whole data stage required')
    calendar=Path(a.calendar).read_text().splitlines();sessions=[d for d in calendar if START<=d<=END];following=next(d for d in calendar if d>END)
    if len(sessions)!=749:raise ValueError('749 explicit historical source sessions required')
    out.mkdir(parents=True);packets=capture(out/'capture',sessions);build_provider(out/'provider',packets,sessions,following)
    write(out/'preparation.json',{'calendar_file':str(Path(a.calendar).resolve()),'calendar_sha256':sha(a.calendar),'queries':13,'source_start':START,'source_end':END,'2026_prices_captured':False})
    print('blogger ETF source views ready; no returns computed')


if __name__=='__main__':main()
