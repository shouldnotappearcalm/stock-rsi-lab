"""Generate fixed diagnostic targets only after authenticated raw development.

The only source change permitted is an explicit date-cap argument. Historical
targets and every historical formation receipt must reproduce byte hashes.
This script neither computes portfolio returns nor chooses new parameters.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

from scripts.capture_cninfo_csi500_reports_pre2026 import sha256_file
from scripts.run_low_risk_intraday_replay import authenticate_development
from scripts.run_qlib_low_risk_goal_diagnostic_2026 import full_input_hashes
from scripts.run_qlib_low_risk_pre2026 import parse_memberships
from stock_rsi.qlib_snapshot import QlibSnapshot
from stock_rsi.return_families import build_targets


TARGET_END='2026-10-13'
METHOD_FILES=('scripts/prepare_reversal_frozen_2026_targets.py','src/stock_rsi/return_families.py',
    'src/stock_rsi/low_risk_monthly.py','src/stock_rsi/prior_close_orders.py','src/stock_rsi/qlib_snapshot.py',
    'scripts/run_low_risk_intraday_replay.py','scripts/run_qlib_low_risk_goal_diagnostic_2026.py',
    'scripts/run_qlib_low_risk_pre2026.py','scripts/run_cninfo_orj_signal_pre2026.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py',
    'experiments/qlib/audit_sources/2026-10-17-return-families-development-source.py')


def json_hash(value):return hashlib.sha256((json.dumps(value,indent=2)+'\n').encode()).hexdigest()


def assert_cap_only_change(old,new):
    expected=old.replace('def build_targets(snapshot,memberships,start=START,end=END):',
        'def build_targets(snapshot,memberships,start=START,end=END,*,permitted_end=END):')
    expected=expected.replace("if start> end or start<START or end>END:raise ValueError('target generation exceeds pre-2026 research cap')",
        "if start> end or start<START or end>permitted_end:raise ValueError('target generation exceeds explicit research cap')")
    if ast.dump(ast.parse(expected))!=ast.dump(ast.parse(new)):
        raise ValueError('source changed beyond the explicit date-cap permission')


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('provider-uri','development-dir','development-audit','plan','expected-plan-sha256','output-dir'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if out.exists():raise ValueError('diagnostic target output already exists')
    if sha256_file(args.plan)!=args.expected_plan_sha256:raise ValueError('diagnostic target plan changed')
    plan=json.loads(Path(args.plan).read_text());dev=Path(args.development_dir)
    if (plan['status']!='FROZEN_BEFORE_REVERSAL_2026_TARGETS' or plan['target_end']!=TARGET_END
            or set(plan['method_code_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/name)!=value for name,value in plan['method_code_sha256'].items())):
        raise ValueError('diagnostic target method changed')
    rawplan=root/'experiments/qlib/reversal-intraday-development-plan.json'
    if sha256_file(rawplan)!=plan['raw_development_plan_sha256']:raise ValueError('raw development plan changed')
    development_plan=json.loads(rawplan.read_text())
    screen_path=root/'experiments/qlib/return-families-pre2026-plan.json'
    if sha256_file(screen_path)!=plan['original_screen_plan_sha256']:
        raise ValueError('original formation screen plan changed')
    screen=json.loads(screen_path.read_text())
    if any(name!='src/stock_rsi/return_families.py' and sha256_file(root/name)!=value
           for name,value in screen['method_code_sha256'].items()):
        raise ValueError('original formation or price-reading dependency changed')
    if any(name!='src/stock_rsi/return_families.py' and sha256_file(root/name)!=value
           for name,value in development_plan['method_code_sha256'].items()):
        raise ValueError('tested raw account or execution method changed')
    prior=json.loads((dev/'summary.json').read_text())
    if prior['plan_sha256']!=plan['raw_development_plan_sha256']:raise ValueError('development experiment mismatch')
    authenticate_development(dev,{'development_summary_sha256':plan['raw_development_summary_sha256'],
                                  'method_code_sha256':development_plan['method_code_sha256']})
    if sha256_file(args.development_audit)!=plan['raw_development_audit_sha256']:raise ValueError('independent audit changed')
    audit=json.loads(Path(args.development_audit).read_text())
    if (audit['replay_summary_sha256']!=plan['raw_development_summary_sha256'] or audit['valid_profiles']!=60
            or audit['raw_confirmation_passes_independently'] is not True
            or prior['raw_development_confirmation_passes'] is not True):raise ValueError('raw development confirmation not passed')
    old=root/'experiments/qlib/audit_sources/2026-10-17-return-families-development-source.py'
    if sha256_file(old)!=development_plan['method_code_sha256']['src/stock_rsi/return_families.py']:
        raise ValueError('archived economic source differs from tested development')
    if sha256_file(old)!=screen['method_code_sha256']['src/stock_rsi/return_families.py']:
        raise ValueError('economic source differs from original screen')
    assert_cap_only_change(old.read_text(),(root/'src/stock_rsi/return_families.py').read_text())
    if full_input_hashes(args.provider_uri)!=plan['input_sha256']:raise ValueError('fixed extended price snapshot changed')
    snapshot=QlibSnapshot(args.provider_uri)
    memberships=parse_memberships((Path(args.provider_uri)/'instruments/csi500.txt').read_text())
    targets,receipts=build_targets(snapshot,memberships,end=TARGET_END,permitted_end=TARGET_END)
    before={name:{day:value for day,value in records.items() if day<'2026-01-01'} for name,records in targets.items()}
    historical_receipts=[r for r in receipts if r['execution_session']<'2026-01-01']
    if (json_hash(before)!=plan['initial_family_targets_sha256']
            or json_hash(historical_receipts)!=plan['initial_formation_receipts_sha256']):
        raise ValueError('development target/formation prefix changed')
    chosen=targets['contrarian60_12']
    if len(chosen)!=34 or len(receipts)!=34 or any(r['latest_factor_price_read']!=r['formation_asof'] for r in receipts):
        raise ValueError('complete causal monthly target history required')
    out.mkdir(parents=True)
    (out/'targets.json').write_text(json.dumps(chosen,indent=2)+'\n')
    (out/'formation_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    receipt={'status':'FROZEN_REVERSAL_2026_TARGETS_PREPARED','strategy':'contrarian60_12','months':len(chosen),
        'target_end':TARGET_END,'planned_account_end':'2026-10-16','development_prefix_reproduced':True,
        'archived_source_sha256':sha256_file(old),'permission_only_source_change_verified':True,
        'targets_sha256':sha256_file(out/'targets.json'),'formation_receipts_sha256':sha256_file(out/'formation_receipts.json'),
        'input_sha256':plan['input_sha256'],'plan_sha256':args.expected_plan_sha256,
        '2026_features_read_within_each_formation_asof':True,'2026_strategy_returns_queried':False,
        'sealed_evidence':False,'objective_achieved':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('frozen reversal targets prepared',len(chosen),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
