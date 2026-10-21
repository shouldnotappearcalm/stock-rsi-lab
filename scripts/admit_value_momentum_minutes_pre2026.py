"""Composite scope checks for a separately frozen local-only source admission."""
import argparse,json
from collections import Counter
from pathlib import Path
from scripts.capture_value_momentum_minutes_pre2026 import authenticate,METHOD_FILES as CAPTURE_METHODS,RAW
from scripts.admit_low_beta60_minutes_pre2026 import inspect_packet,verify_query_receipt
from scripts.fundamental_query_journal import file_sha,digest

CAPTURE='szse-value-momentum-minutes-dev-20261021'
CP='experiments/qlib/szse-value-momentum-minute-capture-plan.json'
RQ='experiments/qlib/szse-value-momentum-minute-gap-identities.json'
AUDIT='experiments/qlib/szse-value-momentum-minute-capture-independent-audit.json'
METHOD_FILES=tuple(dict.fromkeys((*CAPTURE_METHODS,'scripts/admit_value_momentum_minutes_pre2026.py')))
PUBLIC_FILES=(CP,RQ,AUDIT,'experiments/qlib/szse-value-momentum-minute-capture-manifest.json',
 'experiments/qlib/szse-value-momentum-minute-capture-composite-scope.json',
 'experiments/qlib/szse-value-momentum-minute-capture-verification.json',
 'docs/research/szse-value-momentum-minute-admission-plan-2026-10-21.md')
LOCAL_FILES=tuple(CAPTURE+'/'+n for n in ('plan.json','request.json','capture_request.json','manifest.json','composite-scope.json','client_cleanup.json'))


def read(path):return json.loads(Path(path).read_text())


def verify_journal_bytes(capture,audit):
 actual={str(p.relative_to(capture)):file_sha(p) for p in (capture/'queries').rglob('*') if p.is_file()}
 if actual!=audit['query_artifact_sha256']:
  raise ValueError('exact independently audited query artifact bytes required')


def verify_capture_scope(scope,manifest,cleanup,*,capture_plan_sha256,request_sha256,manifest_sha256,cleanup_sha256):
 expected={'status':'COMPOSITE_PRE2026_MINUTE_CAPTURE_RECORDED','candidate':'szse_value_momentum_equal',
  'capture_plan_sha256':capture_plan_sha256,'request_sha256':request_sha256,
  'legacy_helper_manifest_sha256':manifest_sha256,'cleanup_sha256':cleanup_sha256,
  'legacy_status_marker_preserved':True,'expected_active_pairs':1744,'fixed_reused_pairs':1051,
  'maximum_fresh_logical_reservations':693,'new_2026_queries':False,
  'admitted_for_reconstructed_execution':False,'portfolio_returns_computed':False,'objective_achieved':False}
 if (any(scope.get(k)!=v or type(scope.get(k)) is not type(v) for k,v in expected.items())
     or manifest.get('status')!='LOW_BETA60_PRE2026_MINUTE_CAPTURE_RECORDED'
     or type(manifest.get('complete_capture')) is not bool
     or scope.get('complete_capture') is not manifest['complete_capture']):
  raise ValueError('actual legacy capture and separate composite scope must bind exactly')
 rows=cleanup['closed_clients'];created=cleanup['created_clients']
 if (type(created) is not int or not 0<=created<=693 or not isinstance(rows,list) or len(rows)!=created
     or any(type(r.get('entered')) is not bool or r.get('close_called') is not True
      or 'error' not in r or r['error'] is not None and not isinstance(r['error'],str) for r in rows)):
  raise ValueError('complete source-client cleanup record required')
 # Failed initialization/cleanup stays inspectable; it never grants admission.
 return created==1 and rows[0]['entered'] is True and rows[0]['error'] is None


