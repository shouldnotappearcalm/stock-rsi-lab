"""Authenticate and compile frozen pre2026 source events, without portfolio ROI."""
import argparse
import copy
from dataclasses import asdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from stock_rsi.calendar import TradingCalendar
from stock_rsi.distribution_event_compiler_v2 import CONTRACT,compile_distribution_events_v2

START,END='2023-12-29','2025-12-31'
METHOD_FILES=('scripts/prepare_price_delay_account_sources_pre2026.py',
 'src/stock_rsi/distribution_event_compiler_v2.py','src/stock_rsi/distribution_event_compiler.py',
 'src/stock_rsi/stock_distribution_account.py','src/stock_rsi/raw_share_account.py',
 'src/stock_rsi/broker.py','src/stock_rsi/calendar.py','src/stock_rsi/data.py',
 'src/stock_rsi/models.py','src/stock_rsi/time.py')
LOCAL_FILES=('price-delay-raw-dev-20261021/manifest.json','price-delay-raw-dev-20261021/calendar.json',
 'price-delay-pre2026-formations-20261021/targets.json',
 'price-delay-corporate-reviewed-20261021/reviewed-manifest.json',
 'price-delay-primary-capture-audit-20261021.json',
 'price-delay-corporate-primary-20261021/manifest.json',
 'budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json',
 'illiquidity-corporate-reviewed-20261020/reviewed-manifest.json',
 'return-family-corporate-notices-20261017/reviewed-manifest.json',
 'szse-value-corporate-notices-20261017/reviewed-manifest.json')
PUBLIC_FILES=('experiments/qlib/price-delay-raw-source-independent-audit.json',
 'experiments/qlib/price-delay-corporate-reviewed-manifest.json',
 'experiments/qlib/price-delay-primary-capture-independent-audit.json',
 'experiments/qlib/price-delay-primary-content-review.json',
 'experiments/qlib/price-delay-primary-noncash-content-review.json',
 'experiments/qlib/price-delay-primary-adjustment-content-review.json',
 'docs/research/price-delay-source-event-plan-2026-10-21.md')


def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_packet(code,packet,sessions):
    if (packet['instrument']!=code or packet['window']!=[START,END]
            or [r['date'] for r in packet['bars']]!=sessions
            or any(not START<=r['date']<=END for r in packet['bars'])):
        raise ValueError('complete fixed security/calendar without future rows required')


