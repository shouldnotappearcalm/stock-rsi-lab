"""Two-stage fixed-policy nested execution experiment; no alpha search."""
import argparse
import csv
import json
from datetime import date
from functools import partial
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.capture_low_risk_raw_account_data import START, END, EXPECTED_TARGET_SHA256
from scripts.run_low_risk_raw_share_validation import CAPITALS, clean, canonical_distributions, simulate_fixed_targets, summarize_case
from scripts.tdx_history_checks import inspect_minutes
from stock_rsi.calendar import TradingCalendar
from stock_rsi.intraday_broker import IntradayBroker
from stock_rsi.intraday_tape import aggregate_minutes
from stock_rsi.raw_share_account import RawShareAccount


PARTICIPATION=(100,500,1000)
EXTRA_BPS=(0,5,10,20,40)
RAW_SHA='4177efc8615eca4a53fec13161087ca9329b8f1448bc75a41e94179cb368f19a'
PROOF_SHA='ef97c73712072ed58a05dceea01cc041063a013f8229defbe22d25089a4d1c25'
METHOD_FILES=('scripts/run_low_risk_intraday_replay.py','scripts/run_low_risk_raw_share_validation.py',
 'scripts/capture_cninfo_csi500_reports_pre2026.py','scripts/capture_low_risk_raw_account_data.py','scripts/tdx_history_checks.py',
 'src/stock_rsi/intraday_broker.py','src/stock_rsi/intraday_tape.py','src/stock_rsi/raw_share_account.py',
 'src/stock_rsi/execution_cost.py','src/stock_rsi/broker.py','src/stock_rsi/models.py','src/stock_rsi/data.py',
 'src/stock_rsi/calendar.py','src/stock_rsi/time.py')


class TapeBank:
    def __init__(self,old,extra,bars,end):
        self.index={};self.cache={};self.accessed=set();self.bars=bars;self.end=end
        for root in (old,extra):
            manifest=json.loads((root/'manifest.json').read_text())
            if sha256_file(root/'plan.json')!=manifest['plan_sha256']:raise ValueError('tape plan changed')
            for name,expected in manifest['per_session_sha256'].items():
                if Path(name).name!=name:raise ValueError('tape filename changed')
                key=tuple(name[:-5].split('-',1))
                if key in self.index:raise ValueError('duplicate historical tape key')
                self.index[key]=(root/'sessions'/name,expected)

    def __call__(self,code,day):
        key=(code,day.isoformat())
        if day.isoformat()>self.end:raise ValueError('future tape access rejected by phase cutoff')
        self.accessed.add(key)
        if key in self.cache:return self.cache[key]
        if key not in self.index:raise ValueError('missing required prefix tape '+str(key))
        path,expected=self.index[key]
        if sha256_file(path)!=expected:raise ValueError('historical tape bytes changed')
        packet=json.loads(path.read_text())
        if packet['instrument']!=code or packet['requested_day']!=day.isoformat():raise ValueError('tape identity changed')
        record=packet.get('methods',{}).get('minutes.history',packet)
        if record['status']!='RESPONSE_CAPTURED':raise ValueError('historical minute source unavailable')
        value=record['response'];facts=inspect_minutes(code,day.isoformat(),value,self.bars[code][day.isoformat()])
        if not facts['last_close_matches'] or facts['traded_points_outside_daily_range']:
            raise ValueError('historical minute price signature conflicts with raw day')
        rows=aggregate_minutes(code,day,value['points'])
        if sum(r['volume_lower_shares'] for r in rows)>int(self.bars[code][day.isoformat()]['volume']):
            raise ValueError('stressed minute volume exceeds whole-day source')
        self.cache[key]=rows
        return rows


