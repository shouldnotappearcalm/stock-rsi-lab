import pathlib,json,hashlib,copy,zipfile,xml.etree.ElementTree as ET
R=pathlib.Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead'); B=pathlib.Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015/price-delay-regime-primary-horizon-20261021')
M=R/'experiments/qlib/price-delay-regime-primary-source-manifest.json'; E=R/'experiments/qlib/price-delay-regime-horizon-evidence.json'
h=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
m=json.loads(M.read_text());e=json.loads(E.read_text())
assert h(M)=='a274d78b936d5888853c9ec099c509a66470bccb667dd1ca5b125072fa203949'
assert len(m['source_file_sha256'])==len(m['artifact_sha256'])==20
for p,s in m['source_file_sha256'].items():assert h(p)==s,(p,'source bytes')
for p,s in m['artifact_sha256'].items():assert h(B/p)==s,(p,'imported bytes')
assert sorted(m['artifact_sha256'].values())==sorted(m['source_file_sha256'].values())
receipts=[]
for f in ['reading-receipts-issuer.json','reading-receipts-rule.json','reading-receipts-rule-extra.json','reading-receipts-old-issuer.json']:receipts+=json.loads((B/f).read_text())
def validate_docs(mm):
 ds=mm['documents'];assert len(ds)==8 and len({d['file'] for d in ds})==8
 matched=[]
 for d in ds:
  assert d['historical_first_arrival_verified'] is False
  assert mm['artifact_sha256'].get(d['file'])==d['sha256']==h(B/d['file'])
  ok=[r for r in receipts if r.get('requested_url',r.get('url'))==d['url'] and r.get('status')==200 and r.get('sha256',r.get('body_sha256'))==d['sha256'] and r.get('body_bytes')==(B/d['file']).stat().st_size]
  assert len(ok)==1,(d['file'],'receipt mismatch')
  matched.append({'file':d['file'],'sha256':d['sha256'],'url':d['url'],'bytes':(B/d['file']).stat().st_size,'receipt_body_matches':True})
 return matched
matched=validate_docs(m)
assert e==m['reviewed_regime_evidence']
def validate_evidence(ee):
 assert ee['contract']=='SSE_MAINBOARD_RISK_WARNING_HORIZON_V1'
 assert ee['account_capabilities']=={'risk_warning_buy_permission':False}
 epochs=ee['rule_epochs'];assert len(epochs)==2
 expected=[('sse-rule-2023.docx','2023-02-17','2023-02-18T00:00:00+08:00','2023-12-29','2026-07-05','0.05'),('sse-rule-2026.docx','2026-04-24','2026-04-25T00:00:00+08:00','2026-07-06','2026-10-20','0.10')]
 for a,b in zip(epochs,expected):
  assert tuple(a[k] for k in ['source_file','published_on','engineering_available_at','valid_from','valid_through','limit_ratio'])==b
  assert a['actual_arrival_verified'] is False
  assert a['sha256']==m['artifact_sha256'][a['source_file']]
 states=ee['state_intervals'];assert len(states)==2
 specs=[('SH600079','2025-12-16','2025-12-13','2025-12-14T00:00:00+08:00','issuer-sh600079-st-notice.pdf'),('SH600363','2026-09-30','2026-09-29','2026-09-30T00:00:00+08:00','issuer-sh600363-st-notice.pdf')]
 for a,b in zip(states,specs):
  assert tuple(a[k] for k in ['instrument','effective_from','published_on','engineering_available_at','source_file'])==b
  assert a['effective_through']=='2026-10-20' and a['actual_arrival_verified'] is False
  assert a['exchange']=='SSE' and a['board']=='MAINBOARD' and a['risk_status']=='OTHER_RISK_WARNING'
  assert a['source_sha256']==m['artifact_sha256'][a['source_file']]
  assert 'oct14' not in a['source_file']
validate_evidence(e)
# Check that originals retain their stated effective dates and that deferred provisions do not defer risk-warning band.
def docxtext(p):
 with zipfile.ZipFile(p) as z:return ''.join(ET.fromstring(z.read('word/document.xml')).itertext())
oldtext=docxtext(B/'sse-rule-2023.docx');newtext=docxtext(B/'sse-rule-2026.docx');defer=docxtext(B/'sse-rule-2026-deferred.docx')
assert '5%' in oldtext and '10%' in newtext and '2026' in newtext and '7月6日' in newtext.replace(' ','')
assert '风险警示' not in defer
assert '2026年9月30日' in (B/'sse-sh600363-confirmation-text.txt').read_text()
assert '2026 年 9 月 30 日' in (B/'issuer-sh600363-st-notice-text.txt').read_text()
assert 'ST 人福' in (B/'issuer-sh600079-oct14-confirmation-text.txt').read_text()
neg={}
for name,kind in [('doc_missing_from_artifact_map','map'),('receipt_url_mutation','url'),('published_date_or_epoch_shift','date'),('arrival_upgrade','arrival'),('buy_permission_upgrade','permission'),('later_Oct14_used_for_original_state','oct14')]:
 mm=copy.deepcopy(m);ee=copy.deepcopy(e)
 if kind=='map':del mm['artifact_sha256'][mm['documents'][0]['file']]
 if kind=='url':mm['documents'][3]['url']='https://www.sse.com.cn/wrong.docx'
 if kind=='date':ee['rule_epochs'][1]['valid_from']='2026-04-24'
 if kind=='arrival':ee['rule_epochs'][1]['actual_arrival_verified']=True
 if kind=='permission':ee['account_capabilities']['risk_warning_buy_permission']=True
 if kind=='oct14':ee['state_intervals'][0]['source_file']='issuer-sh600079-oct14-confirmation.pdf'
 try:validate_docs(mm) if kind in ['map','url'] else validate_evidence(ee)
 except AssertionError:neg[name]=True
 else:raise AssertionError(('negative accepted',name))
report={'status':'INDEPENDENT_SOURCE_BYTES_RECEIPTS_AND_RUNTIME_EVIDENCE_BINDINGS_VERIFIED','manifest_sha256':h(M),'runtime_evidence_sha256':h(E),'review_code_sha256':h(__file__),'imported_artifacts_verified':20,'original_source_files_verified':20,'unique_documents_verified':8,'all_document_files_in_hash_map':True,'all_eight_successful_HTTP_receipts_match_URL_body_SHA_and_size':True,'deferred_attachment_metadata_correction_matches_original_HTTP_receipt':True,'document_checks':matched,'runtime_evidence_exact_manifest_projection':True,'rule_epochs_verified':e['rule_epochs'],'state_intervals_verified_as_engineering_clips':e['state_intervals'],'buy_permission_is_false':True,'October14_confirmation_not_used_for_earlier_visibility':True,'negative_controls_rejected':neg,'critical_or_important_findings':[],'ready_for_bounded_engineering_replay_from_source_binding_review':True,'historical_arrival_verified':False,'exhaustive_uninterrupted_primary_state_chronology_certified':False,'raw_isST_series_rechecked':False,'portfolio_returns_computed':False,'network_queries':0,'repository_or_formal_source_changes':False,'limitations':['The effective starts are primary-document facts;Oct20 ends are experiment clips. Unchanged rawisST match is a root/runtime validation claim, not independently re-read in this document-only review.','Next-day visibility is explicitly engineering availability, not an authenticated historical receipt. Current reading receipts are datedOct21.','This review verifies source/evidence bindings and facts already reviewed, not trading-driver correctness, investor permissions or achievable fills.']}
out=pathlib.Path('/tmp/price-delay-regime-primary-source-binding-review-20261021.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n');print(str(out),h(out))
