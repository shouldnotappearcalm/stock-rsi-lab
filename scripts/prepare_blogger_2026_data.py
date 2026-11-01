"""Append fixed Tencent identities, rejecting any changed overlap or old bytes."""
import argparse
from decimal import Decimal
import json,struct,shutil
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from scripts.prepare_blogger_etf_data import FUNDS,INDEXES,inventory,sha,write,block_flags

START,OLD_END,FETCH_START,END='2023-07-03','2025-12-31','2025-12-01','2026-10-30'
IDENTITIES=tuple((c,m) for c in FUNDS for m in ('raw','hfq'))+tuple((c,'raw') for c in INDEXES)
FIELDS=('open','high','low','close','factor','volume','change','buyblock','sellblock')


def read(p):return json.loads(Path(p).read_text())


def calendar(packet):
    if packet['error_code']!='0' or packet['fields']!=['calendar_date','is_trading_day']:raise ValueError('successful actual session table required')
    rows=packet['rows'];dates=[r[0] for r in rows]
    if dates!=sorted(set(dates)) or any(r[1] not in ('0','1') for r in rows):raise ValueError('ordered explicit calendar required')
    sessions=[d for d,flag in rows if flag=='1' and START<=d<=END]
    following=next((d for d,flag in rows if flag=='1' and d>END),None)
    if not sessions or [sessions[0],sessions[-1]]!=[START,END] or following!='2026-11-02':raise ValueError('fixed complete October and actual next clock session required')
    return sessions,following


def parse(body,code,mode,sessions):
    field='hfqday' if mode=='hfq' else 'day';part=(body.get('data') or {}).get(code.lower())
    if (code,mode) not in IDENTITIES or body.get('code')!=0 or not isinstance(part,dict) or field not in part:raise ValueError('explicit security and adjustment identity required')
    bars=[]
    for r in part[field]:
        if not isinstance(r,list) or len(r)!=6:raise ValueError('six exact daily fields required')
        day=r[0];op,close,high,low,volume=map(Decimal,r[1:])
        if (not FETCH_START<=day<=END or any(not v.is_finite() or v<=0 for v in (op,close,high,low,volume))
                or low>min(op,close) or high<max(op,close)):raise ValueError('bounded positive complete OHLC/activity required')
        if mode=='raw' and code in FUNDS and any(v!=v.quantize(Decimal('.001')) for v in (op,close,high,low)):raise ValueError('ETF raw tick required')
        bars.append(dict(zip(('date','open','close','high','low','volume_provider_units'),r)))
    if [r['date'] for r in bars]!=sessions:raise ValueError('every actual requested session, no gaps/future bars')
    return {'instrument':code,'mode':mode,'window':[FETCH_START,END],'bars':bars,'volume_unit_verified':False,'historical_arrival_verified':False}


def merge(old,new,sessions):
    if old['instrument']!=new['instrument'] or old['mode']!=new['mode']:raise ValueError('same source identity required')
    old_rows={r['date']:r for r in old['bars']};overlap=0
    for r in new['bars']:
        if r['date']<=OLD_END:
            a=old_rows.get(r['date'])
            if a is None or set(a)!=set(r) or any(Decimal(a[k])!=Decimal(r[k]) for k in a if k!='date'):raise ValueError('source overlap changed; do not rebase or overwrite')
            overlap+=1
    expected=[d for d in sessions if FETCH_START<=d<=OLD_END]
    if [r['date'] for r in new['bars'] if r['date']<=OLD_END]!=expected or not expected:raise ValueError('all predeclared overlap sessions required')
    bars=old['bars']+[r for r in new['bars'] if r['date']>OLD_END]
    if [r['date'] for r in bars]!=sessions:raise ValueError('old history and new tails must exactly partition actual calendar')
    return {**old,'window':[START,END],'bars':bars},overlap


def references(folder,packets,sessions):
    result={};wanted=[d for d in sessions if d>OLD_END]
    for c in FUNDS:
        data=read(folder/(c+'.json'));q=data['query'];rows=[dict(zip(data['fields'],r)) for r in data['rows']]
        if (data['error_code']!='0' or q['code']!=c[:2].lower()+'.'+c[2:] or q['adjustflag']!='3'
                or q['start_date']!='2026-01-05' or q['end_date']!=END or [r['date'] for r in rows]!=wanted):raise ValueError('complete raw BaoStock reference identity required')
        raw={r['date']:r for r in packets[c+'-raw']['bars']}
        for r in rows:
            if r['code']!=q['code'] or r['adjustflag']!='3' or r['tradestatus']!='1':raise ValueError('raw active identity required')
            if any(Decimal(r[k])!=Decimal(raw[r['date']][k]) for k in ('open','high','low','close')):raise ValueError('reference provider OHLC disagrees with primary Tencent prices')
            pre=Decimal(r['preclose'])
            if not pre.is_finite() or pre<=0:raise ValueError('positive reported raw reference required')
            result[c,r['date']]=str(pre)
    return result


