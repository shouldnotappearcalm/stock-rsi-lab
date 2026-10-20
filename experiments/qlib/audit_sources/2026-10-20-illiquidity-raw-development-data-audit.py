"""Source diagnostics only; reuses the frozen shared coverage checker.

Not an independent financial audit, not a portfolio replay or PIT certificate.
Every original exception is recorded rather than corrected here.
"""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from scripts.capture_frozen_target_development_data import target_codes
from scripts.run_low_risk_raw_share_validation import validate_source_coverage


def main():
    parser=argparse.ArgumentParser()
    for n in ('raw-dir','targets','request','output'):parser.add_argument('--'+n,required=True)
    args=parser.parse_args();raw=Path(args.raw_dir);out=Path(args.output)
    assert not out.exists();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest=json.loads((raw/'manifest.json').read_text());request=json.loads(Path(args.request).read_text())
    targets=json.loads(Path(args.targets).read_text());codes=target_codes(targets)
    assert codes==request['codes']==sorted(manifest['per_code_sha256'])
    assert manifest['request_sha256']==sha(args.request)
    assert manifest['target_sha256']==sha(args.targets)==request['target_sha256']
    assert manifest['window']==['2023-12-29','2025-12-31']
    assert sha(raw/'calendar.json')==manifest['calendar_sha256']
    sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    assert sessions==sorted(set(sessions)) and len(sessions)==486
    first={}
    for day,target in sorted(targets.items()):
        for c in target['weights']:first.setdefault(c,day)
    coverage=[];components=[];states=[];quarantine=[];incomplete=[]
    for code in codes:
        p=raw/'codes'/(code+'.json');assert sha(p)==manifest['per_code_sha256'][code]
        packet=json.loads(p.read_text())
        assert packet['instrument']==code and packet['window']==manifest['window']
        observed=[r['date'] for r in packet['bars']]
        assert observed==sorted(set(observed)) and set(observed)<=set(sessions)
        if observed!=sessions:
            incomplete.append({'instrument':code,'observed_rows':len(observed),
                'first_observed_session':observed[0] if observed else None,
                'missing_sessions':[d for d in sessions if d not in set(observed)],
                'first_target_day':first[code],'prelisting_not_automatically_admitted':True})
        try:validate_source_coverage({code:packet})
        except ValueError as exc:coverage.append({'instrument':code,'error':str(exc)})
        for row in packet['distributions']:
            assert '2023-12-29'<=row['dividOperateDate']<='2025-12-31'
            if Decimal(row['dividStocksPs'] or '0')!=0 or Decimal(row['dividReserveToStockPs'] or '0')!=0:
                components.append({'instrument':code,'first_target_day':first[code],
                    'record_date':row['dividRegistDate'],'record_precedes_first_possible_buy':row['dividRegistDate']<first[code],
                    'source_record':row,'primary_tax_or_zero_entitlement_proof_required':True})
        for r in packet['bars']:
            if r['isST']!='0' and r['date']>=first[code]:
                states.append({'instrument':code,'day':r['date'],'isST':r['isST'],
                    'interpretation':'Potentially outside supported ordinary-stock account; no holding or execution inferred'})
        quarantine.extend({'instrument':code,**q} for q in packet['quarantine'])
    result={'status':'ILLIQUIDITY_RAW_DEVELOPMENT_SOURCE_DIAGNOSTICS_COMPLETE',
        'raw_manifest_sha256':sha(raw/'manifest.json'),'target_sha256':sha(args.targets),
        'request_sha256':sha(args.request),'audit_source_sha256':sha(__file__),
        'shared_coverage_code_sha256':sha('scripts/run_low_risk_raw_share_validation.py'),
        'window':manifest['window'],'names':len(codes),'expected_calendar_rows_per_name':len(sessions),
        'incomplete_source_calendars':incomplete,
        'original_source_totals':manifest['totals'],'coverage_exceptions':coverage,
        'noncash_components_requiring_review':components,'potential_unsupported_state_rows':states,
        'quarantined_source_rows':quarantine,'all_original_packets_unchanged':True,
        'shared_coverage_checker_used':True,'independent_financial_audit':False,
        'no_source_exception_alone_promotes_or_deletes_a_stock':True,
        'raw_share_or_intraday_return_computed':False,'2026_values_queried':False,
        'historical_arrival_verified':False,'objective_achieved':False}
    out.write_text(json.dumps(result,indent=2)+'\n')
    print('source diagnostics',len(codes),'names;',len(coverage),'coverage exceptions;',
        len(components),'noncash distributions;',len(states),'potential unsupported-state rows')


if __name__=='__main__':main()
