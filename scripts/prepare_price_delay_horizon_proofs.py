"""Authenticate saved sources and exclusively project reviewed 2026 metadata.

No network, event compilation or account replay. All evidence maps are frozen
before the projection. Original failed capture and all48 account files stay intact.
"""
import argparse
import copy
import json
from pathlib import Path

from scripts import price_delay_horizon_proof_projection as core
from scripts import reassemble_price_delay_horizon_raw as raw
from scripts.prepare_price_delay_horizon_formations import immutable_financial_hashes

RAW='price-delay-raw-horizon-v2-20261021'
OLDRAW='price-delay-raw-dev-20261021'
OLDEVENTS='price-delay-account-source-events-20261021'
OLDPDF='price-delay-corporate-reviewed-20261021'
FORM='price-delay-horizon-formations-20261021'
REQUEST='experiments/qlib/price-delay-horizon-proof-projection-request.json'
RAW_SHA='9fe3990c0b4b1c076b78c97971ceecf593687b2f15699154c3bdbbce666f6490'
TARGET_SHA='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923'
REASSEMBLY_REQUEST='experiments/qlib/price-delay-horizon-local-reassembly-request.json'
REASSEMBLY_SHA='b43aa018c7439824913841643df4af9ea6d6cdb454e18a8bfe570d33974cf12d'
CACHE_ROOTS={
 'low-beta60-corporate-reviewed-horizon-20261021/reviewed-manifest.json':'01dcd1f8e96c544243ee88c446075cdaf68e8fd772dc45813144c85094251c0a',
 'low-beta60-corporate-reviewed-2026-20261021/reviewed-manifest.json':'7fdec0f62c3a83842c9e447a19416d9dd4b4165a44669484822e9d841c5a7d80',
 'szse-value-momentum-full-reviewed-proofs-20261021.json':'ac0cf40ccc3dc1d4ab3a723bfcd1e75cb34f51cac3068bba879b12033a09b9d8',
 'szse-value-full-corporate-notices-20261017/reviewed-manifest.json':'0c14b8e9bfa421a20b5bb6b1befd4b8c0c7c93e674b9f87e910394efacd64723',
 'return-family-corporate-notices-20261017/reviewed-manifest.json':'a77d0caf8788616fee773c1c4e5a0b9614956cbd0f79732644fee0b0b85b1bd8',
 'reversal-full-corporate-notices-20261017/reviewed-manifest.json':'ff7d6c9e1a17978c74d204a616f1bd965600a5605d02667570256d881ccbf022'}
# Original source route only; no fallback or file choice based on account results.
DOCUMENT_ROUTES={
 'SH601128-20260603.pdf':('low-beta60-corporate-2026-20261021','manifest.json','low-beta60-2026-corporate-content-review.json','REVIEWED_BYTE_REUSE'),
 'SZ000937-20260611.pdf':('low-beta60-corporate-2026-20261021','manifest.json','low-beta60-2026-corporate-content-review.json','HTTP'),
 'SZ000937-20260827.pdf':('low-beta60-corporate-2026-20261021','manifest.json','low-beta60-2026-corporate-content-review.json','HTTP'),
 'SH601918-20260130.pdf':('low-beta60-corporate-2026-20261021','manifest.json','low-beta60-2026-corporate-content-review.json','HTTP'),
 'SZ000975-20260417.pdf':('low-beta60-corporate-2026-20261021','manifest.json','low-beta60-2026-corporate-content-review.json','HTTP'),
 'SH601598-20261013.pdf':('low-beta60-horizon-cninfo-primary-20261021','manifest.json','low-beta60-horizon-primary-content-review.json','HTTP'),
 'SZ002608.pdf':('szse-value-momentum-primary-2026-gaps-20261021','manifest.json','szse-value-momentum-primary-2026-seven-content-review.json','HTTP'),
 'SZ002756.pdf':('szse-value-momentum-primary-2026-gaps-20261021','manifest.json','szse-value-momentum-primary-2026-seven-content-review.json','HTTP'),
 'SZ002812.pdf':('szse-value-momentum-primary-2026-gaps-20261021','manifest.json','szse-value-momentum-primary-2026-seven-content-review.json','HTTP'),
 'SZ002595-20260430.pdf':('szse-value-momentum-noncash-2026-capture-20261021','manifest.json','szse-value-momentum-noncash-2026-content-review.json','HTTP'),
 'SH603737-1225328631.pdf':('reversal-full-corporate-notices-20261017','reviewed-manifest.json','reversal-full-corporate-reviewed-manifest.json','REVIEWED_BYTE_REUSE'),
 'SH601966-1225371939.pdf':('reversal-full-corporate-notices-20261017','reviewed-manifest.json','reversal-full-corporate-reviewed-manifest.json','REVIEWED_BYTE_REUSE'),
 'SH603233.pdf':('price-delay-horizon-missing-primary-20261021','manifest.json','price-delay-horizon-single-primary-content-review.json','HTTP'),
 'SH603605-20261012.pdf':('price-delay-horizon-remaining-primary-20261021','manifest.json','price-delay-horizon-four-primary-content-review.json','HTTP'),
 'SH603596-20260430.pdf':('price-delay-horizon-remaining-primary-20261021','manifest.json','price-delay-horizon-four-primary-content-review.json','HTTP'),
 'SH603606-20260519.pdf':('price-delay-horizon-remaining-primary-20261021','manifest.json','price-delay-horizon-four-primary-content-review.json','HTTP'),
 'SZ002831-20260529.pdf':('price-delay-horizon-remaining-primary-20261021','manifest.json','price-delay-horizon-four-primary-content-review.json','HTTP')}
