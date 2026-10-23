"""Separate cached primary review and strict-failure checks; no production imports/ROI."""
import argparse
import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ARCHIVE = 'reversal-full-corporate-notices-20261017'
PDF = 'SH603737-1225328631.pdf'
PDF_SHA = 'f6b3f28129ccf65adf1d3a1be7fba7c1c6a7eb062550b84e6605072cdb6ea0e0'
FAILURE = 'asset-expansion-continuous-account-20261023'
OLD = 'asset-expansion-raw-development-20261022'
RAW = 'asset-expansion-raw-reconstructed-20261023'
EVENT_ID = 'e6de261ef4d82d2f529184019b0e99abb1a362ec296ebe7f163f5f12d6eb6ac5'
OUTPUT = 'asset-expansion-SH603737-tax-source-review-v2-20261023.json'
PLAN = 'docs/research/asset-expansion-2026-tax-source-review-v2-plan-2026-10-23.md'
METHOD = 'experiments/qlib/audit_sources/2026-10-23-asset-expansion-tax-source-review-v2.py'
TEST = 'tests/test_asset_expansion_tax_source_review_v2.py'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def need(ok, message):
    if not ok:raise ValueError(message)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def cents(v):return v.quantize(D('.01'),rounding=ROUND_HALF_UP)
def day(ts):return datetime.fromisoformat(ts).astimezone(ZoneInfo('Asia/Shanghai')).date().isoformat()

def table_dates(compact):
    # Accept one explicit SSE row format. Unsupported extraction order fails;
    # a date elsewhere in the announcement cannot supply a missing table cell.
    compact=compact.translate(str.maketrans({'Ａ':'A','－':'-'}))
    compact=compact.replace('（','(').replace('）',')').replace('—','-').replace('–','-')
    headers=['股权登记日','最后交易日','除权(息)日','新增无限售条件流通股份上市日','现金红利发放日']
    table=re.escape('股份类别'+''.join(headers)+'A股')
    table+=r'(2026/[0-9]{1,2}/[0-9]{1,2})-(2026/[0-9]{1,2}/[0-9]{1,2})(2026/[0-9]{1,2}/[0-9]{1,2})(2026/[0-9]{1,2}/[0-9]{1,2})(?![0-9])'
    matches=re.findall(table,compact)
    need(matches,'complete labelled SSE action-date table required')
    normalized=[]
    for row in matches:
        normalized.append({k:'%04d-%02d-%02d'%tuple(map(int,v.split('/')))
                           for k,v in zip(('recorded','ex_date','listed','pay_date'),row)})
    need(all(v==normalized[0] for v in normalized),'conflicting labelled action tables')
    return normalized[0]


def reject_receipt(result,exc):
    result.update(status='SOURCE_REVIEW_FAILURE_RETAINED',error_type=type(exc).__name__,error=str(exc))
    result.pop('primary_proof_for_future_version',None)


def text_facts(text):
    compact=re.sub(r'\s+','',text).replace('：',':')
    for literal in ('证券代码:603737','2026-030','三棵树涂料股份有限公司','2025年年度权益分派实施公告',
        '每股派发现金红利0.068元','每股转增0.2股','股本溢价发行所形成的资本公积金','本次转增股本不扣税'):
        need(literal in compact,'missing bound primary identity/term: '+literal)
    need(re.search(r'三棵树涂料股份有限公司董事会2026年0?5月26日',compact),
         'publication date must be the issuer signature date')
    dates=table_dates(compact)
    need(dates=={'recorded':'2026-05-29','ex_date':'2026-06-01',
                 'listed':'2026-06-01','pay_date':'2026-06-01'},'labelled event dates differ')
    return {'instrument':'SH603737','notice_number':'2026-030','announced':'2026-05-26',
        'recorded':'2026-05-29','ex_date':'2026-06-01','listed':'2026-06-01','pay_date':'2026-06-01',
        'gross_cash_per_share':'0.068','capital_per_share':'0.2',
        'issuer_explicit_share_premium_and_no_tax_statement':True,'statutory_tax_certification':False}