def project_proofs(original,source_sha):
    if (original.get('cash_override_contract')!=CONTRACT
            or original.get('event_compilation_admitted') is not False
            or original.get('admitted_for_account_replay') is not False):
        raise ValueError('only the separately frozen source-review proposal may be projected')
    result=copy.deepcopy(original)
    result.update(status='EVALUATOR_SOURCE_PROJECTION_NO_ACCOUNT_ADMISSION',
        original_cash_override_contract_label=original['cash_override_contract'],
        cash_override_contract=CONTRACT,source_reviewed_manifest_sha256=source_sha)
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('plan','expected-plan-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir)
    if out.exists():raise ValueError('preserve previous source compilation')
    if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('source compilation plan changed')
    plan=json.loads(Path(a.plan).read_text())
    if (plan['status']!='FROZEN_PRICE_DELAY_EVENT_SOURCE_COMPILATION_NO_ROI' or plan['window']!=[START,END]
            or plan['cash_override_contract']!=CONTRACT or plan['portfolio_returns_to_compute'] is not False
            or plan['new_2026_queries_allowed'] is not False
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or set(plan['local_source_sha256'])!=set(LOCAL_FILES)
            or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES)):
        raise ValueError('source compilation method/scope changed')
    for bindings,root in ((plan['method_code_sha256'],repo),(plan['local_source_sha256'],base),
                          (plan['public_evidence_sha256'],repo)):
        if any(file_sha(root/f)!=h for f,h in bindings.items()):raise ValueError('frozen source or code bytes changed')
    raw=base/'price-delay-raw-dev-20261021';reviewed=base/'price-delay-corporate-reviewed-20261021'
    m=json.loads((raw/'manifest.json').read_text());proof_path=reviewed/'reviewed-manifest.json'
    proposal=json.loads(proof_path.read_text());sessions=json.loads((raw/'calendar.json').read_text())['sessions']
    if (len(sessions)!=486 or sessions!=sorted(set(sessions)) or [sessions[0],sessions[-1]]!=[START,END]
            or file_sha(raw/'calendar.json')!=m['calendar_sha256']
            or proposal['raw_manifest_sha256']!=file_sha(raw/'manifest.json')
            or proposal['target_sha256']!=m['target_sha256']):raise ValueError('raw source calendar/identity changed')
    target_path=base/'price-delay-pre2026-formations-20261021/targets.json'
    if file_sha(target_path)!=m['target_sha256']:raise ValueError('original target identity changed')
    targets=json.loads(target_path.read_text())['price_delay_d1']
    codes=sorted({c for t in targets.values() for c in t['weights']})
    if (len(targets)!=24 or len(codes)!=151 or set(codes)!=set(m['per_code_sha256'])
            or any(day not in sessions or t['as_of'] not in sessions or not t['as_of']<day
                   for day,t in targets.items())):raise ValueError('complete frozen monthly target scope required')
    packets={}
    for code,h in m['per_code_sha256'].items():
        path=raw/'codes'/(code+'.json')
        if file_sha(path)!=h:raise ValueError('raw packet changed')
        packet=json.loads(path.read_text());verify_packet(code,packet,sessions);packets[code]=packet
    if len(proposal['documents'])!=15:raise ValueError('all fifteen original source documents required')
    for d in proposal['documents']:
        if Path(d['file']).name!=d['file'] or file_sha(reviewed/d['file'])!=d['sha256']:
            raise ValueError('reviewed original PDF changed')
    content=json.loads((repo/'experiments/qlib/price-delay-primary-content-review.json').read_text())
    if (content['scoped_primary_content_review_completed'] is not True
            or content['documents_read']!=15 or content['pages_read']!=54
            or content['capture_manifest_sha256']!=file_sha(base/'price-delay-corporate-primary-20261021/manifest.json')
            or any(file_sha(repo/content[k+'_review_file'])!=content[k+'_review_sha256'] for k in ('noncash','adjustment'))):
        raise ValueError('targeted primary review absent or unbound')
    for name,h in proposal['inherited_source_manifests'].items():
        if name not in LOCAL_FILES or file_sha(base/name)!=h:
            raise ValueError('inherited primary source interpretation changed')
    inherited=json.loads((base/'budgeted-residual-corporate-reviewed-20261021/reviewed-manifest.json').read_text())
    if any(inherited['capital_tax'].get(key)!=proof for key,proof in proposal['capital_tax'].items()):
        raise ValueError('old event-level tax interpretation must stay unchanged')
    effective=project_proofs(proposal,file_sha(proof_path))
    events,receipts=compile_distribution_events_v2(packets,effective,TradingCalendar(sessions))
    kinds={k:sum(r['source_kind']==k for r in receipts) for k in
           ('VENDOR_DISTRIBUTION','PRIMARY_NOTICE_SUPPLEMENT','PRIMARY_CASH_PRECISION_CORRECTION')}
    if (len(events)!=378 or kinds!={'VENDOR_DISTRIBUTION':375,'PRIMARY_NOTICE_SUPPLEMENT':3,'PRIMARY_CASH_PRECISION_CORRECTION':0}
            or sum(e.capital_tax_exempt_verified for e in events)!=4
            or sum(e.stock_tax_basis_verified for e in events)!=0
            or [(r['instrument'],r['ex_date']) for r in receipts if r['requires_zero_record_ownership_if_tax_unverified']]!=[('SH603596','2024-05-20')]):
        raise ValueError('frozen source-event counts or proof coverage changed')
    def encode(value):
        if isinstance(value,(date,Decimal)):return str(value)
        raise TypeError('unsupported source artifact value')
    out.mkdir(parents=True)
    artifacts={'effective_proofs.json':effective,'derived_events.json':[asdict(e) for e in events],
               'event_source_receipts.json':list(receipts)}
    for name,value in artifacts.items():
        with (out/name).open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False,default=encode);f.write('\n')
    summary={'status':'PRICE_DELAY_378_SOURCE_EVENTS_COMPILED_INDEPENDENT_AUDIT_PENDING',
        'plan_sha256':a.expected_plan_sha256,'method_code_sha256':plan['method_code_sha256'],
        'raw_manifest_sha256':file_sha(raw/'manifest.json'),'reviewed_manifest_sha256':file_sha(proof_path),
        'target_sha256':m['target_sha256'],'source_names':151,'source_sessions':486,'monthly_targets':24,
        'compiled_events':len(events),'source_kind_counts':kinds,'verified_capital_tax_exemptions':4,
        'direct_primary_capital_tax_statements':3,'conditional_capital_tax_inferences':1,'strict_statutory_capital_tax_certification':False,
        'verified_stock_tax_basis_events':0,'unverified_tax_proof_receipts':1,
        'source_packet_sha256':m['per_code_sha256'],'original_source_proposal_modified':False,
        'unexplained_later_factor_date_labels':7,'adjustment_factors_used_to_infer_entitlements':False,
        'artifact_sha256':{name:file_sha(out/name) for name in artifacts},
        'event_compilation_independently_verified':False,'raw_account_replay_admitted':False,
        'full_corporate_actions_certified':False,'actual_FIFO_tax_liability_verified':False,
        'historical_arrival_certified':False,'portfolio_returns_computed':False,
        'new_2026_queries':False,'objective_achieved':False}
    with (out/'summary.json').open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
    print('compiled378source events; no portfolio ROI; independent audit and raw account pending',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
