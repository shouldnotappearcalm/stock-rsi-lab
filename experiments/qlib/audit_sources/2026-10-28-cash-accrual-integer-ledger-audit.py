"""Pinned stdlib ledger with explicit allocator/band adapters; no production imports."""
import ast,copy,hashlib,json,math
from fractions import Fraction
from pathlib import Path

ROOT=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead');BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
POLICY='cn_total_ni_minus_cfo_mean_assets_bottom_decile'
HELPER=ROOT/'experiments/qlib/audit_sources/2026-10-21-low-beta60-raw-daily-audit.py'
HELPER_SHA='aa8763240039be18551f2707b5cb415b0957bda446068caa1440c1604f6ae2fc'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}

def budgeted(equity,owned,weights,marks):
    equity=Fraction(equity);budget=equity*sum(Fraction(str(w)) for w in weights.values());post={};options=[];tol=max(Fraction(1,10**8),equity/Fraction(10**10))
    for c,w in sorted(weights.items()):
        if not w:continue
        price=Fraction(marks[c]);wanted=equity*Fraction(str(w))/price;held=owned.get(c,0)
        base=(held+((wanted-held)/100+Fraction(1,10**10)).__floor__()*100 if wanted>=held else (wanted/100+Fraction(1,10**10)).__floor__()*100)
        post[c]=base;proposed=base+100 if wanted>=held else min(base+100,held);cost=(proposed-base)*price;gain=cost*(2*(wanted-base)*price-cost)
        if cost>0 and gain>0:options.append((float(format(float(gain),'.12g')),c,proposed,cost))
    left=budget-sum(post[c]*Fraction(marks[c]) for c in post);assert left>=-tol
    for _,c,q,cost in sorted(options,key=lambda x:(-x[0],x[1])):
        if cost<=left+tol:post[c]=q;left-=cost
    orders=[]
    for c in sorted(set(owned)|set(post)):
        delta=post.get(c,0)-owned.get(c,0)
        if delta:orders.append(('BUY' if delta>0 else 'SELL',c,abs(delta)))
    orders.sort(key=lambda x:(x[0]!='SELL',x[1]));return orders,post


def namespace():
    assert sha(HELPER)==HELPER_SHA
    module=ast.parse(HELPER.read_text());nodes=[n for n in module.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef))]
    for n in nodes:
        if isinstance(n,ast.Import):assert all(v.name in {'argparse','copy','csv','hashlib','json'} for v in n.names)
        if isinstance(n,ast.ImportFrom):assert n.module in {'collections','datetime','decimal','pathlib','zoneinfo'}
    code=ast.unparse(ast.Module(body=nodes,type_ignores=[]))
    assert code.count("'low_beta60'")==1 and code.count("'frozen monthly low_beta60 target, physical-share execution'")==1
    code=code.replace("'low_beta60'",repr(POLICY)).replace("'frozen monthly low_beta60 target, physical-share execution'",repr('frozen monthly '+POLICY+' target, physical-share execution'))
    # An independent rational implementation replaces the old floor-only sizing block.
    a=code.index('            planned = []');b=code.index('            assert planned ==',a)
    code=code[:a]+"            planned, post = budgeted(equity, owned, target['weights'], marks)\n            assert intent['allocation_receipt']['post_order_normalized_positions'] == post\n            assert intent['allocation_receipt']['execution_prices_or_returns_used'] is False\n"+code[b:]
    assert code.count("ref * D('1.095')")==1 and code.count("ref * D('.905')")==1
    code=code.replace("ref * D('1.095')","cents(ref * D('1.10'))").replace("ref * D('.905')","cents(ref * D('.90'))")
    code=code.replace("blocked = price >=", "assert cents(ref * D('.90')) <= price <= cents(ref * D('1.10'))\n                blocked = price >=")
    code=code.replace('len(registered) == 179','len(registered) == 72').replace("'record_and_ex_events_reconstructed': 179","'record_and_ex_events_reconstructed': 72")
    ns={'sha':sha,'read':read,'budgeted':budgeted};exec(compile(code,str(HELPER)+'[cash explicit adapters]','exec'),ns);return ns