METHODS=tuple(dict.fromkeys((*raw.METHODS,'scripts/price_delay_horizon_proof_projection.py',
 'scripts/prepare_price_delay_horizon_proofs.py','tests/test_price_delay_horizon_proof_projection.py',
 'tests/test_prepare_price_delay_horizon_proofs.py')))
PUBLIC=tuple(dict.fromkeys((*raw.PUBLIC,REASSEMBLY_REQUEST,
 'experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json',
 'experiments/qlib/price-delay-horizon-corporate-inventory-request.json',
 'experiments/qlib/price-delay-horizon-corporate-inventory-output-review.json',
 'experiments/qlib/price-delay-horizon-corporate-proof-field-map-draft.json',
 'experiments/qlib/price-delay-horizon-four-primary-independent-review.json',
 'experiments/qlib/price-delay-horizon-four-primary-content-review.json',
 *(f for f,h in core.REVIEW_FILES.values()),
 *('experiments/qlib/'+v[2] for v in DOCUMENT_ROUTES.values()),
 'docs/research/price-delay-horizon-account-continuation-plan-2026-10-21.md',
 'docs/research/price-delay-horizon-proof-projection-plan-2026-10-21.md')))
LOCAL=tuple(dict.fromkeys((*CACHE_ROOTS,
 RAW+'/manifest.json',RAW+'/calendar.json',OLDRAW+'/manifest.json',OLDRAW+'/calendar.json',
 FORM+'/candidate_targets.json',FORM+'/summary.json','price-delay-pre2026-formations-20261021/targets.json',
 *(OLDEVENTS+'/'+n for n in ('summary.json','effective_proofs.json','derived_events.json','event_source_receipts.json')),
 'price-delay-event-source-independent-audit-20261021.json',OLDPDF+'/reviewed-manifest.json',
 'price-delay-horizon-corporate-inventory-20261021.json')))
PROFILE={'status':'FROZEN_PRICE_DELAY_REVIEWED_PROOF_PROJECTION_NO_EVENT_OR_ACCOUNT',
 'candidate':'price_delay_d1','window':['2023-12-29','2026-10-20'],
 'output_directory':core.OUTPUT,'maximum_new_source_queries':0,
 'events_to_compile':False,'account_to_run':False,'portfolio_returns_to_compute':False,
 'source_admitted_for_account_replay':False,'full_October_complete':False}


def docs(manifest):
 v=manifest['documents'];return list(v.values()) if isinstance(v,dict) else v


def validate_profile(plan):
 core.need(all(type(plan.get(k)) is type(v) and plan[k]==v for k,v in PROFILE.items()),'fixed source-only proof projection scope required')
 for field,names in (('method_code_sha256',METHODS),('public_evidence_sha256',PUBLIC),('local_source_sha256',LOCAL)):
  core.need(set(plan[field])==set(names),'complete exact input bindings required: '+field)
 specs=plan['primary_evidence']
 core.need(isinstance(specs,dict) and set(specs)==set(DOCUMENT_ROUTES),'exact17 registered original source routes required')
 for name,spec in specs.items():
  cap,manifest,review,route=DOCUMENT_ROUTES[name]
  core.need(spec['route']==route and spec['source_manifest_file']==cap+'/'+manifest and
   spec['source_document_file']==name and spec['pdf_file']==cap+'/'+name and
   spec['content_review_refs']==[{'root':'repo','file':'experiments/qlib/'+review}],
   'original primary source route or review changed: '+name)
  if route=='HTTP':core.need(spec['capture_root']==cap,'original capture root required')
 core.need(set(plan['immutable_trees_sha256'])=={raw.SOURCE,raw.PRIMARY,'price-delay-horizon-remaining-primary-20261021',OLDPDF,OLDEVENTS},'all original capture/PDF/event trees required')


