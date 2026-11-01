"""Bounded same-provider transport recovery; preserve the original failed capture."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from scripts import prepare_blogger_etf_data as base


def recover(original,probes,out,sessions):
    original,probes,out=Path(original),Path(probes),Path(out)
    if out.exists():raise ValueError('fresh recovery only')
    out.mkdir(parents=True);packets={};receipts={};errors={};attempts=[]
    identity=[(c,m) for c in base.FUNDS for m in ('raw','hfq')]+[(c,'raw') for c in base.INDEXES]
    known_probes={'SH518880-raw':'gold_raw.json','SH510050-raw':'etf50_raw.json','SH000016-raw':'index50.json'}
    parent=base.inventory(original)
    for code,mode in identity:
        key=code+'-'+mode;wire=original/(key+'-wire.json');raw=None;origin=None
        if (original/(key+'.json')).exists() and wire.exists():raw=wire.read_bytes();origin=str(wire)
        elif key in known_probes and (probes/known_probes[key]).exists():raw=(probes/known_probes[key]).read_bytes();origin=str(probes/known_probes[key])
        if raw is not None:
            bars=base.parse(json.loads(raw),code,mode,sessions)
        else:
            for attempt in range(2):
                target=base.url(code,mode)+'&ut=7eea3edcaed734bea9cbfc24409ed989'
                record={'identity':key,'attempt':attempt+1,'url':target};attempts.append(record)
                time.sleep(.5)
                try:
                    req=Request(target,headers={'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'})
                    with urlopen(req,timeout=20) as response:raw=response.read(4*1024*1024+1);record['status']=response.status
                    if len(raw)>4*1024*1024 or record['status']!=200:raise ValueError('bounded HTTP body required')
                    (out/(key+'-attempt'+str(attempt+1)+'-wire.json')).write_bytes(raw)
                    bars=base.parse(json.loads(raw),code,mode,sessions);origin=target;record['parsed']=True;break
                except Exception as exc:record.update(error_type=type(exc).__name__,error=str(exc));raw=None
            if raw is None:errors[key]=attempts[-1];print('still missing',key,flush=True);continue
        (out/(key+'-wire.json')).write_bytes(raw)
        packet={'instrument':code,'mode':mode,'bars':bars,'window':[base.START,base.END],'volume_unit_verified':False,'historical_arrival_verified':False}
        base.write(out/(key+'.json'),packet);packets[key]=packet;receipts[key]={'origin':origin,'wire_sha256':base.sha(out/(key+'-wire.json')),'rows':len(bars)}
        print('recovered',key,len(bars),flush=True)
    result={'status':'ALL13_RECOVERED' if not errors else 'RECOVERY_INCOMPLETE','receipts':receipts,'errors':errors,'HTTP_attempts':attempts,
            'max_retries_per_missing_identity':2,'same_provider_only':True,'source_vintage_atomicity_verified':False,
            'original_failed_capture_sha256':parent,'all_output_sha256':base.inventory(out),'2026_prices_requested':False}
    base.write(out/'manifest.json',result)
    if errors:raise ValueError('remaining source identities missing')
    if base.inventory(original)!=parent:raise ValueError('original failure evidence changed')
    return packets


def main():
    p=argparse.ArgumentParser()
    for n in ('original','probes','calendar','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();out=Path(a.out)
    if out.exists():raise ValueError('fresh whole stage required')
    day=Path(a.calendar).read_text().splitlines();sessions=[d for d in day if base.START<=d<=base.END];following=next(d for d in day if d>base.END)
    out.mkdir(parents=True);packets=recover(a.original,a.probes,out/'capture',sessions);base.build_provider(out/'provider',packets,sessions,following)
    base.write(out/'preparation.json',{'source':'bounded same-provider recovery','calendar':str(Path(a.calendar).resolve()),'calendar_sha256':base.sha(a.calendar),'2026_prices_captured':False})
    print('all13 source identities and capped provider ready')


if __name__=='__main__':main()
