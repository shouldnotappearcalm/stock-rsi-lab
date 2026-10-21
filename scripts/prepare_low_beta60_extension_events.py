"""Append 2026 evaluator events without rewriting frozen pre2026 economics."""
import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

from scripts.prepare_low_beta60_account_sources import METHOD_FILES as OLD_METHODS,file_sha,verify_packet
from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2
from stock_rsi.stock_distribution_account import StockDistributionAccount

START,END='2023-12-29','2026-10-13'
METHOD_FILES=(*OLD_METHODS,'scripts/prepare_low_beta60_extension_events.py')
LOCAL_FILES=('low-beta60-raw-dev-20261021/manifest.json','low-beta60-raw-dev-20261021/calendar.json',
 'low-beta60-raw-extension-20261021/manifest.json','low-beta60-raw-extension-20261021/calendar.json',
 'low-beta60-raw-extension-independent-audit-20261021.json',
 'low-beta60-account-source-events-20261021/summary.json',
 'low-beta60-account-source-events-20261021/effective_proofs.json',
 'low-beta60-account-source-events-20261021/derived_events.json',
 'low-beta60-account-source-events-20261021/event_source_receipts.json',
 'low-beta60-event-source-independent-audit-20261021.json',
 'low-beta60-corporate-reviewed-20261021/reviewed-manifest.json',
 'low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json',
 'low-beta60-corporate-2026-20261021/manifest.json',
 'low-beta60-2026-corporate-independent-audit-20261021.json',
 'low-beta60-calendar-extension-formations-20261021/targets.json')
PUBLIC_FILES=('experiments/qlib/low-beta60-raw-extension-independent-audit.json',
 'experiments/qlib/low-beta60-event-source-independent-audit.json',
 'experiments/qlib/low-beta60-2026-corporate-reviewed-manifest.json',
 'experiments/qlib/low-beta60-2026-corporate-content-review.json',
 'experiments/qlib/low-beta60-2026-corporate-proof-projection-review.json',
 'docs/research/low-beta60-extension-event-plan-2026-10-21.md')


def serialize_event(event):
    return {k:str(v) if isinstance(v,(date,Decimal)) else v for k,v in asdict(event).items()}


def canonical_day(text):
    if not isinstance(text,str) or date.fromisoformat(text).isoformat()!=text:
        raise ValueError('canonical source date required')
    return text


def compile_append_only(old_packets,old_proofs,old_events,old_receipts,extended_packets,new_proofs,calendar):
    old_calendar=TradingCalendar([d.isoformat() for d in calendar.days if d<date(2026,1,1)])
    events,receipts=compile_distribution_events_v2(old_packets,old_proofs,old_calendar)
    if [serialize_event(e) for e in events]!=old_events or list(receipts)!=old_receipts:
        raise ValueError('original economic event/receipt reconstruction differs')
    if not set(old_packets)<=set(extended_packets):raise ValueError('original source name missing')
    for code,packet in old_packets.items():
        for field,daykey in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
            prefix=[r for r in extended_packets[code].get(field,[]) if canonical_day(r[daykey])<'2026-01-01']
            if prefix!=packet.get(field,[]):raise ValueError('original raw source prefix changed')
    unresolved=new_proofs.get('unresolved_tax',{})
    if (not isinstance(unresolved,dict) or any(v.get('verified_exempt') is not False for v in unresolved.values())
            or set(unresolved)&set(new_proofs.get('capital_tax',{}))):
        raise ValueError('unresolved tax cannot be silently upgraded')
    projected={};ignored=0
    for code,packet in extended_packets.items():
        if packet['instrument']!=code:raise ValueError('extension issuer identity changed')
        selected=[]
        for row in packet['distributions']:
            ex=canonical_day(row['dividOperateDate'])
            if ex<'2026-01-01':
                if code not in old_packets:ignored+=1
                continue
            if ex>calendar.days[-1].isoformat() or canonical_day(row['dividRegistDate'])<'2026-01-01':
                raise ValueError('extension event outside cutoff or crosses old record-date prefix')
            selected.append(row)
        projected[code]={'instrument':code,'distributions':selected}
    for item in new_proofs.get('supplementary_distributions',[]):
        r=item['record']
        if not '2026-01-01'<=canonical_day(r['dividRegistDate'])<canonical_day(r['dividOperateDate'])<=calendar.days[-1].isoformat():
            raise ValueError('supplement crosses original year or requested cutoff')
    appended,extra_receipts=compile_distribution_events_v2(projected,new_proofs,calendar)
    unsafe=sorted(r['instrument']+'|'+r['ex_date'] for r in extra_receipts if r['requires_zero_record_ownership_if_tax_unverified'])
    if unsafe!=sorted(unresolved):raise ValueError('unverified source events must match explicit unresolved markers exactly')
    combined=tuple(events)+tuple(appended);combined_receipts=tuple(receipts)+tuple(extra_receipts)
    StockDistributionAccount(calendar,'1',combined,tax_reserve_rate='.2')
    return combined,combined_receipts,{'original_events':len(events),'appended_events':len(appended),
        'earlier_rows_of_future_only_names_ignored':ignored,'unverified_tax_event_keys':unsafe}