def validate_old_audit(audit,summary_sha,proof_sha,raw_sha,events,receipts):
 core.need(audit['status']=='INDEPENDENT_378_EVENT_ECONOMICS_IDENTITIES_AND_SOURCE_RECEIPTS_RECONSTRUCTED' and
  audit['summary_sha256']==summary_sha and audit['reviewed_manifest_sha256']==proof_sha and audit['raw_manifest_sha256']==raw_sha and
  audit['all378_economics_dates_event_IDs_and_receipts_identical'] is True and audit['all151_source_packets_authenticated'] is True and
  audit['all15_primary_PDF_bytes_and_two_content_reviews_authenticated'] is True and audit['events_reconstructed']==events==receipts==378 and
  audit['imports_project_code'] is False and type(audit['critical_or_important_findings']) is int and audit['critical_or_important_findings']==0,
  'original378 source files differ from the independently reconstructed canonical version')


def recheck(plan,repo,base):
 for field,parent in (('method_code_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base),('primary_files_sha256',base)):
  core.authenticate_file_map(parent,plan[field])
 for name,bound in plan['immutable_trees_sha256'].items():
  core.need(raw.tree_hashes(base/name)==bound,'original evidence tree changed: '+name)
 core.need(immutable_financial_hashes(base)==plan['immutable_financial_sha256'],'all48 frozen financial artifacts required unchanged')
 core.authenticate_file_map(base,plan['immutable_financial_sha256'])
 for n in (OLDRAW,RAW):
  manifest=core.read(base/n/'manifest.json')
  for code,h in manifest['per_code_sha256'].items():
   core.need(core.file_sha(core.path_under(base,n+'/codes/'+code+'.json'))==h,'original source packet changed')


def authenticate(plan_file,expected,repo,base):
 core.need(core.file_sha(plan_file)==expected,'external proof projection request SHA changed')
 plan=core.read(plan_file);validate_profile(plan);recheck(plan,repo,base)
 old_request=core.read(repo/REASSEMBLY_REQUEST)
 core.need(plan['immutable_financial_sha256']==old_request['immutable_financial_sha256'] and len(plan['immutable_financial_sha256'])==48,'canonical original48 financial map required')
 # Reuses the original authenticated failed-capture/reassembly request. This has
 # no source calls and reconstructs the saved SH603233 source coordinate only.
 raw.authenticate(repo/REASSEMBLY_REQUEST,REASSEMBLY_SHA,repo,base)
 core.need(core.file_sha(base/RAW/'manifest.json')==RAW_SHA and core.file_sha(base/FORM/'candidate_targets.json')==TARGET_SHA,'known independent source/target SHA anchors required')
 audit=core.read(repo/'experiments/qlib/price-delay-horizon-local-reassembly-independent-audit.json')
 core.need(audit['manifest_sha256']==RAW_SHA and audit['all203_packets_676_sessions_verified'] is True and audit['all151_original_literal_pre2026_prefixes_identical'] is True and audit['imports_project_code'] is False and not audit['critical_or_important_findings'],'complete independent original source reconstruction required')
 for n,h in CACHE_ROOTS.items():core.need(core.file_sha(base/n)==h,'fixed cache interpretation root changed')
 ss=core.read(base/RAW/'calendar.json')['sessions'];os=core.read(base/OLDRAW/'calendar.json')['sessions']
 core.need(len(ss)==676 and len(os)==486 and ss[:486]==os and ss==sorted(set(ss)) and [ss[0],ss[-1]]==PROFILE['window'],'explicit676/486 calendar prefix required')
 targets=core.read(base/FORM/'candidate_targets.json');oldtargets=core.read(base/'price-delay-pre2026-formations-20261021/targets.json')['price_delay_d1']
 m=core.read(base/RAW/'manifest.json');oldm=core.read(base/OLDRAW/'manifest.json')
 core.need(len(targets)==34 and len(oldtargets)==24 and list(sorted(targets.items()))[:24]==list(sorted(oldtargets.items())) and {c for t in targets.values() for c in t['weights']}==set(m['per_code_sha256']) and len(m['per_code_sha256'])==203 and len(oldm['per_code_sha256'])==151,'same34targets/203names and old24/151 required')
 packets={}
 for code in m['per_code_sha256']:
  p=core.read(base/RAW/'codes'/(code+'.json'));core.need(p['instrument']==code and p['window']==PROFILE['window'] and [r['date'] for r in p['bars']]==ss,'full203 source packets required');packets[code]=p
  if code in oldm['per_code_sha256']:
   old=core.read(base/OLDRAW/'codes'/(code+'.json'))
   for f,d in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
    core.need([r for r in p[f] if r[d]<'2026-01-01']==old[f],'literal old151 source prefix changed')
 core.need(core.file_sha(base/'price-delay-event-source-independent-audit-20261021.json')=='934b8a825b3d4662f7bd8f54fb87c6136801a71aee4efd99db7a9ae74af7d201','original independent378 audit SHA anchor changed')
 validate_old_audit(core.read(base/'price-delay-event-source-independent-audit-20261021.json'),
  core.file_sha(base/OLDEVENTS/'summary.json'),core.file_sha(base/OLDPDF/'reviewed-manifest.json'),core.file_sha(base/OLDRAW/'manifest.json'),
  len(core.read(base/OLDEVENTS/'derived_events.json')),len(core.read(base/OLDEVENTS/'event_source_receipts.json')))
 source=core.read(base/OLDEVENTS/'summary.json')
 for n,h in source['artifact_sha256'].items():core.need(core.file_sha(core.path_under(base,OLDEVENTS+'/'+n))==h,'old378 source artifact changed')
 oldproof=core.read(base/OLDEVENTS/'effective_proofs.json')
 core.need(len(oldproof['documents'])==15,'original15 primary PDFs required')
 for d in oldproof['documents']:core.need(core.file_sha(core.path_under(base,OLDPDF+'/'+d['file']))==d['sha256'],'original15 primary bytes changed')
 chains={}
 for name,spec in plan['primary_evidence'].items():chains[name]=core.authenticate_primary_evidence(base,repo,spec,plan['primary_files_sha256'],plan['public_evidence_sha256'])
 recheck(plan,repo,base)
 return plan,packets,chains


def main(argv=None):
 p=argparse.ArgumentParser()
 for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
 p.add_argument('--preflight-only',action='store_true');a=p.parse_args(argv)
 repo=Path(__file__).resolve().parents[1];base=Path(a.source_root).resolve();out=Path(a.output_dir).resolve()
 core.need(out==base/core.OUTPUT and not out.exists(),'fixed unused projection directory required')
 plan,packets,chains=authenticate(a.request,a.expected_request_sha256,repo,base)
 if a.preflight_only:
  print('projection preflight passed: source chains17 authenticated; no projection/write/events/account');return 0
 reviews=core.load_reviewed_notices(repo);notices=core.canonical_reviewed_notices(reviews)
 cached={name:core.read(base/name) for name in CACHE_ROOTS};documents={}
 for name,proposal in cached.items():
  for d in docs(proposal):documents.setdefault(d['file'],copy.deepcopy(d))
 for name,chain in chains.items():
  d=copy.deepcopy(documents.get(name,chain['document']))
  if d['instrument'] in notices:d.update(copy.deepcopy(notices[d['instrument']]))
  d['day']=d.get('publication_day',d.get('day'));d['source_evidence_chain']=chain
  documents[name]=d
 bundle={'packets':packets,'cached':cached,'reviews':reviews,'documents':documents,
  'old_events':core.read(base/OLDEVENTS/'derived_events.json'),'old_receipts':core.read(base/OLDEVENTS/'event_source_receipts.json')}
 proposal=core.project_sources(bundle)
 proposal.update(raw_manifest_sha256=RAW_SHA,target_sha256=TARGET_SHA,projection_request_sha256=a.expected_request_sha256,source_evidence_chains=chains)
 recheck(plan,repo,base)
 result=core.write_projection(out,proposal,{name:base/spec['pdf_file'] for name,spec in plan['primary_evidence'].items()})
 recheck(plan,repo,base)
 summary={'status':'PRICE_DELAY_HORIZON_PROOF_PROJECTION_COMPLETE_SOURCE_ONLY',**result,
  'projection_request_sha256':a.expected_request_sha256,'raw_manifest_sha256':RAW_SHA,'target_sha256':TARGET_SHA,
  'artifact_sha256':{p.name:core.file_sha(p) for p in out.iterdir() if p.is_file()},
  'original378_source_and15PDF_and48_financial_artifacts_unchanged':True,
  'original_failed_capture_unchanged':True,'input_maps_rechecked_after_projection':True,
  'primary_HTTP_chains':sum(x['HTTP_decoded_body_matches_PDF'] for x in chains.values()),
  'primary_reviewed_byte_reuse_only':sum(x['chain_kind']=='AUTHENTICATED_REVIEWED_BYTE_REUSE_ONLY' for x in chains.values()),
  'capital_supported':len(proposal['capital_tax']),'unresolved_tax_keys':sorted(proposal['unresolved_tax']),
  'supplementary_distributions':len(proposal['supplementary_distributions']),
  'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,
  'full_October_complete':False,'objective_achieved':False}
 with (out/'summary.json').open('x') as f:json.dump(summary,f,indent=2,ensure_ascii=False);f.write('\n')
 print('projected17source PDFs,8cash,5capital,2unknown,1cash/1mixed precision; no events/account/ROI');return 0


if __name__=='__main__':raise SystemExit(main())
