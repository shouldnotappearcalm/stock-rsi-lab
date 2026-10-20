"""Read only the already captured 12-name pre2026 pilot; no portfolio outcomes.

Unit discovery happened in a preliminary read-only comparison before this
script. The fixed conversion is documented upstream, not estimated from ROI.
This script preserves all discrepancies, and certifies only this small sample.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def audit(provider, pilot):
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest=json.loads((pilot/'manifest.json').read_text())
    assert manifest['window']==['2023-12-29','2025-12-31']
    assert len(manifest['codes'])==12 and len(set(manifest['codes']))==12
    calendar=(provider/'calendars/day.txt').read_text().splitlines()
    indices={d:i for i,d in enumerate(calendar)};results={}
    for code in manifest['codes']:
        packet=pilot/'codes'/(code+'.json');assert sha(packet)==manifest['per_code_sha256'][code]
        data=json.loads(packet.read_text())['raw_daily']
        path=provider/'features'/code.lower()/'amount.day.bin'
        raw=path.read_bytes();values=struct.unpack('<'+'f'*(len(raw)//4),raw)
        begin=int(values[0]);assert begin==values[0]
        counts={'source_rows':0,'inactive_rows':0,'active_rows':0,'matched':0,'mismatched':0,'missing':0}
        differences=[];maximum_error=0.
        for fields in data['rows']:
            row=dict(zip(data['fields'],fields));day=row['date']
            assert '2023-12-29'<=day<='2025-12-31' and row['code']==code[:2].lower()+'.'+code[2:]
            counts['source_rows']+=1
            if row['tradestatus']!='1' or not row['amount'] or float(row['amount'])<=0:
                counts['inactive_rows']+=1;continue
            counts['active_rows']+=1;offset=indices[day]-begin
            q=values[1+offset] if 0<=offset<len(values)-1 else math.nan
            if not math.isfinite(q) or q<=0:counts['missing']+=1;continue
            expected=float(row['amount']);actual=q*1000
            error=abs(actual/expected-1);maximum_error=max(maximum_error,error)
            if math.isclose(actual,expected,rel_tol=1e-6,abs_tol=1):counts['matched']+=1
            else:
                counts['mismatched']+=1
                differences.append({'day':day,'qlib_thousand_CNY':q,'raw_amount_CNY':row['amount'],'relative_error':error})
        results[code]={**counts,'maximum_relative_error':maximum_error,'differences':differences,
            'pilot_packet_sha256':sha(packet),'qlib_amount_binary_sha256':sha(path)}
    admitted=all(r['matched']>=480 and r['missing']==r['mismatched']==0 for r in results.values())
    return {'status':'PRE2026_AMOUNT_UNIT_SAMPLE_AUDITED','conversion_CNY_per_source_unit':1000,
        'preflight_unit_discovery_before_script_registration':True,
        'unit_documentation':'https://tushare.pro/document/2?doc_id=27',
        'upstream_normalizer':'https://github.com/chenditc/investment_data/blob/b8c129b4d9b838f050eac8b1135111b3b79fc894/qlib/normalize.py#L30',
        'pilot_manifest_sha256':sha(pilot/'manifest.json'),'calendar_sha256':sha(provider/'calendars/day.txt'),
        'audit_source_sha256':sha(__file__),'window':manifest['window'],'sample_names':len(results),
        'all_active_sample_rows_match_CNY_conversion':admitted,'results_by_code':results,
        'scope':'Amount unit check on preexisting12-name pilot only; not full-universe quote truth or historical arrival certification',
        'full_universe_amount_truth_verified':False,'historical_arrival_verified':False,
        '2026_market_values_queried':False,'portfolio_outcomes_computed':False,'objective_achieved':False}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('provider-uri','pilot','output'):p.add_argument('--'+n,required=True)
    args=p.parse_args();out=Path(args.output);assert not out.exists()
    result=audit(Path(args.provider_uri),Path(args.pilot));out.write_text(json.dumps(result,indent=2)+'\n')
    print('amount unit audit',result['all_active_sample_rows_match_CNY_conversion'],
        sum(r['matched'] for r in result['results_by_code'].values()),'active observations')
