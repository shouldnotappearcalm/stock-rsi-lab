"""Fixed domestic bond source plus unchanged stock data; no strategy P&L."""
import argparse,json,shutil,struct
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from scripts.prepare_blogger_etf_data import inventory,sha,write,block_flags

STOCK,BOND='SH510050','SH511010'
FIELDS=('open','high','low','close','factor','volume','change','buyblock','sellblock')

def read(p):return json.loads(Path(p).read_text())

def parse(body,mode,dates):
    field='hfqday' if mode=='hfq' else 'day';part=(body.get('data') or {}).get(BOND.lower())
    if body.get('code')!=0 or not isinstance(part,dict) or field not in part:raise ValueError('explicit bond/raw/HFQ identity required')
    bars=[]
    for r in part[field]:
        if not isinstance(r,list) or len(r)!=6:raise ValueError('six source fields required')
        op,cl,hi,lo,vol=map(Decimal,r[1:])
        if any(not x.is_finite() for x in (op,cl,hi,lo,vol)) or cl<=0 or min(op,hi,lo,vol)<0:raise ValueError('finite positive mark and nonnegative observed trade fields required')
        if vol>0 and (min(op,hi,lo)<=0 or lo>min(op,cl) or hi<max(op,cl)):raise ValueError('active bar must have complete OHLC')
        if mode=='raw' and any(x!=x.quantize(Decimal('.001')) for x in (op,cl,hi,lo)):raise ValueError('raw bond ETF tick required')
        bars.append(dict(zip(('date','open','close','high','low','volume_provider_units'),r)))
    if [r['date'] for r in bars]!=dates:raise ValueError('exact actual session window, no gaps/future/duplicates')
    return {'instrument':BOND,'mode':mode,'bars':bars,'volume_unit_verified':False}

