"""Independent stdlib-only inventory reconstruction; no source admission or ROI."""
import hashlib,json
from collections import Counter
from decimal import Decimal
from itertools import combinations
from pathlib import Path
B=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
R=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
ROOTS=['szse-value-momentum-raw-full-v2-20261021','low-beta60-raw-horizon-20261021','reversal-raw-full-20261017','szse-value-raw-full-20261017']
IN=Path('/tmp/price-delay-horizon-raw-inventory-20261021.json');OUT=Path('/tmp/price-delay-horizon-raw-inventory-review-20261021.json')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_bytes())
def sig(rows):
    result=[]
    for x in rows:
        result.append([x['date'],x['code']]+[str(Decimal(x[k]).normalize()) if x[k] else '' for k in ['open','high','low','close','preclose','volume','amount']]+[x['tradestatus'],x['isST']])
    return result

def main():
    inv=load(IN);target=B/'price-delay-horizon-formations-20261021/candidate_targets.json'
    assert sha(target)==inv['target_sha256']=='5d122dac55da8f57934524de0b6e3640a303363aca49e0a0a09dd70d5850a923'
    ts=load(target);names=sorted({c for t in ts.values() for c in t['weights']});assert len(ts)==34 and len(names)==203
    oldroot=B/'price-delay-raw-dev-20261021';om=load(oldroot/'manifest.json');assert sha(oldroot/'manifest.json')==inv['original_raw_manifest_sha256']
    assert len(om['per_code_sha256'])==151 and set(om['per_code_sha256'])<=set(names)
    oldcal=load(oldroot/'calendar.json')['sessions'];assert sha(oldroot/'calendar.json')==om['calendar_sha256']
    manifests={};calendars={}
    for root in ROOTS:
        p=B/root/'manifest.json';assert sha(p)==inv['source_manifest_sha256'][root];manifests[root]=load(p)
        cp=B/root/'calendar.json';assert sha(cp)==manifests[root]['calendar_sha256'];calendars[root]=load(cp)['sessions']
    days=calendars[ROOTS[1]];assert len(days)==676 and days==sorted(set(days)) and days[:486]==oldcal
    assert (days[0],days[-1])==('2023-12-29','2026-10-20') and sha(B/ROOTS[1]/'calendar.json')==inv['calendar_sha256']
    assert all(x==days[:len(x)] for x in calendars.values())
    rebuilt={};route=Counter();cross=Counter();refs=0;core_pairs=0;oldcomparisons=0;all_old_hashes={};selected_baselines={}
    for code in names:
        old=None
        if code in om['per_code_sha256']:
            op=oldroot/'codes'/(code+'.json');assert sha(op)==om['per_code_sha256'][code];old=load(op);all_old_hashes[code]=sha(op)
            assert old['instrument']==code and [x['date'] for x in old['bars']]==oldcal
        options=[];packets=[]
        for root in ROOTS:
            if code not in manifests[root]['per_code_sha256']:continue
            p=B/root/'codes'/(code+'.json');h=sha(p);assert h==manifests[root]['per_code_sha256'][code]
            obj=load(p);assert obj['instrument']==code and obj['window'][0]<=obj['window'][1]<='2026-10-20'
            bars=[x for x in obj['bars'] if days[0]<=x['date']<=days[-1]];dates=[x['date'] for x in bars]
            assert dates==sorted(set(dates)) and set(dates)<=set(days)
            assert all(x['code']==code[:2].lower()+'.'+code[2:] for x in bars)
            overlap={}
            if old is not None:
                overlap={'raw_core_matches_original':sig([x for x in bars if x['date']<='2025-12-31'])==sig(old['bars'])}
                for field,label in [('distributions','distributions_match_original'),('adjustments','adjustments_match_original')]:
                    overlap[label]=[x for x in obj[field] if days[0]<=x['dividOperateDate']<='2025-12-31']==old[field]
                assert all(overlap.values());oldcomparisons+=1
            row={'root':root,'packet_sha256':h,'window':obj['window'],'source_sessions':len(bars),'first_source_session':dates[0] if dates else None,'last_source_session':dates[-1] if dates else None,'complete_676_session_coverage':dates==days,'missing_sessions':sorted(set(days)-set(dates)),'original_pre2026_overlap':overlap,'full_raw_core_sha256':hashlib.sha256(json.dumps(sig(bars),sort_keys=True,separators=(',',':')).encode()).hexdigest(),'accepted_distribution_rows_through_cutoff':sum(days[0]<=x['dividOperateDate']<=days[-1] for x in obj['distributions']),'accepted_adjustment_rows_through_cutoff':sum(days[0]<=x['dividOperateDate']<=days[-1] for x in obj['adjustments']),'quarantine_rows_not_admitted':len(obj.get('quarantine',[]))}
            options.append(row);packets.append({x['date']:x for x in bars});refs+=1
        for left,right in combinations(packets,2):
            common=sorted(set(left)&set(right));assert sig([left[d] for d in common])==sig([right[d] for d in common]);core_pairs+=1
        full=[x for x in options if x['complete_676_session_coverage']]
        status='FULL_CACHE_AVAILABLE_NOT_ADMITTED' if full else 'PARTIAL_CACHE_ONLY' if options else 'NO_RAW_CACHE'
        rebuilt[code]={'status':status,'has_original_pre2026_baseline':old is not None,'fixed_priority_full_route':full[0]['root'] if full else None,'choices':options,'common_date_core_conflicts':[]}
        cross[(status,'old' if old is not None else 'new')]+=1
        if full:route['whole_cache']+=1
        elif old is not None:route['incremental']+=1;selected_baselines[code]={'basis':'original_pre2026','packet_sha256':all_old_hashes[code]}
        elif options:
            assert all([d for d in pkt if d<='2025-12-31']==oldcal for pkt in packets)
            route['incremental']+=1;selected_baselines[code]={'basis':'cached_complete_486_prefix','root':options[0]['root'],'packet_sha256':options[0]['packet_sha256']}
        else:route['cold']+=1
        if status=='PARTIAL_CACHE_ONLY':assert all(x['missing_sessions']==['2026-10-19','2026-10-20'] for x in options)
    assert rebuilt==inv['items'],'per-item evidence differs'
    assert refs==inv['matching_cache_references']==189
    assert dict(Counter(x['status'] for x in rebuilt.values()))==inv['status_counts']
    assert not inv['original_prefix_differences'] and not inv['common_date_core_conflicts']
    assert inv['source_priority_fixed_before_inventory']==ROOTS and inv['names']==203 and inv['original_names']==151 and inv['additional_names']==52 and inv['calendar_sessions']==676 and inv['original_486_calendar_prefix_identical'] is True
    assert sha(R/'experiments/qlib/audit_sources/2026-10-21-price-delay-horizon-raw-inventory.py')==inv['inventory_code_sha256']
    assert sha(R/'docs/research/price-delay-horizon-raw-inventory-plan-2026-10-21.md')==inv['protocol_sha256']
    assert inv['network_calls']==0 and all(inv[k] is False for k in ['source_admitted_for_replay','strategy_or_targets_changed','portfolio_returns_computed','prior_2026_strategy_performance_reports_read','objective_achieved'])
    assert route=={'whole_cache':102,'incremental':80,'cold':21}
    output={'status':'BOUNDED_INDEPENDENT_RAW_INVENTORY_RECONSTRUCTION_PASS_NOT_ADMISSION','inventory_sha256':sha(IN),'review_script_sha256':sha(Path(__file__)),'target_sha256':sha(target),'checks':{'all_203_per_code_items_exactly_reconstructed':True,'all_189_packet_hashes_match_registered_manifests':True,'all_151_original_packet_hashes_verified':True,'registered_calendar_hashes_verified':4,'calendar_sessions':676,'original_calendar_sessions':486,'old_prefix_comparisons':oldcomparisons,'old_prefix_conflicts':0,'common_date_core_pair_comparisons':core_pairs,'common_date_core_conflicts':0,'partial_cache_missing_only_Oct19_Oct20':True,'all_16_new_partial_names_have_complete_486_prefix':True},'status_counts':inv['status_counts'],'old_new_cross_counts':{a+'/'+b:v for (a,b),v in sorted(cross.items())},'source_routes':dict(route),'logical_source_query_budget':{'incremental':80*3,'cold':21*5,'total':80*3+21*5},'incremental_baseline_provenance':selected_baselines,'source_manifest_sha256':inv['source_manifest_sha256'],'original_raw_manifest_sha256':inv['original_raw_manifest_sha256'],'critical':[],'important':[],'minor':[],'boundaries':['Inventory only; no source admission, raw-source queries, account replay or portfolio ROI.','Common-date cross-cache comparison covers raw price/share-volume/amount/tradestatus/isST core; cross-cache action-vintage differences are not certified absent.','Original151 overlap checks normalize financial-core number strings and compare distribution/adjustment objects exactly; no claim of all raw-bar fields byte equality.','16 new partial baselines have complete source sessions; this establishes incremental routing only, not historical arrival, complete company actions or tax evidence.','Full-cache routes still require separate admission/event verification; 345 is logical query count before separately frozen transport/admin/retry policy.','No prior-strategy 2026 financial or performance artifacts opened.'],'source_admitted_for_replay':False,'portfolio_returns_computed':False}
    OUT.write_text(json.dumps(output,indent=2)+'\n');print(OUT);print(sha(OUT));print(json.dumps({'routes':dict(route),'cross':output['old_new_cross_counts'],'query_budget':output['logical_source_query_budget']}))
if __name__=='__main__':main()