def audit_failure(state, old, events, bps):
    a=state['account'];checkpoint=state['prefix_checkpoint']
    need(a['last_clock']==['2026-05-29',1] and checkpoint['last_clock']==['2025-12-31',1],'strict failure before June1 mutation')
    for key in ('cash','owned','fills','orders'):
        need(checkpoint[key]==old[key],'old account checkpoint differs '+key)
    oldids={e['event_id'] for e in events if e['ex_date']<='2025-12-31' and e['instrument'] in old['codes']}
    need([x for x in checkpoint['corporate_ledger'] if x['event_id'] in oldids]==old['corporate_ledger'],'original event prefix')
    for x in checkpoint['corporate_ledger']:
        if x['event_id'] in oldids:continue
        need(x['instrument'] not in old['codes'] and x['kind'] in ('RECORD_DATE_OWNERSHIP','EX_DATE_ENTITLEMENT'),'only added unheld historical dependencies')
        fields=('quantity',) if x['kind']=='RECORD_DATE_OWNERSHIP' else ('registered_quantity','cash_gross','stress_tax_reserve','capital_shares','stock_shares','taxable_stock_income')
        need(all(D(str(x[k]))==0 for k in fields),'nonzero added historical event')
    byid={e['event_id']:e for e in events};registered={};owned={};cash=D('1000000');fills={};ledger={}
    for f in a['fills']:fills.setdefault(day(f['execution_at']),[]).append(f)
    for x in a['corporate_ledger']:ledger.setdefault(x['day'],[]).append(x)
    for at in sorted(set(fills)|set(ledger)):
        entries=ledger.get(at,[])
        for x in entries:
            if x['kind']=='NET_DIVIDEND_CASH_AVAILABLE':
                e=byid[x['event_id']];q=registered[x['event_id']]
                gross=cents(D(e['cash_per_share'])*q);net=gross-cents(gross*D('.2'))
                need(D(x['cash_delta'])==net and at>e['pay_date'],'dividend net/date differs');cash+=net
            elif x['kind']=='EX_DATE_ENTITLEMENT':
                e=byid[x['event_id']];q=registered[x['event_id']]
                need(q==x['registered_quantity'] and at==e['ex_date'],'registered ex entitlement differs')
                need(D(x['cash_gross'])==cents(D(e['cash_per_share'])*q),'gross cash differs')
                need(D(x['stress_tax_reserve'])==cents(D(x['cash_gross'])*D('.2')),'reserve differs')
                need(x['capital_shares']==0 and x['stock_shares']==0,'no noncash credited before strict failure')
        for f in fills.get(at,[]):
            gross=D(f['price'])*f['quantity'];side=f['action']
            cost=cents(max(D(5),gross*D('.0005' if side=='BUY' else '.0015')))+cents(gross*D(bps)/10000)
            need(type(f['quantity']) is int and f['quantity']>0 and D(f['cost'])==cost,'integer fill or fee differs')
            owned[f['security_id']]=owned.get(f['security_id'],0)+f['quantity']*(1 if side=='BUY' else -1)
            cash+=(-gross if side=='BUY' else gross)-cost
            need(cash==D(f['cash_after']) and cash>=0,'fill cash trail differs')
        owned={k:v for k,v in owned.items() if v}
        for x in entries:
            if x['kind']=='RECORD_DATE_OWNERSHIP':
                e=byid[x['event_id']]
                need(at==e['recorded'] and x['quantity']==owned.get(e['instrument'],0),'record ownership differs')
                registered[x['event_id']]=x['quantity']
    need(cash==D(a['cash']) and owned==a['owned'],'final partial cash/share state differs')
    e=byid[EVENT_ID];q=registered[EVENT_ID]
    need(q==2700 and e['capital_tax_exempt_verified'] is False and D(e['capital_per_share'])*q==540,'exact strict tax dependency')
    need(not any(x['day']>='2026-06-01' for x in a['corporate_ledger']),'failed session mutated ledger')
    need(len(state['exit_checks'])==41 and all(x['instrument']=='SH603056' and x['owned']==0 and x['pending_orders']==0
        and x['unpaid_cash_claims']==0 and x['uncredited_stock_claims']==0 and not x['future_entitled_events'] for x in state['exit_checks']),'actual exit observations')
    return {'old_checkpoint_verified':True,'fills_and_cost_cash_trail_checked':len(a['fills']),
        'record_date_entitlement_checked':q,'exact_integer_capital_shares':540,'failed_session_mutations':0,
        'post_exit_clearance_observations':41,'portfolio_return_computed':False}


