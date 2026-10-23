from pathlib import Path
from decimal import Decimal as D
from collections import Counter
import json,hashlib,shutil
from scripts import inspect_cash_accrual_corpus as r
base=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015');root=Path.cwd();out=base/r.OUTPUT;q=root/'experiments/qlib/cash-accrual-source-request.json';h='19c36e97ffc5da71ed8c3e6933b257a561c6a815a44f5045d1892f5bd3286ec7';req,known=r.verify(base,root,base/'qlib-enhanced-dev/instruments/csi500.txt',q,h)
terminal=r.read(out/'terminal.json');assert terminal['complete'] is True,terminal.get('error');captures=r.tree(out);assert captures=={**terminal['capture_sha256'],'terminal.json':r.sha(out/'terminal.json')};index=r.read_bound(out/'case_index.json',captures['case_index.json']);assert list(index)==[d['capture_key'] for d in req['documents']]
counts=Counter();errors=Counter();cells=controls=0;qa=[];qa_groups=set();units=Counter();negative=Counter();status_by_year={};protected_on_unsupported=0
for i,doc in enumerate(req['documents']):
    key=doc['capture_key'];case=r.read_bound(out/'cases'/(key+'.json'),captures['cases/'+key+'.json']);r.validate_case(case,doc,base,known,req['normative_basis']);counts[case['status']]+=1;status_by_year.setdefault(str(doc['effective_fiscal_year']),Counter())[case['status']]+=1
    raw,oldpath,cachepath=r.case_paths(base,doc);old=r.read_bound(oldpath,known[str(oldpath.resolve())]);cache=r.read_bound(cachepath,known[str(cachepath.resolve())]);pages=cache['pages'];r.cash.metadata(doc)
    assert case['status']==index[key]['status'] and index[key]['sha256']==captures['cases/'+key+'.json']
    for obs in old['source_observations']:assert obs['record_id']==r.digest({k:v for k,v in obs.items() if k!='record_id'})
    try:assets=r.cash.parse_asset_cells(pages,doc['effective_fiscal_year'],normative_basis=req['normative_basis']) if old['cover_code_consistent'] and old['cover_annual_year_consistent'] else None
    except ValueError:assets=None
    n=0
    if assets is not None:
        for obs in old['source_observations']:
            before=obs['payload']['cells']['total_assets'];after=assets[obs['fiscal_end']];assert all(before[k]==after[k] for k in ('value_CNY','literal','fiscal_end','column_index'));n+=1
    assert n==case['protected_asset_cells_compared'];controls+=n
    if case['status']==r.SUPPORTED:
        parsed=case['report']['parsed'];assert r.cash.parse_report(pages,doc['effective_fiscal_year'],normative_basis=req['normative_basis'])==parsed
        for kind,(_,_,field,_) in r.cash.STATEMENTS.items():
            for period in parsed[kind]:
                c=parsed[kind][period] if kind=='balances' else parsed[kind][period][field];assert c['unit'] in ('元','万元');amount=D(c['literal'].replace(',',''))*{'元':D(1),'万元':D(10000)}[c['unit']];assert amount==D(c['value_CNY']);assert c['row_text_sha256']==r.digest(c['row_text']);cells+=1;units[c['unit']]+=1
                if amount<0:negative[field]+=1
        group=(doc['instrument'][:2],doc['effective_fiscal_year'])
        if group in {('SH',2022),('SZ',2022),('SH',2024),('SZ',2024)} and group not in qa_groups:
            qa_groups.add(group);qa.append({'capture_key':key,'instrument':doc['instrument'],'fiscal_year':doc['effective_fiscal_year'],'source_path':doc['source_path'],'source_sha256':doc['source_sha256'],'fields':{kind:{period:(parsed[kind][period] if kind=='balances' else parsed[kind][period][r.cash.STATEMENTS[kind][2]]) for period in parsed[kind]} for kind in r.cash.STATEMENTS}})
    elif case['status']==r.UNSUPPORTED:
        protected_on_unsupported+=n
        try:r.cash.parse_report(pages,doc['effective_fiscal_year'],normative_basis=req['normative_basis'])
        except (ValueError,KeyError,ArithmeticError) as exc:assert type(exc).__name__==case['error_type'] and str(exc)==case['error'];errors[case['error']]+=1
        else:raise AssertionError('unsupported case is now supported')
    else:assert not(old['cover_code_consistent'] and old['cover_annual_year_consistent']) and case['report'] is None
    if (i+1)%200==0:print('root checked',i+1,flush=True)
assert counts==terminal['summary']['status_counts'] and cells==terminal['summary']['raw_monetary_cells'] and controls==terminal['summary']['protected_asset_cells_compared'];assert len(qa)==4
assert not r.changed(known) and r.tree(out)==captures
local=base/'cash-accrual-original-source-root-audit-v1-20261023';assert not local.exists();local.mkdir();(local/'visual-review-candidates.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
summary={**terminal['summary'],'status':'ROOT_SHARED_GRAMMAR_AND_SEPARATE_LITERAL_NORMALIZATION_CHECKED_NOT_FACTOR_ADMITTED','request_sha256':h,'independent_literal_decimal_normalizations':cells,'source_units':dict(units),'negative_source_cells':dict(negative),'protected_asset_comparisons_on_unsupported_NI_CFO_cases':protected_on_unsupported,'status_counts_by_fiscal_year':{y:dict(c) for y,c in status_by_year.items()},'visual_QA_candidates':[{k:v for k,v in d.items() if k!='fields'} for d in qa],'all_inputs_unchanged':True,'all_outputs_unchanged':True,'input_count':len(known),'local_artifact_count':len(captures),'ratios_rankings_or_returns_computed':False,'2026_financial_or_market_values_read':False,'objective_achieved':False,'shared_source_grammar_and_same_author_root_check_not_independent_audit':True}
(local/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');(local/'root-context.json').write_text(json.dumps({'all_input_sha256':known,'all_capture_sha256':captures},ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
