"""Same-provider bounded alternative after Eastmoney transport failures; no ROI."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import struct
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from scripts import prepare_blogger_etf_data as common

START,END='2023-07-03','2025-12-31'


def url(code,mode):
    if code not in common.FUNDS+common.INDEXES or mode not in ('raw','hfq') or code in common.INDEXES and mode!='raw':raise ValueError('fixed13 identities only')
    params={'param':code.lower()+',day,'+START+','+END+',640,'+('hfq' if mode=='hfq' else '')}
    return 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode(params)


def parse(body,code,mode,sessions):
    part=(body.get('data') or {}).get(code.lower());field='hfqday' if mode=='hfq' else 'day'
    if body.get('code')!=0 or not isinstance(part,dict) or field not in part:raise ValueError('explicit code and requested adjustment field required; no silent fallback')
    result=[]
    for f in part[field]:
        if not isinstance(f,list) or len(f)!=6:raise ValueError('expected6 daily values')
        day=f[0];op,close,high,low,volume=map(Decimal,f[1:])
        if (not START<=day<=END or any(not v.is_finite() or v<=0 for v in (op,close,high,low,volume))
                or low>min(op,close) or high<max(op,close)):
            raise ValueError('positive full OHLC/activity and bounded date required')
        if mode=='raw' and code in common.FUNDS and any(v!=v.quantize(Decimal('.001')) for v in (op,close,high,low)):
            raise ValueError('ETF raw tick changed')
        result.append({'date':day,'open':f[1],'close':f[2],'high':f[3],'low':f[4],'volume_provider_units':f[5]})
    if [r['date'] for r in result]!=sessions:raise ValueError('complete actual session sequence required')
    return {'instrument':code,'mode':mode,'window':[START,END],'bars':result,'volume_unit_verified':False,'historical_arrival_verified':False}


def capture(out,sessions):
    out=Path(out);out.mkdir();packets={};receipts={};errors={}
    for code,mode in [(c,m) for c in common.FUNDS for m in ('raw','hfq')]+[(c,'raw') for c in common.INDEXES]:
        key=code+'-'+mode;target=url(code,mode)
        try:
            req=Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'})
            with urlopen(req,timeout=20) as response:raw=response.read(4*1024*1024+1);status=response.status
            (out/(key+'-wire.json')).write_bytes(raw)
            if status!=200 or len(raw)>4*1024*1024:raise ValueError('bounded HTTP response required')
            packet=parse(json.loads(raw),code,mode,sessions);common.write(out/(key+'.json'),packet);packets[key]=packet
            receipts[key]={'url':target,'sha256':common.sha(out/(key+'-wire.json')),'rows':len(packet['bars'])}
            print('Tencent captured',key,len(packet['bars']),flush=True)
        except Exception as exc:errors[key]={'url':target,'type':type(exc).__name__,'error':str(exc)};print('Tencent missing',key,flush=True)
    manifest={'status':'ALL13_CAPTURED' if not errors else 'CAPTURE_INCOMPLETE','source':'TENCENT_ONLY_NO_PROVIDER_SPLICE',
              'maximum_queries':13,'receipts':receipts,'errors':errors,'2026_prices_requested':False,'all_output_sha256':common.inventory(out)}
    common.write(out/'manifest.json',manifest)
    if errors:raise ValueError('remaining missing Tencent sources')
    return packets


def build(out,packets,sessions,following):
    out=Path(out);out.mkdir();(out/'calendars').mkdir();(out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(sessions)+'\n');(out/'calendars/day_future.txt').write_text('\n'.join(sessions+[following])+'\n')
    (out/'instruments/all.txt').write_text(''.join(f'{c}\t{START}\t{END}\n' for c in common.FUNDS+common.INDEXES))
    for c in common.FUNDS+common.INDEXES:
        raw=packets[c+'-raw']['bars'];hfq=packets[c+'-hfq']['bars'] if c in common.FUNDS else raw
        first=Decimal(hfq[0]['close']);previous_norm=None
        values={k:[] for k in ('open','high','low','close','factor','volume','change','buyblock','sellblock')}
        for r,h in zip(raw,hfq):
            if r['date']!=h['date']:raise ValueError('adjustment date alignment required')
            norm=Decimal(h['close'])/first;factor=norm/Decimal(r['close'])
            for k in ('open','high','low','close'):values[k].append(float(Decimal(r[k])*factor))
            values['factor'].append(float(factor));values['volume'].append(float(Decimal(r['volume_provider_units'])/factor))
            values['change'].append(float(norm/previous_norm-1) if previous_norm else 0.)
            if c in common.FUNDS and previous_norm is not None:
                # Implied ex-right reference, not an authenticated exchange limit.
                reference=previous_norm/factor
                buy,sell=common.block_flags({**r,'provider_implied_preclose':str(reference)},c)
            else:buy,sell=0,0
            values['buyblock'].append(buy);values['sellblock'].append(sell);previous_norm=norm
        folder=out/'features'/c.lower();folder.mkdir(parents=True)
        for k,v in values.items():(folder/(k+'.day.bin')).write_bytes(struct.pack('<'+str(len(v)+1)+'f',0,*v))
    common.write(out/'manifest.json',{'status':'PRE2026_SINGLE_PROVIDER_ETF_ENGINEERING_VIEW','source':'TENCENT','window':[START,END],
        'implied_price_reference':'prior normalized close / current factor; first warmup reference unused',
        'volume_units_verified':False,'impact_cost':0,'all_output_sha256':common.inventory(out)})


def main():
    p=argparse.ArgumentParser();p.add_argument('--calendar',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out)
    if out.exists():raise ValueError('fresh alternate capture required')
    days=Path(a.calendar).read_text().splitlines();sessions=[d for d in days if START<=d<=END];following=next(d for d in days if d>END)
    if sessions[0]!=START or sessions[-1]!=END or len(sessions)>640:raise ValueError('actual bounded warmup calendar required')
    out.mkdir(parents=True);packets=capture(out/'capture',sessions);build(out/'provider',packets,sessions,following)
    common.write(out/'preparation.json',{'source':'Tencent all13 independent captures; rejected Eastmoney captures retained separately',
        'warmup_start':START,'last_quote':END,'calendar_file':str(Path(a.calendar).resolve()),'calendar_sha256':common.sha(a.calendar),
        'all_strategy_windows_covered_before2024':True,'provider_mix':False,'2026_prices_captured':False})
    print('Tencent source ready; no returns computed')


if __name__=='__main__':main()