def main():
    p=argparse.ArgumentParser()
    for n in ('repo-root','source-root','request','expected-request-sha256','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();repo,base,request,out=map(Path,(a.repo_root,a.source_root,a.request,a.output))
    need(not out.exists() and out.resolve()==(base/OUTPUT).resolve() and sha(request)==a.expected_request_sha256,'fresh frozen review')
    r=read(request);need(r['status']=='FROZEN_ONE_CACHED_PRIMARY_TAX_SOURCE_NO_ROI' and r['network_queries']==0,'source-only protocol')
    bound={str(request):a.expected_request_sha256}
    for label,h in r['bound_sha256'].items():
        kind,name=label.split('/',1);need(not Path(name).is_absolute() and '..' not in Path(name).parts,'relative binding')
        bound[str({'repo':repo,'source':base}[kind]/name)]=h
    for path,h in bound.items():need(sha(path)==h,'bound source before '+path)
    result={'request_sha256':a.expected_request_sha256,'review_code_sha256':sha(repo/METHOD),
        'primary_file':ARCHIVE+'/'+PDF,'primary_sha256':PDF_SHA,'network_queries':0,
        'portfolio_returns_computed':False,'objective_achieved':False}
    original=None
    try:
        archive=base/ARCHIVE;need(sha(archive/PDF)==PDF_SHA,'exact cached original PDF')
        capture=read(archive/'manifest.json');reviewed=read(archive/'reviewed-manifest.json')
        doc=next(x for x in capture['documents'] if x['file']==PDF)
        need(doc in reviewed['documents'] and doc['sha256']==PDF_SHA and doc['announcement_id']=='1225328631'
            and doc['instrument']=='SH603737' and doc['day']=='2026-05-26'
            and doc['url']=='https://static.cninfo.com.cn/finalpage/2026-05-26/1225328631.PDF','bound original issuer/date/path')
        for name,h in capture['query_sha256'].items():need(sha(archive/name)==h,'original listing hash')
        from pypdf import PdfReader
        from pdfminer.high_level import extract_text
        pdf=PdfReader(archive/PDF);one=text_facts(''.join(page.extract_text() for page in pdf.pages))
        two=text_facts(extract_text(archive/PDF));need(one==two,'two extractors differ')
        result.update(primary_facts=one,pages=len(pdf.pages),both_extractors_all_pages_checked=True)
        projection=read(base/FAILURE/'source_projection.json');summary=read(base/FAILURE/'summary.json');cases={}
        oldcodes=set(read(base/'asset-expansion-raw-pre2026-20261022/manifest.json')['per_code_sha256'])
        for bps in ('20','40'):
            failure=summary['results_by_extra_bps'][bps]
            need(failure['status']=='STRICT_ACCOUNT_FAILURE_RETAINED' and failure['error']=='applicable capital transfer tax treatment is unverified','strict retained failure')
            oldfolder=base/OLD/bps;import csv
            with (oldfolder/'daily.csv').open() as f:cash=list(csv.DictReader(f))[-1]['cash']
            old={'cash':cash,'owned':read(oldfolder/'ownership.json')['2025-12-31'],'codes':oldcodes,
                 **{k:read(oldfolder/(k+'.json')) for k in ('orders','fills','corporate_ledger')}}
            cases[bps]=audit_failure(read(base/FAILURE/bps/'failed_account_state.json'),old,projection['events'],int(bps))
        result.update(status='CACHED_ISSUER_TAX_TERMS_AND_BOTH_STRICT_FAILURES_CHECKED',strict_failures=cases,
            primary_proof_for_future_version={'verified_exempt':True,'source_file':PDF,'source_sha256':PDF_SHA,
            'publication_day':'2026-05-26','expected_capital_per_share':'0.200000'})
    except BaseException as exc:
        original=exc;reject_receipt(result,exc)
    changed=[]
    for path,h in bound.items():
        try:need(sha(path)==h,'source changed')
        except BaseException as exc:
            changed.append(path)
            if original is None:original=exc
    if original is not None:
        reject_receipt(result,original)
    result.update(changed_inputs=changed,all_bound_sha256=bound)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    if original is not None:raise original
    print(result['status'],flush=True)

if __name__=='__main__':main()