def main(argv=None):
 parser=argparse.ArgumentParser()
 for n in ('source-root','plan','expected-plan-sha256','output-dir'):parser.add_argument('--'+n,required=True)
 a=parser.parse_args(argv);base=Path(a.source_root);repo=Path(__file__).resolve().parents[1];out=Path(a.output_dir)
 if out.exists():raise ValueError('preserve prior minute source admission')
 if file_sha(a.plan)!=a.expected_plan_sha256:raise ValueError('frozen composite minute admission plan changed')
 plan=read(a.plan)
 if (plan['status']!='FROZEN_COMPOSITE_PRE2026_MINUTE_SOURCE_ADMISSION'
     or plan['candidate']!='szse_value_momentum_equal' or plan['required_active_sessions']!=1744
     or set(plan['method_code_sha256'])!=set(METHOD_FILES)
     or set(plan['public_evidence_sha256'])!=set(PUBLIC_FILES) or set(plan['local_source_sha256'])!=set(LOCAL_FILES)):
  raise ValueError('fixed local-only composite admission scope required')
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
  for n,h in plan[field].items():
   if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(parent/n)!=h:raise ValueError('frozen admission source/method changed: '+n)
 capture=base/CAPTURE;cp=read(repo/CP);request=read(repo/RQ);m=read(capture/'manifest.json');scope=read(capture/'composite-scope.json');cleanup=read(capture/'client_cleanup.json')
 if (file_sha(repo/CP)!=plan['capture_plan_sha256'] or file_sha(repo/RQ)!=plan['request_sha256']
     or file_sha(capture/'plan.json')!=file_sha(repo/CP) or file_sha(capture/'request.json')!=file_sha(repo/RQ)
     or file_sha(capture/'manifest.json')!=plan['capture_manifest_sha256']):raise ValueError('actual capture identity changed')
 reused,fresh=authenticate(base,repo,request,cp)
 cleanup_ok=verify_capture_scope(scope,m,cleanup,capture_plan_sha256=file_sha(repo/CP),request_sha256=file_sha(repo/RQ),
  manifest_sha256=file_sha(capture/'manifest.json'),cleanup_sha256=file_sha(capture/'client_cleanup.json'))
 sourceaudit=read(repo/AUDIT)
 if (sourceaudit['capture_manifest_sha256']!=file_sha(capture/'manifest.json') or sourceaudit['capture_plan_sha256']!=file_sha(repo/CP)
     or sourceaudit['request_sha256']!=file_sha(repo/RQ) or sourceaudit['scope_sha256']!=file_sha(capture/'composite-scope.json')
     or sourceaudit['imports_project_code'] is not False):raise ValueError('independent capture provenance audit differs')
 verify_journal_bytes(capture,sourceaudit)
 config={'reused':reused,'fresh':fresh}
 if (read(capture/'capture_request.json')!=config or m['plan_sha256']!=file_sha(repo/CP)
     or m['capture_request_sha256']!=file_sha(capture/'capture_request.json') or m['requested']!=1744
     or m['captured']!=len(m['per_session_sha256']) or m['reused_session_provenance']!=reused):raise ValueError('actual capture partition changed')
 snapshot=capture/('capture-snapshot-'+digest(m)+'.json')
 if not snapshot.exists() or read(snapshot)!=m or file_sha(snapshot)!=sourceaudit['legacy_snapshot_sha256']:
  raise ValueError('original immutable capture snapshot changed')
 expected={c+'-'+d+'.json' for c,d in request['active_requests']}
 if not set(m['per_session_sha256'])<=expected or {p.name for p in (capture/'sessions').iterdir()}!=set(m['per_session_sha256']):
  raise ValueError('unexpected, unbound or future minute packet')
 raw=base/RAW;rm=read(raw/'manifest.json');bars={c:{r['date']:r for r in read(raw/'codes'/(c+'.json'))['bars']} for c in rm['per_code_sha256']}
 identities={digest({'method':'minutes.history','instrument':c,'requested_day':d,'host':cp['host'],'include_raw':True}):
  {'method':'minutes.history','instrument':c,'requested_day':d,'host':cp['host'],'include_raw':True} for c,d in fresh}
 queries=capture/'queries';folders=list(queries.iterdir()) if queries.exists() else []
 if any(not f.is_dir() or f.name not in identities or read(f/'request.json')!=identities[f.name] for f in folders):
  raise ValueError('unregistered fresh minute request folder')
 reservations=list(queries.glob('*/reserved-*.json'));responses=list(queries.glob('*/response-*.json'))
 if (len(reservations)!=m['fresh_query_reservations'] or len(responses)!=m['fresh_query_responses_preserved']
     or len(reservations)>693 or any(f.name!='reserved-1.json' or f.parent.name not in identities for f in reservations)
     or any(f.name!='response-1.json' or f.parent.name not in identities for f in responses)):
  raise ValueError('frozen one-attempt693 logical budget changed')
 rows=[];captured_status=Counter()
 for code,day in request['active_requests']:
  name=code+'-'+day+'.json';row={'instrument':code,'day':day}
  if name not in m['per_session_sha256']:
   row['status']='SOURCE_NOT_CAPTURED';rows.append(row);continue
  f=capture/'sessions'/name;h=m['per_session_sha256'][name]
  if file_sha(f)!=h:raise ValueError('captured minute bytes changed')
  packet=read(f);record=packet.get('methods',{}).get('minutes.history',packet)
  captured_status[record['status']]+=1;row['source_sha256']=h
  if name in reused:
   origin=reused[name]
   if h!=origin['sha256'] or file_sha(base/origin['root']/'sessions'/name)!=h:raise ValueError('reused source bytes changed')
   row['origin']=origin
  else:verify_query_receipt(capture,code,day,packet,cp['host']);row['origin']='FROZEN_FRESH_QUERY'
  try:row.update(inspect_packet(code,day,packet,bars[code][day]))
  except (ValueError,KeyError,ArithmeticError) as exc:row.update(status='SOURCE_REJECTED',error_type=type(exc).__name__,error=str(exc))
  rows.append(row)
 if dict(captured_status)!=m['response_status_counts']:raise ValueError('captured source status totals changed')
 counts=dict(Counter(r['status'] for r in rows))
 passed=(counts=={'ADMITTED_RECONSTRUCTED_ACTIVE_TAPE':1744} and m['complete_capture'] is True
  and m['abnormal_exit'] is None and not m['stopped_after_consecutive_source_failures']
  and len(reservations)==len(responses)==693 and cleanup_ok and sourceaudit['capture_fully_recorded'] is True)
 out.mkdir(parents=True)
 (out/'details.json').write_text(json.dumps({'sessions':rows,'nonexecuting_source_intervals':request['nonexecuting_source_intervals']},indent=2)+'\n')
 result={'status':'COMPOSITE_PRE2026_MINUTE_SOURCE_ADMISSION_COMPLETE','plan_sha256':a.expected_plan_sha256,
  'method_code_sha256':plan['method_code_sha256'],'capture_plan_sha256':file_sha(repo/CP),
  'capture_manifest_sha256':file_sha(capture/'manifest.json'),'request_sha256':file_sha(repo/RQ),
  'capture_scope_sha256':file_sha(capture/'composite-scope.json'),'independent_capture_audit_sha256':file_sha(repo/AUDIT),
  'raw_manifest_sha256':file_sha(raw/'manifest.json'),'target_sha256':request['target_sha256'],
  'required_active_sessions':1744,'nonexecuting_source_intervals':2,'status_counts':counts,
  'fresh_reservations':len(reservations),'fresh_responses':len(responses),'reused_packets':1051,'client_cleanup_passes':cleanup_ok,
  'admitted_for_reconstructed_execution':passed,'details_sha256':file_sha(out/'details.json'),
  'exact_share_total_matches':sum(r.get('facts',{}).get('exact_total_shares_match') is True for r in rows),
  'exact_share_precision_certified':False,'historical_arrival_verified':False,'sdk_date_echo_authenticated':False,
  'queue_and_impact_calibrated':False,'full_corporate_actions_certified':False,'portfolio_returns_computed':False,
  'new_2026_market_values_queried':False,'candidate_promoted':False,'objective_achieved':False,
  'exceptions':[r for r in rows if r['status']!='ADMITTED_RECONSTRUCTED_ACTIVE_TAPE']}
 (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Composite minute admission',counts,'passed',passed,'no account/ROI/network',flush=True);return 0 if passed else 2

if __name__=='__main__':raise SystemExit(main())