def capture(out,dates):
    out.mkdir();packets={};receipts={};errors={}
    for mode in ('raw','hfq'):
        target='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':BOND.lower()+',day,'+dates[0]+','+dates[-1]+',640,'+('hfq' if mode=='hfq' else '')})
        try:
            with urlopen(Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://gu.qq.com/'}),timeout=20) as response:raw=response.read(4*1024*1024+1);status=response.status
            p=out/(mode+'-wire.json');p.write_bytes(raw)
            if status!=200 or len(raw)>4*1024*1024:raise ValueError('bounded HTTP200 required')
            packet=parse(json.loads(raw),mode,dates);write(out/(mode+'.json'),packet);packets[mode]=packet
            receipts[mode]={'url':target,'wire_sha256':sha(p),'rows':len(dates)};print('captured bond',mode,len(dates),flush=True)
        except Exception as e:errors[mode]={'type':type(e).__name__,'error':str(e),'url':target};print('failed bond',mode,str(e),flush=True)
    write(out/'manifest.json',{'status':'BOTH_BOND_MODES_CAPTURED' if not errors else 'CAPTURE_FAILED','receipts':receipts,'errors':errors})
    if errors:raise ValueError('bond capture failed; no prices synthesized')
    return packets

def merge(before,after,dates):
    lookup={r['date']:r for r in before['bars']};count=0
    for r in after['bars']:
        if r['date']<='2025-12-31':
            if r['date'] not in lookup or any(Decimal(r[k])!=Decimal(lookup[r['date']][k]) for k in r if k!='date'):raise ValueError('bond source overlap changed')
            count+=1
    combined=before['bars']+[r for r in after['bars'] if r['date']>'2025-12-31']
    if [r['date'] for r in combined]!=dates or count!=23:raise ValueError('all23 overlap sessions and exact forward tail required')
    return {**before,'bars':combined}

def bond_values(raw,adjusted,references=None):
    denom=Decimal(adjusted[0]['close']);previous=None;values={f:[] for f in FIELDS}
    for r,h in zip(raw,adjusted):
        if r['date']!=h['date']:raise ValueError('same raw/HFQ dates required')
        norm=Decimal(h['close'])/denom;factor=norm/Decimal(r['close'])
        for f in ('open','high','low','close'):values[f].append(float(Decimal(r[f])*factor))
        values['factor'].append(float(factor));values['volume'].append(float(Decimal(r['volume_provider_units'])/factor));values['change'].append(float(norm/previous-1) if previous is not None else 0.)
        if Decimal(r['volume_provider_units'])==0:flags=(1,1)
        elif previous is None:flags=(0,0)
        else:
            pre=references[r['date']] if references is not None and r['date']>'2025-12-31' else str(previous/factor)
            flags=block_flags({**r,'provider_implied_preclose':pre},BOND)
        values['buyblock'].append(flags[0]);values['sellblock'].append(flags[1]);previous=norm
    return values

def build(out,calendar,following,stock_provider,packets,references=None,original=None):
    out.mkdir();(out/'calendars').mkdir();(out/'instruments').mkdir()
    (out/'calendars/day.txt').write_text('\n'.join(calendar)+'\n');(out/'calendars/day_future.txt').write_text('\n'.join(calendar+[following])+'\n')
    bond_dates=[r['date'] for r in packets['raw']['bars']];offset=calendar.index(bond_dates[0])
    if bond_dates!=calendar[offset:]:raise ValueError('complete bond calendar suffix required')
    (out/'instruments/all.txt').write_text(STOCK+'\t'+calendar[0]+'\t'+calendar[-1]+'\n'+BOND+'\t'+bond_dates[0]+'\t'+calendar[-1]+'\n')
    sf=out/'features'/STOCK.lower();sf.mkdir(parents=True)
    for f in FIELDS:shutil.copyfile(stock_provider/'features'/STOCK.lower()/(f+'.day.bin'),sf/(f+'.day.bin'))
    values=bond_values(packets['raw']['bars'],packets['hfq']['bars'],references);bf=out/'features'/BOND.lower();bf.mkdir()
    for f,v in values.items():(bf/(f+'.day.bin')).write_bytes(struct.pack('<'+str(len(v)+1)+'f',offset,*v))
    if original is not None:
        for c in (STOCK,BOND):
            for f in FIELDS:
                rel=Path('features')/c.lower()/(f+'.day.bin');old=(original/rel).read_bytes()
                if (out/rel).read_bytes()[:len(old)]!=old:raise ValueError('original development quote prefix changed')
    write(out/'manifest.json',{'end':calendar[-1],'source':'TENCENT_PRICES','inactive_bond_rows':sum(Decimal(r['volume_provider_units'])==0 for r in packets['raw']['bars']),
        'original_development_prefixes_identical':original is not None,'all_output_sha256':inventory(out)})

def prepare_development(stock_data,out):
    if out.exists():raise ValueError('fresh data output required')
    stock=stock_data/'provider';cal=(stock/'calendars/day.txt').read_text().splitlines();future=(stock/'calendars/day_future.txt').read_text().splitlines()[-1]
    if cal[0]!='2022-12-01' or cal[-1]!='2025-12-31':raise ValueError('physically capped fixed warmup stock data required')
    out.mkdir(parents=True);packets=capture(out/'capture',[d for d in cal if d>='2023-07-03']);(out/'combined').mkdir()
    for mode,p in packets.items():write(out/'combined'/(mode+'.json'),p)
    build(out/'provider',cal,future,stock,packets)
    write(out/'preparation.json',{'phase':'development','stock_data_root':str(stock_data),'stock_data_sha256':inventory(stock_data),'new_candidate_returns_computed':False})

def capture_references(out,packets,dates):
    import baostock as bs
    fields='date,code,open,high,low,close,preclose,volume,adjustflag,tradestatus';login=bs.login()
    if login.error_code!='0':raise ValueError('reference login failed')
    try:
        r=bs.query_history_k_data_plus('sh.511010',fields,start_date=dates[0],end_date=dates[-1],frequency='d',adjustflag='3');rr=[]
        while r.error_code=='0' and r.next():rr.append(r.get_row_data())
        packet={'fields':r.fields,'rows':rr,'error_code':r.error_code,'source':'BaoStock raw reported preclose, not official exchange stream'};write(out,packet)
        mapped=[dict(zip(r.fields,row)) for row in rr]
        if r.error_code!='0' or [row['date'] for row in mapped]!=dates:raise ValueError('complete reference calendar required')
        byday={row['date']:row for row in packets['raw']['bars']};result={}
        for row in mapped:
            if row['code']!='sh.511010' or row['adjustflag']!='3' or any(Decimal(row[f])!=Decimal(byday[row['date']][f]) for f in ('open','high','low','close')):raise ValueError('reference identity or primary OHLC mismatch')
            if not Decimal(row['preclose']).is_finite() or Decimal(row['preclose'])<=0:raise ValueError('positive raw preclose required')
            result[row['date']]=row['preclose']
        return result
    finally:bs.logout()

def prepare_forward(dev,prior,out):
    if out.exists():raise ValueError('fresh forward data required')
    out.mkdir(parents=True);before=(dev/'provider/calendars/day.txt').read_text().splitlines();source=(prior/'provider/calendars/day.txt').read_text().splitlines();tail=[d for d in source if d>'2025-12-31'];cal=before+tail
    if before[-1]!='2025-12-31' or source[-1]!='2026-10-30':raise ValueError('fixed complete January-October window required')
    packets=capture(out/'capture',[d for d in source if d>='2025-12-01']);(out/'combined').mkdir()
    for mode in packets:
        packets[mode]=merge(read(dev/'combined'/(mode+'.json')),packets[mode],[d for d in cal if d>='2023-07-03']);write(out/'combined'/(mode+'.json'),packets[mode])
    refs=capture_references(out/'reference-source.json',packets,tail)
    stock_provider=out/'stock-appended';(stock_provider/'features'/STOCK.lower()).mkdir(parents=True);cut=source.index(tail[0])
    for f in FIELDS:
        rel=Path('features')/STOCK.lower()/(f+'.day.bin');a=(dev/'provider'/rel).read_bytes();b=(prior/'provider'/rel).read_bytes()
        if a[4*(before.index('2023-07-03')+1):]!=b[4:4*(cut+1)]:raise ValueError('stock source normalization or history changed')
        (stock_provider/rel).write_bytes(a+b[4*(cut+1):])
    following=(prior/'provider/calendars/day_future.txt').read_text().splitlines()[-1]
    if following!='2026-11-02':raise ValueError('actual next clock session required')
    build(out/'provider',cal,following,stock_provider,packets,refs,dev/'provider')
    write(out/'preparation.json',{'phase':'forward','development_data_root':str(dev),'development_data_sha256':inventory(dev),
        'source_2026_root':str(prior),'source_2026_sha256':inventory(prior),'new_candidate_returns_computed':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['development','forward']);p.add_argument('--stock-data');p.add_argument('--development-data');p.add_argument('--previous-forward');p.add_argument('--out',required=True);a=p.parse_args()
    if a.phase=='development':prepare_development(Path(a.stock_data).resolve(),Path(a.out).resolve())
    else:prepare_forward(Path(a.development_data).resolve(),Path(a.previous_forward).resolve(),Path(a.out).resolve())