def load_packets(directory,manifest,sessions,*,old=False):
    packets={}
    for code,h in manifest['per_code_sha256'].items():
        f=directory/'codes'/(code+'.json')
        if Path(code).name!=code or file_sha(f)!=h:raise ValueError('authenticated source packet changed')
        packet=json.loads(f.read_bytes())
        if old:verify_packet(code,packet,sessions)
        elif packet['instrument']!=code or packet['window']!=[START,END] or [r['date'] for r in packet['bars']]!=sessions:
            raise ValueError('full extension source/calendar required')
        packets[code]=packet
    return packets


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('plan','expected-plan-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve prior source compilation')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('external event plan SHA changed')
    plan=json.loads(Path(a.plan).read_bytes())
    if (plan['status']!='FROZEN_LOW_BETA60_APPEND_ONLY2026_EVENTS_NO_ROI'
            or plan['window']!=[START,END] or plan['unconditional_interim_observation_end']!='2026-10-20'
            or plan['portfolio_returns_to_compute'] is not False or plan['source_queries_allowed'] is not False
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or set(plan['local_source_sha256'])!=set(LOCAL_FILES)
            or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES)):
        raise ValueError('append-only method/scope changed')
    for bindings,parent in ((plan['method_code_sha256'],repo),(plan['local_source_sha256'],base),
                            (plan['public_evidence_sha256'],repo)):
        for f,h in bindings.items():
            if Path(f).is_absolute() or '..' in Path(f).parts or file_sha(parent/f)!=h:
                raise ValueError('frozen source or method bytes changed')
    original=base/'low-beta60-raw-dev-20261021';extension=base/'low-beta60-raw-extension-20261021'
    om=json.loads((original/'manifest.json').read_bytes());em=json.loads((extension/'manifest.json').read_bytes())
    os=json.loads((original/'calendar.json').read_bytes())['sessions'];es=json.loads((extension/'calendar.json').read_bytes())['sessions']
    if (len(os)!=486 or len(es)!=671 or es!=sorted(set(es)) or es[:486]!=os or [es[0],es[-1]]!=[START,END]
            or om['calendar_sha256']!=file_sha(original/'calendar.json')
            or em['calendar_sha256']!=file_sha(extension/'calendar.json')):
        raise ValueError('original/extended explicit session prefix changed')
    old=load_packets(original,om,os,old=True);new=load_packets(extension,em,es)
    targets_path=base/'low-beta60-calendar-extension-formations-20261021/targets.json'
    targets=json.loads(targets_path.read_bytes())['low_beta60']
    if (len(old)!=69 or len(new)!=79 or len(targets)!=34 or em['target_sha256']!=file_sha(targets_path)
            or {c for t in targets.values() for c in t['weights']}!=set(new)):
        raise ValueError('same full79-name/34-target source scope required')
    source=base/'low-beta60-account-source-events-20261021';ss=json.loads((source/'summary.json').read_bytes())
    for name,h in ss['artifact_sha256'].items():
        if Path(name).name!=name or file_sha(source/name)!=h:raise ValueError('original source-event artifact changed')
    old_proofs=json.loads((source/'effective_proofs.json').read_bytes())
    proof_dir=base/'low-beta60-corporate-reviewed-2026-20261021';proofs=json.loads((proof_dir/'reviewed-manifest.json').read_bytes())
    if (proofs['raw_manifest_sha256']!=file_sha(extension/'manifest.json') or proofs['strict_tax_questions_remaining']!=1
            or proofs['event_compilation_admitted'] is not False or proofs['portfolio_returns_computed'] is not False):
        raise ValueError('separate reviewed evidence proposal and unresolved tax required')
    for proposal,parent in ((old_proofs,base/'low-beta60-corporate-reviewed-20261021'),(proofs,proof_dir)):
        for d in proposal['documents']:
            if Path(d['file']).name!=d['file'] or file_sha(parent/d['file'])!=d['sha256']:
                raise ValueError('original reviewed primary PDF changed')
    old_events=json.loads((source/'derived_events.json').read_bytes());old_receipts=json.loads((source/'event_source_receipts.json').read_bytes())
    events,receipts,stats=compile_append_only(old,old_proofs,old_events,old_receipts,new,proofs,TradingCalendar(es))
    if (stats!={'original_events':179,'appended_events':87,'earlier_rows_of_future_only_names_ignored':25,
                'unverified_tax_event_keys':['SZ000937|2026-06-17']} or len(events)!=266):
        raise ValueError('complete original and 2026 source-event reconciliation required')
    out.mkdir(parents=True)
    for name in ('derived_events.json','event_source_receipts.json'):
        (out/('original_'+name)).write_bytes((source/name).read_bytes())
    artifacts={'derived_events.json':[serialize_event(e) for e in events],
        'event_source_receipts.json':list(receipts),'effective_2026_proofs.json':proofs}
    for name,value in artifacts.items():
        with (out/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    summary={'status':'LOW_BETA60_266_SOURCE_EVENTS_COMPILED_ONE_TAX_GUARD_RETAINED_INDEPENDENT_AUDIT_PENDING',
        'plan_sha256':a.expected_plan_sha256,'window':[START,END],**stats,'compiled_events':len(events),
        'raw_manifest_sha256':file_sha(extension/'manifest.json'),
        'reviewed_2026_manifest_sha256':file_sha(proof_dir/'reviewed-manifest.json'),
        'source_kind_counts':{kind:sum(r['source_kind']==kind for r in receipts) for kind in
            ('VENDOR_DISTRIBUTION','PRIMARY_NOTICE_SUPPLEMENT','PRIMARY_CASH_PRECISION_CORRECTION')},
        'all_original_events_and_receipts_reconstructed_unchanged':True,
        'original_source_files_modified':False,'unknown_tax_requires_zero_registered_ownership':True,
        'artifact_sha256':{name:file_sha(out/name) for name in [*artifacts,'original_derived_events.json','original_event_source_receipts.json']},
        'source_queries':0,'event_compilation_independently_verified':False,'account_replay_admitted':False,
        'historical_arrival_verified':False,'actual_FIFO_tax_liability_verified':False,
        'full_corporate_actions_certified':False,'portfolio_returns_computed':False,
        'full_requested_October_complete':False,'candidate_promoted':False,'objective_achieved':False}
    with (out/'summary.json').open('x') as f:json.dump(summary,f,ensure_ascii=False,indent=2);f.write('\n')
    print('compiled266events; original179 unchanged; one tax guard retained; no ROI',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
