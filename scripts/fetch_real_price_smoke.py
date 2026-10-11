#!/usr/bin/env python3
"""Public raw-price engineering sample; deliberately not a PIT research dataset."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def convert(body, symbol, start, end, provenance):
    if not re.fullmatch(r'[06]\d{5}', symbol):
        raise ValueError('ordinary SSE/SZSE mainboard symbol required')
    exchange='sh' if symbol.startswith('6') else 'sz'
    rows=body.get('data',{}).get(exchange+symbol,{}).get('day')
    if body.get('code') != 0 or not rows:
        raise ValueError('raw day data missing; never substitute qfqday')
    output=[]
    previous=None
    for row in sorted(rows,key=lambda r:r[0]):
        day=row[0]
        op,close,high,low=(float(x) for x in row[1:5])
        if not all(math.isfinite(x) and x>0 for x in (op,close,high,low)):
            raise ValueError('invalid source price')
        if start<=day<=end:
            prior=previous if previous is not None else op
            payload={'trade_date':day,'open':op,'close':close,'high':high,'low':low,
                     'volume_provider_raw':row[5],'limit_up':round(prior*1.1,2),'limit_down':round(prior*.9,2),
                     'suspended':False,'limits_status':'ASSUMED_MAINBOARD_10PCT_UNVERIFIED'}
            output.append({'record_id':f'{symbol}:{day}:raw','fact_key':f'{symbol}:{day}:bar',
                           'security_id':symbol,'kind':'bar','event_at':day+'T15:00:00+08:00',
                           'public_at':day+'T15:01:00+08:00','available_at':day+'T17:00:00+08:00','payload':payload})
        previous=close
    if not output:
        raise ValueError('empty requested range')
    days=[row['payload']['trade_date'] for row in output]
    if len(set(days))!=len(days):
        raise ValueError('duplicate source trading day')
    metadata=dict(provenance)|{'availability':'RECONSTRUCTED_17H_UNVERIFIED',
        'calendar':'observed source dates, not independently verified full exchange calendar',
        'volume_unit':'provider raw, unverified; not used for capacity',
        'limitations':['single current-surviving security','corporate actions not audited','historical publication/arrival unknown',
                        'limits and suspension status assumed','not eligible for financial-efficacy claims']}
    return {'dataset_id':f'tencent_raw_{symbol}_{start}_{end}', 'evidence_level':'REAL_PRICE_ENGINEERING_ONLY',
            'provenance':metadata,'sessions':days,'records':output}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--symbol',default='600519')
    parser.add_argument('--start',default='2024-01-01')
    parser.add_argument('--end',default='2024-03-31')
    parser.add_argument('--output',required=True)
    parser.add_argument('--raw-response',help='import a previously captured original JSON instead of networking')
    args=parser.parse_args()
    exchange='sh' if args.symbol.startswith('6') else 'sz'
    url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urlencode({'param':f'{exchange}{args.symbol},day,{args.start},{args.end},320,'})
    if args.raw_response:
        raw=Path(args.raw_response).read_bytes()
    else:
        request=Request(url,headers={'User-Agent':'stock-rsi-lab/0.1 research','Referer':'https://gu.qq.com/'})
        with urlopen(request,timeout=30) as response:
            raw=response.read(5000000)
    metadata={'source':'Tencent public fqkline raw day','request_url':url,
              'captured_at':datetime.now(timezone.utc).isoformat(), 'source_sha256':hashlib.sha256(raw).hexdigest(),
              'imported_from_capture':bool(args.raw_response)}
    data=convert(json.loads(raw),args.symbol,args.start,args.end,metadata)
    output=Path(args.output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'source.response.json').write_bytes(raw)
    (output/'dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    (output/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    print(json.dumps({'rows':len(data['records']),'dataset':str(output/'dataset.json'),'evidence_level':data['evidence_level']},ensure_ascii=False))


if __name__=='__main__':main()