def main():
    run=BASE/'cash-accrual-integer-pre2026-v1-20261028';request=ROOT/'experiments/qlib/cash-accrual-integer-request.json';h='4a2b575bf42b25ffb4b97bd657ff0960929f4a5c122af8d83f3dd1d2e9198916';assert sha(request)==h;req=read(request);t=read(run/'terminal.json');caps=tree(run)
    assert t['complete'] and t['request_sha256']==h and caps=={**t['capture_sha256'],'terminal.json':sha(run/'terminal.json')}
    known={**req['input_sha256'],str(request):h,str(HELPER):HELPER_SHA,str(Path(__file__).resolve()):sha(__file__)};assert all(sha(p)==v for p,v in known.items())
    raw=BASE/'cash-accrual-raw-pre2026-v1-20261028';m=read(raw/'manifest.json');sessions=read(raw/'calendar.json')['sessions'];packets={c:read(raw/'codes'/(c+'.json')) for c in m['per_code_sha256']};bars={c:{v['date']:v for v in p['bars']} for c,p in packets.items()}
    targets=read(ROOT/'experiments/qlib/cash-accrual-pre2026-targets.json')[POLICY];proof=read(ROOT/'experiments/qlib/cash-accrual-primary-reviewed.json');events={}
    for c,p in sorted(packets.items()):
        for v in p['distributions']:
            key=c+'|'+v['dividOperateDate'];tax=proof['capital_tax'].get(key);capital=v['dividReserveToStockPs'];cash=v['dividCashPsBeforeTax'];stock=v['dividStocksPs']
            assert cash and stock
            if not capital:assert float(cash)>0 and float(stock)==0 and v['dividCashStock'].startswith('10派') and '转' not in v['dividCashStock'] and '送' not in v['dividCashStock'] and not v['dividStockMarketDate'];capital='0'
            primary=[tax['source_sha256']] if tax else [];verified=tax is not None
            if verified:assert tax['verified_exempt'] and tax['expected_capital_per_share']==capital and any(d['instrument']==c and d['sha256']==tax['source_sha256'] and d['day']==v['dividPlanDate'] for d in proof['documents'])
            identity={'instrument':c,'source_kind':'VENDOR_DISTRIBUTION','source_distribution':v,'primary_source_sha256':primary,'effective_stock_taxable_income_per_original_share':'0','capital_tax_exempt_verified':verified,'stock_tax_basis_verified':False};eid=digest(identity)
            assert eid not in events;events[eid]={'event_id':eid,'instrument':c,'announced':v['dividPlanDate'],'recorded':v['dividRegistDate'],'ex_date':v['dividOperateDate'],'pay_date':v['dividPayDate'] or None,'listed':v['dividStockMarketDate'] or None,'cash_per_share':cash,'capital_per_share':capital,'capital_tax_exempt_verified':verified,'stock_per_share':stock,'stock_taxable_income_per_share':'0','stock_tax_basis_verified':False}
    assert len(events)==72 and list(events.values())==read(run/'events.json')
    ns=namespace();ns.update(sessions=sessions,bars=bars,targets=targets,events=events);cases={};results={}
    for cost in ('20','40'):
        c=read(run/cost/'case.json');v={**c,'rows':c['days']};cases[cost]=v;results[cost]=ns['audit'](v,int(cost),t['results_by_extra_bps'][cost])
    controls={}
    for name in ('erased_fee','forged_nav','false_record_quantity','wrong_target_quantity','unfilled_as_filled','missing_capital_credit'):
        v=copy.deepcopy(cases['40'])
        if name=='erased_fee':v['fills'][0]['cost']='0'
        elif name=='forged_nav':v['rows'][-1]['equity']=str(ns['D'](v['rows'][-1]['equity'])+1)
        elif name=='false_record_quantity':next(x for x in v['corporate_ledger'] if x['kind']=='RECORD_DATE_OWNERSHIP')['quantity']+=100
        elif name=='wrong_target_quantity':v['intents'][0]['decisions'][0]['quantity']+=100
        elif name=='unfilled_as_filled':next(x for x in v['orders'] if x['status']=='UNFILLED_MARKET_CONSTRAINT')['status']='FILLED'
        else:next(x for x in v['corporate_ledger'] if x['kind']=='CAPITAL_SHARES_LISTED')['quantity']+=1
        try:ns['audit'](v,40,t['results_by_extra_bps']['40'])
        except (AssertionError,KeyError):controls[name]=True
        else:raise AssertionError('arithmetic control accepted '+name)
    assert all(sha(p)==v for p,v in known.items()) and tree(run)==caps
    result={'status':'PASS_SEPARATE_INTEGER_LEDGER_SNAPSHOTS_AND_RATIONAL_ALLOCATOR','request_sha256':h,'all_input_sha256':known,'all_output_sha256':caps,
            'cases':results,'arithmetic_negative_controls_rejected':controls,'negative_controls_use_hash_gate':False,'all_inputs_outputs_unchanged':True,
            'adaptations':['two policy labels','two179to72event count constants','ordinary cent-rounded10%bands','rational reimplementation of greedy budgeted allocator and receipt check'],
            'imports_production_account_or_broker_or_signal':False,'shared_pinned_ledger_algorithm_same_author_not_independent_assurance':True,
            '2026_portfolio_return_computed':False,'historical_arrival_verified':False,'actual_FIFO_verified':False,'objective_achieved':False}
    out=BASE/'cash-accrual-integer-ledger-audit-v2-20261028';assert not out.exists();out.mkdir();(out/'proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':result['status'],'cases':results,'controls':controls}),flush=True)
if __name__=='__main__':main()
