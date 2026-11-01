"""Bounded old-date warmup capture, one symbol, immutable existing price suffix."""
import argparse,json,struct
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from scripts.prepare_blogger_etf_data import inventory,sha,write,block_flags

CODE='SH510050';START='2022-12-01';JOIN='2023-07-03';END='2025-12-31'
FIELDS=('open','high','low','close','factor','volume','change','buyblock','sellblock')

def read(p):return json.loads(Path(p).read_text())

def parse(body,mode,dates):
    field='hfqday' if mode=='hfq' else 'day';part=(body.get('data') or {}).get(CODE.lower())
    if body.get('code')!=0 or not isinstance(part,dict) or field not in part:raise ValueError('explicit raw/HFQ identity required')
    result=[]
    for row in part[field]:
        if not isinstance(row,list) or len(row)!=6:raise ValueError('six fields required')
        day=row[0];op,cl,hi,lo,vol=map(Decimal,row[1:])
        if not START<=day<='2023-07-31' or any(not v.is_finite() or v<=0 for v in (op,cl,hi,lo,vol)) or lo>min(op,cl) or hi<max(op,cl):raise ValueError('bounded complete positive OHLC/activity required')
        if mode=='raw' and any(v!=v.quantize(Decimal('.001')) for v in (op,cl,hi,lo)):raise ValueError('raw ETF tick required')
        result.append(dict(zip(('date','open','close','high','low','volume_provider_units'),row)))
    if [r['date'] for r in result]!=dates:raise ValueError('exact requested actual warmup sessions, no future or duplicates')
    return {'instrument':CODE,'mode':mode,'bars':result}

def merge(earlier,original,dates):
    old={r['date']:r for r in original['bars']};overlap=0
    for r in earlier['bars']:
        if r['date']>=JOIN:
            if r['date'] not in old or any(Decimal(r[k])!=Decimal(old[r['date']][k]) for k in r if k!='date'):raise ValueError('warmup overlap version changed')
            overlap+=1
    joined=[r for r in earlier['bars'] if r['date']<JOIN]+original['bars']
    if [r['date'] for r in joined]!=dates or not overlap:raise ValueError('complete earlier warmup and unchanged original history required')
    return {**original,'bars':joined},overlap

def build(out,packets,dates,following,original_provider):
    out.mkdir();(out/'calendars').mkdir();(out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(dates)+'\n');(out/'calendars/day_future.txt').write_text('\n'.join(dates+[following])+'\n')
    (out/'instruments/all.txt').write_text(CODE+'\t'+dates[0]+'\t'+dates[-1]+'\n')
    anchor=next(r for r in packets['hfq']['bars'] if r['date']==JOIN);denom=Decimal(anchor['close']);values={f:[] for f in FIELDS};previous=None
    for r,h in zip(packets['raw']['bars'],packets['hfq']['bars']):
        if r['date']>=JOIN:break
        norm=Decimal(h['close'])/denom;factor=norm/Decimal(r['close'])
        for f in ('open','high','low','close'):values[f].append(float(Decimal(r[f])*factor))
        values['factor'].append(float(factor));values['volume'].append(float(Decimal(r['volume_provider_units'])/factor));values['change'].append(float(norm/previous-1) if previous is not None else 0.)
        flags=block_flags({**r,'provider_implied_preclose':str(previous/factor)},CODE) if previous is not None else (0,0)
        values['buyblock'].append(flags[0]);values['sellblock'].append(flags[1]);previous=norm
    warm=len(values['close']);folder=out/'features'/CODE.lower();folder.mkdir(parents=True);evidence={}
    for f in FIELDS:
        path=original_provider/'features'/CODE.lower()/(f+'.day.bin');original=path.read_bytes()
        if struct.unpack('<f',original[:4])[0]!=0:raise ValueError('known old origin required')
        blob=struct.pack('<'+str(warm+1)+'f',0,*values[f])+original[4:]
        if len(blob)!=4*(len(dates)+1) or blob[4*(warm+1):]!=original[4:]:raise ValueError('unchanged original quote values required')
        (folder/(f+'.day.bin')).write_bytes(blob);evidence[f]={'old_sha256':sha(path),'old_value_bytes':len(original)-4,'prewarm_rows':warm,'all_original_value_bytes_identical':True}
    write(out/'manifest.json',{'end':dates[-1],'old_values_unchanged':evidence,'initial_old_join_change_and_flags_retained_as_warmup_sentinels':True,'all_output_sha256':inventory(out)})

def prepare(old,calendar_file,out):
    if out.exists():raise ValueError('fresh immutable warmup dataset required')
    all_dates=Path(calendar_file).read_text().splitlines();dates=[d for d in all_dates if START<=d<=END];fetch=[d for d in dates if d<='2023-07-31'];following=next(d for d in all_dates if d>END)
    if not dates or dates[0]!=START or dates[-1]!=END or len([d for d in dates if d<'2024-01-02'])<200:raise ValueError('complete real calendar and200pre2024 sessions required')
    out.mkdir(parents=True);(out/'capture').mkdir();(out/'combined').mkdir();packets={};receipts={};errors={}
    for mode in ('raw','hfq'):
        target='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':'sh510050,day,'+START+',2023-07-31,640,'+('hfq' if mode=='hfq' else '')})
        try:
            with urlopen(Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'}),timeout=20) as response:raw=response.read(4*1024*1024+1);status=response.status
            wire=out/'capture'/(mode+'-wire.json');wire.write_bytes(raw)
            if status!=200 or len(raw)>4*1024*1024:raise ValueError('bounded HTTP200 required')
            p=parse(json.loads(raw),mode,fetch);write(out/'capture'/(mode+'.json'),p)
            original=read(old/'capture'/(CODE+'-'+mode+'.json'));p,count=merge(p,original,dates);packets[mode]=p;write(out/'combined'/(mode+'.json'),p)
            receipts[mode]={'url':target,'wire_sha256':sha(wire),'overlap_rows':count};print('warmup',mode,'overlap',count,flush=True)
        except Exception as e:errors[mode]={'type':type(e).__name__,'error':str(e),'url':target}
    write(out/'capture/manifest.json',{'status':'COMPLETE_TWO_WARMUP_SOURCES' if not errors else 'WARMUP_CAPTURE_FAILED','receipts':receipts,'errors':errors})
    if errors:raise ValueError('warmup source missing; preserve failures')
    build(out/'provider',packets,dates,following,old/'provider')
    write(out/'preparation.json',{'old_data_root':str(old),'old_data_sha256':inventory(old),'calendar_file':str(calendar_file),'calendar_sha256':sha(calendar_file),
        'quotes_end':END,'all_inputs_pre2026':True,'new_candidate_returns_computed':False,'same_normalization_anchor':JOIN})
    print('batch2 data ready; no returns computed')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('old-data','calendar','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();prepare(Path(a.old_data).resolve(),Path(a.calendar).resolve(),Path(a.out).resolve())
