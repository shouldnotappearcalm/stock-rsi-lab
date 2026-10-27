"""Whole-corpus same-grammar replay plus separate Decimal/source-line audit.

No investment, independent assurance, historical-arrival or full visual-QA claim.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
from scripts import inspect_cash_accrual_cfo_corpus as r


def check_one(job):
    base,document,normative,known,path,expected=job
    case=r.read_bound(path,expected)
    reproduced=r.inspect_one(base,document,normative,known)
    r.need(case==reproduced,'complete original worker source case must replay exactly')
    r.validate_case(case,document,base,known,normative)
    result={'capture_key':case['capture_key'],'status':case['status'], 'source_parser_variant':case['source_parser_variant'],
            'instrument':case['instrument'],'fiscal_year':case['fiscal_year'],'record_id':None,
            'protected_asset_cells_compared':case['protected_asset_cells_compared'],'cells':0,'units':{},'negative':{}}
    if case['report'] is not None:
        report=case['report'];result['record_id']=report['record_id'];p=report['parsed'];units=Counter();negative=Counter()
        for kind,(_,_,field,_) in r.cash.STATEMENTS.items():
            for period in p[kind]:
                cell=p[kind][period] if kind=='balances' else p[kind][period][field]
                scale={'元':Decimal(1),'万元':Decimal(10000)}[cell['unit']]
                amount=Decimal(cell['literal'].replace(',',''))*scale
                r.need(amount==Decimal(cell['value_CNY']),'separate literal Decimal normalization')
                table=p['tables'][kind]['lines'];a,b=cell['row_source_start_index'],cell['row_source_end_index']
                r.need('\n'.join(t for page,t in table[a:b])==cell['row_text']
                       and all(page==cell['page'] for page,t in table[a:b]),'exact unaltered physical row mapping')
                if 'caption_end_offset' in cell:
                    prefix=cell['row_text'][:cell['caption_end_offset']]
                    r.need(''.join(prefix.split())==cell['normalized_caption'],'caption-only raw offset reconstruction')
                units[cell['unit']]+=1
                if amount<0:negative[field]+=1
        result.update(cells=6,units=dict(units),negative=dict(negative))
    return result


def audit(base,root,request,expected):
    req,known=r.verify(base,root,base/'qlib-enhanced-dev/instruments/csi500.txt',request,expected)
    known[str(Path(__file__).resolve())]=r.sha(Path(__file__))
    out=base/r.OUTPUT;terminal=r.read(out/'terminal.json');r.need(terminal['complete'] is True,'completed source producer required')
    artifacts=r.tree(out);r.need(artifacts=={**terminal['capture_sha256'],'terminal.json':r.sha(out/'terminal.json')},'entire frozen producer artifact tree')
    index=r.read_bound(out/'case_index.json',artifacts['case_index.json'])
    r.need(list(index)==[d['capture_key'] for d in req['documents']],'complete original document order')
    rows=[];units=Counter();negative=Counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(req['documents']),4):
            jobs=[]
            for d in req['documents'][start:start+4]:
                name='cases/'+d['capture_key']+'.json'
                r.need(index[d['capture_key']]['sha256']==artifacts[name],'case index digest')
                subset={str(p.resolve()):known[str(p.resolve())] for p in r.case_paths(base,d)}
                jobs.append((base,d,req['normative_basis'],subset,out/name,artifacts[name]))
            for row in pool.map(check_one,jobs):
                rows.append(row);units.update(row['units']);negative.update(row['negative'])
            if len(rows)%200==0 or len(rows)==len(req['documents']):print('root source audit',len(rows),'/',len(req['documents']),flush=True)
    counts=dict(Counter(c['status'] for c in rows));preserved=sum(c['source_parser_variant']=='V2_PRESERVED' for c in rows)
    cells=sum(c['cells'] for c in rows);protected=sum(c['protected_asset_cells_compared'] for c in rows)
    r.need(counts==terminal['summary']['status_counts'] and preserved==257
           and cells==terminal['summary']['raw_monetary_cells'] and protected==terminal['summary']['protected_asset_cells_compared'],'all producer totals reconciled')
    r.need(not r.changed(known) and r.tree(out)==artifacts,'whole source/producer unchanged after root audit')
    proof={'status':'PASS_ALL_CFO_SOURCE_CASE_REPLAY_AND_SEPARATE_LITERAL_CHECKS_NOT_FACTOR_ADMISSION',
           'request_sha256':expected,'producer_summary':terminal['summary'],'source_units':dict(units),'negative_cells':dict(negative),
           'independent_literal_decimal_normalizations':cells,'all_original_257_reports_preserved_identically':True,
           'approved_record_ids':{row['capture_key']:row['record_id'] for row in rows},'case_rows':rows,
           'all_input_sha256':known,'all_output_sha256':artifacts,'audit_code_sha256':r.sha(Path(__file__)),
           'all_inputs_outputs_unchanged':True,'historical_arrival_verified':False,'financial_version_history_complete':False,
           'full_corpus_manual_visual_QA_complete':False,'shared_grammar_same_author_not_independent_assurance':True,
           'ratios_rankings_or_returns_computed':False,'2026_values_read':False,'objective_achieved':False}
    folder=base/'cash-accrual-cfo-root-audit-v3-20261027';r.need(not folder.exists(),'fresh root evidence only');folder.mkdir()
    (folder/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],**terminal['summary']},ensure_ascii=False),flush=True)
    return proof


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--request',required=True);p.add_argument('--expected-request-sha256',required=True);a=p.parse_args()
    audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],Path(a.request).resolve(),a.expected_request_sha256)
if __name__=='__main__':main()