def write_case(folder,case):
    with (folder/'daily.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(case['days'][0]));writer.writeheader();writer.writerows(case['days'])
    for key in ('intents','parent_instructions','orders','fills','corporate_ledger','ownership'):
        (folder/(key+'.json')).write_text(json.dumps(clean(case[key]),indent=2)+'\n')
    return {p.name:sha256_file(p) for p in sorted(folder.iterdir())}


def compare_development_prefix(folder,development_folder):
    with (folder/'daily.csv').open() as f:full=list(csv.DictReader(f))
    with (development_folder/'daily.csv').open() as f:dev=list(csv.DictReader(f))
    if [row for row in full if row['day']<'2026-01-01']!=dev:
        raise RuntimeError('intraday development financial prefix changed in full replay')
    for name,clock in (('orders.json','submitted_at'),('fills.json','execution_at')):
        full_rows=json.loads((folder/name).read_text());dev_rows=json.loads((development_folder/name).read_text())
        if [row for row in full_rows if row[clock]<'2026-01-01']!=dev_rows:
            raise RuntimeError('intraday development child/fill prefix changed')


def authenticate_development(development,plan):
    """Authenticate every consumed control artifact before opening 2026 tapes."""
    if sha256_file(development/'summary.json')!=plan['development_summary_sha256']:
        raise ValueError('development result changed')
    prior=json.loads((development/'summary.json').read_text())
    if prior['phase']!='dev' or prior['method_code_sha256']!=plan['method_code_sha256']:
        raise ValueError('development method mismatch')
    expected={f'{p}/{e}/{c}' for p in PARTICIPATION for e in EXTRA_BPS for c in CAPITALS}
    if set(prior['results_by_profile'])!=expected:raise ValueError('development profile matrix changed')
    artifacts={'daily.csv','intents.json','parent_instructions.json','orders.json','fills.json','corporate_ledger.json','ownership.json'}
    for label,result in prior['results_by_profile'].items():
        if result['status']=='INVALID_SOURCE_OR_ACCOUNT':continue
        if result['status']!='NESTED_EXECUTION_ACCOUNT_RECONCILED' or set(result['artifact_sha256'])!=artifacts:
            raise ValueError('development artifact schema changed')
        for name,expected_hash in result['artifact_sha256'].items():
            path=development/label/name
            if not path.is_file() or sha256_file(path)!=expected_hash:
                raise ValueError('development artifact changed: '+label+'/'+name)
    return prior['results_by_profile']


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('dev','full'),required=True)
    for name in ('raw-data-dir','proof-dir','targets','old-tape-dir','prefix-tape-dir','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--development-dir');args=parser.parse_args(argv)
    root=Path(__file__).resolve().parents[1];output=Path(args.output_dir)
    if output.exists():raise ValueError('intraday output already exists')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('intraday plan changed')
    plan=json.loads(Path(args.plan).read_text())
    expected_status='INTRADAY_DEVELOPMENT_METHOD_REGISTERED' if args.phase=='dev' else 'FROZEN_BEFORE_INTRADAY_2026_OUTCOMES'
    if (plan['status']!=expected_status or plan['participation_bps']!=list(PARTICIPATION) or plan['extra_bps']!=list(EXTRA_BPS)
            or plan['capitals']!=list(CAPITALS) or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())
            or any(sha256_file(root/name)!=value for name,value in plan['frozen_economic_core_sha256'].items())):
        raise ValueError('intraday method or economic rules changed')
    raw,proof_dir,old,extra=map(Path,(args.raw_data_dir,args.proof_dir,args.old_tape_dir,args.prefix_tape_dir))
    if (sha256_file(raw/'manifest.json')!=RAW_SHA or sha256_file(proof_dir/'manifest.json')!=PROOF_SHA
            or sha256_file(args.targets)!=EXPECTED_TARGET_SHA256
            or sha256_file(old/'manifest.json')!=plan['old_tape_manifest_sha256']
            or sha256_file(extra/'manifest.json')!=plan['prefix_tape_manifest_sha256']):
        raise ValueError('intraday source identity changed')
    development=None;development_results=None
    if args.phase=='full':
        if not args.development_dir:raise ValueError('development control required before 2026')
        development=Path(args.development_dir)
        development_results=authenticate_development(development,plan)
    end='2025-12-31' if args.phase=='dev' else END
    manifest=json.loads((raw/'manifest.json').read_text());proof=json.loads((proof_dir/'manifest.json').read_text())
    for document in proof['documents']:
        if Path(document['file']).name!=document['file'] or sha256_file(proof_dir/document['file'])!=document['sha256']:
            raise ValueError('corporate notice changed')
    if sha256_file(raw/'calendar.json')!=manifest['calendar_sha256']:raise ValueError('calendar changed')
    calendar=TradingCalendar([day for day in json.loads((raw/'calendar.json').read_text())['sessions'] if day<=end])
    packets={}
    for code,expected in manifest['per_code_sha256'].items():
        path=raw/'codes'/(code+'.json')
        if sha256_file(path)!=expected:raise ValueError('raw market packet changed')
        packet=json.loads(path.read_text())
        if packet['instrument']!=code:raise ValueError('raw security identity changed')
        packet['bars']=[row for row in packet['bars'] if row['date']<=end]
        packet['distributions']=[row for row in packet['distributions'] if row['dividPlanDate'] and row['dividPlanDate']<=end]
        if [row['date'] for row in packet['bars']]!=[day.isoformat() for day in calendar.days]:raise ValueError('session coverage changed')
        packets[code]=packet
    events=canonical_distributions(packets,proof);bars={code:{r['date']:r for r in p['bars']} for code,p in packets.items()}
    targets={day:t for day,t in json.loads(Path(args.targets).read_text()).items() if day<=end}
    bank=TapeBank(old,extra,bars,end);output.mkdir(parents=True);results={}
    for participation in PARTICIPATION:
        for extra_bps in EXTRA_BPS:
            for capital in CAPITALS:
                label=f'{participation}/{extra_bps}/{capital}';folder=output/label;folder.mkdir(parents=True)
                print('intraday '+args.phase+' '+label,flush=True);holders=[]
                if development_results is not None and development_results[label]['status']=='INVALID_SOURCE_OR_ACCOUNT':
                    results[label]={'status':'DEVELOPMENT_INVALID_NOT_RUN_2026','error':development_results[label]['error']}
                    (folder/'error.json').write_text(json.dumps(results[label],indent=2)+'\n')
                    continue
                def factory(cal,cash,distributions,**kwargs):
                    constructor=partial(IntradayBroker,participation_bps=participation,extra_cost_bps=extra_bps,tape_provider=bank)
                    account=RawShareAccount(cal,cash,distributions,broker_factory=constructor,**kwargs);holders.append(account.broker);return account
                try:
                    case=simulate_fixed_targets(calendar,bars,events,targets,capital,account_factory=factory)
                    case['parent_instructions']=case.pop('orders');case['orders']=holders[0].child_orders
                    if len(case['intents'])!=(24 if args.phase=='dev' else 34):raise ValueError('all registered monthly signals required')
                    artifacts=write_case(folder,case)
                    if development is not None:compare_development_prefix(folder,development/label)
                    parents=case['parent_instructions'];wanted=sum(p['quantity'] for p in parents);filled=sum(p['filled_quantity'] for p in parents)
                    results[label]={'status':'NESTED_EXECUTION_ACCOUNT_RECONCILED',**summarize_case(case,capital),
                        'parent_instructions':len(parents),'parent_fill_share_fraction':filled/wanted if wanted else 1,
                        'unfilled_parent_instructions':sum(p['remaining']>0 for p in parents),
                        'actual_children_within_one_million_shares':all(c['quantity']<=1000000 for c in case['orders']),
                        'development_prefix_reproduced':development is not None,'artifact_sha256':artifacts}
                except (ValueError,KeyError) as exc:
                    results[label]={'status':'INVALID_SOURCE_OR_ACCOUNT','error':str(exc)}
                    (folder/'error.json').write_text(json.dumps(results[label],indent=2)+'\n')
                (output/'case_results.json').write_text(json.dumps(results,indent=2)+'\n')
    result={'status':'INTRADAY_FIXED_POLICY_SCENARIOS','phase':args.phase,'end':end,'results_by_profile':results,
        'method_code_sha256':plan['method_code_sha256'],'plan_sha256':args.expected_plan_sha256,
        'tape_accessed_sessions':len(bank.accessed),'tape_access_after_phase_cutoff':False,
        'source_evidence_level':'RECONSTRUCTED_ENGINEERING_SIMULATION','new_alpha_candidates':0,
        'execution':'prior-bucket sized children; per-child costs; sampled adverse current prices; capped participation',
        'queue_and_impact_calibrated':False,'historical_arrival_verified':False,'complete_requested_October':False,
        'original_research_gate_status':'REJECTED','sealed_evidence':False,'objective_achieved':False}
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print('intraday phase complete',args.phase,flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