def build(out,packets,sessions,following,old_provider,reported_references):
    out.mkdir();(out/'calendars').mkdir();(out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(sessions)+'\n');(out/'calendars/day_future.txt').write_text('\n'.join(sessions+[following])+'\n')
    (out/'instruments/all.txt').write_text(''.join(f'{c}\t{START}\t{END}\n' for c in FUNDS+INDEXES))
    prefixes={}
    for c in FUNDS+INDEXES:
        raw=packets[c+'-raw']['bars'];adjusted=packets[c+'-hfq']['bars'] if c in FUNDS else raw
        values={k:[] for k in FIELDS};first=Decimal(adjusted[0]['close']);previous=None
        for r,h in zip(raw,adjusted):
            if r['date']!=h['date']:raise ValueError('raw and HFQ source dates differ')
            norm=Decimal(h['close'])/first;factor=norm/Decimal(r['close'])
            for f in ('open','high','low','close'):values[f].append(float(Decimal(r[f])*factor))
            values['factor'].append(float(factor));values['volume'].append(float(Decimal(r['volume_provider_units'])/factor))
            values['change'].append(float(norm/previous-1) if previous is not None else 0.)
            if c in FUNDS and previous is not None:
                reference=reported_references[c,r['date']] if r['date']>OLD_END else str(previous/factor)
                buy,sell=block_flags({**r,'provider_implied_preclose':reference},c)
            else:buy,sell=0,0
            values['buyblock'].append(buy);values['sellblock'].append(sell);previous=norm
        folder=out/'features'/c.lower();folder.mkdir(parents=True)
        for f,v in values.items():
            rel=Path('features')/c.lower()/(f+'.day.bin');target=out/rel;blob=struct.pack('<'+str(len(v)+1)+'f',0,*v);old=(old_provider/rel).read_bytes()
            target.write_bytes(blob)
            if blob[:len(old)]!=old:raise ValueError('old feature prefix changed: '+str(rel))
            prefixes[str(rel)]={'original_sha256':sha(old_provider/rel),'original_bytes':len(old),'identical':True}
    write(out/'manifest.json',{'status':'FROZEN_OLD_PREFIX_PLUS_TENCENT_2026_TAIL','end':END,'next_clock_session':following,
        'sessions':len(sessions),'old_feature_prefixes':prefixes,'all_output_sha256':inventory(out),'investment_qualified':False})
    return prefixes


def prepare(old,calendar_file,out,references_dir=None,captured_input=None):
    if out.exists():raise ValueError('fresh output only')
    sessions,following=calendar(read(calendar_file));old_dates=(old/'provider/calendars/day.txt').read_text().splitlines()
    if old_dates!=[d for d in sessions if d<=OLD_END]:raise ValueError('original session prefix changed')
    out.mkdir(parents=True);(out/'capture').mkdir();(out/'combined').mkdir();write(out/'calendar-source.json',read(calendar_file))
    packets={};receipts={};errors={};overlaps={};capture=out/'capture'
    wanted=[d for d in sessions if d>=FETCH_START]
    for c,mode in IDENTITIES:
        key=c+'-'+mode;target='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':c.lower()+',day,'+FETCH_START+','+END+',640,'+('hfq' if mode=='hfq' else '')})
        try:
            if captured_input is not None:
                source=captured_input/'capture'/(key+'-wire.json');prior=read(captured_input/'capture/manifest.json')['receipts'][key]
                if sha(source)!=prior['sha256'] or prior['url']!=target:raise ValueError('original captured HTTP receipt required')
                raw=source.read_bytes();status=200
            else:
                req=Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
                with urlopen(req,timeout=20) as response:raw=response.read(4*1024*1024+1);status=response.status
            wire=capture/(key+'-wire.json');wire.write_bytes(raw)
            if status!=200 or len(raw)>4*1024*1024:raise ValueError('bounded successful HTTP required')
            packet=parse(json.loads(raw),c,mode,wanted);write(capture/(key+'.json'),packet)
            merged,count=merge(read(old/'capture'/(key+'.json')),packet,sessions);packets[key]=merged;overlaps[key]=count
            write(out/'combined'/(key+'.json'),merged);receipts[key]={'url':target,'sha256':sha(wire),'rows':len(packet['bars'])}
            print('captured2026',key,'overlap',count,'rows',len(packet['bars']),flush=True)
        except Exception as exc:errors[key]={'url':target,'type':type(exc).__name__,'error':str(exc)};print('failed2026',key,str(exc),flush=True)
    write(capture/'manifest.json',{'status':'ALL13_CAPTURED_AND_OVERLAPS_EXACT' if not errors else 'CAPTURE_INCOMPLETE','receipts':receipts,'errors':errors,'maximum_queries':13,'all_output_sha256':inventory(capture)})
    if errors:raise ValueError('2026 capture failed; retained all failures')
    if references_dir is None:raise ValueError('raw reported2026 reference source required; no inverse-HFQ price boundary')
    shutil.copytree(references_dir,out/'reference-source');reported=references(out/'reference-source',packets,sessions)
    prefixes=build(out/'provider',packets,sessions,following,old/'provider',reported)
    write(out/'preparation.json',{'end':END,'source':'TENCENT_SAME_PROVIDER_EXACT_OVERLAP_APPEND_ONLY','old_data_root':str(old),
        'old_input_sha256':inventory(old),'overlap_sessions_by_identity':overlaps,'all72_feature_prefixes_identical':len(prefixes)==72,
        'calendar_file':str(calendar_file),'calendar_sha256':sha(calendar_file),'2026_portfolio_returns_computed':False,
        'execution_reference_2026':'BAOSTOCK_RAW_PRECLOSE_ALL5_FUNDS_ALL198_DAYS_OHLC_CROSSCHECKED',
        'primary_prices_or_signals_spliced':False,'reported_reference_rows':len(reported),
        'reused_failed_capture_sha256':inventory(captured_input) if captured_input is not None else None})
    print('2026 source prepared, no candidate returns computed',flush=True)


def main():
    p=argparse.ArgumentParser()
    for n in ('old-data','calendar','out','references'):p.add_argument('--'+n,required=True)
    p.add_argument('--captured-input')
    a=p.parse_args();prepare(Path(a.old_data).resolve(),Path(a.calendar).resolve(),Path(a.out).resolve(),Path(a.references).resolve(),Path(a.captured_input).resolve() if a.captured_input else None)


if __name__=='__main__':main()
