"""A known primary correction, loaded only after its own source clock.

The caller authenticates original PDF/payload bytes and the substantive review.
This narrow adapter does not establish cohort-wide amendment completeness.
"""
from copy import deepcopy
from datetime import date,datetime,time,timezone
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo
import re
from stock_rsi.data import digest
from stock_rsi.gross_profitability_monthly import rank_decile

RECONSTRUCTED='RECONSTRUCTED_PUBLICATION_DAY_END'
OBSERVED='OBSERVED_ARRIVAL'
CONTRACT='KNOWN_PRIMARY_OPERATING_ASSET_AMENDMENT_V1'
NAMES=('operating_profit_prior_assets_top_decile_conditional','eligible_equal_weight','operating_profit_prior_assets_bottom_decile_control')

def need(value,message):
    if not value:raise ValueError(message)

def aware(value):
    v=datetime.fromisoformat(value);need(v.tzinfo is not None and v.utcoffset() is not None,'aware source/decision clock required');return v

def day(value):
    v=date.fromisoformat(value);need(v.isoformat()==value,'canonical source date required');return v

def amount(value):
    need(type(value) is str and re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?',value),'plain signed CNY source literal required');v=Decimal(value);need(v.is_finite(),'finite CNY source literal');return v

def apply_known_amendments(observation,as_of,metadata,loader,mode):
    need(mode in (RECONSTRUCTED,OBSERVED),'explicit source visibility mode');clock=aware(as_of);result=deepcopy(observation);receipts=[];applied=set()
    for m in metadata:
        if (m['instrument'],m['capture_key'],m['current_fiscal_end'],m['prior_asset_fiscal_end']) != tuple(result[k] for k in ('instrument','capture_key','current_fiscal_end','prior_asset_fiscal_end')):continue
        need(m['original_record_id']==result['record_id'],'known correction base record changed')
        public=datetime.combine(day(m['publication_day']),time.max,ZoneInfo('Asia/Shanghai'));observed=aware(m['captured_at_utc']);need(observed>=public,'coherent correction capture clock')
        if clock<(public if mode==RECONSTRUCTED else max(public,observed)):continue
        need(m['key'] not in applied,'duplicate known correction');applied.add(m['key'])
        p=loader(m['key']);need(digest(p)==m['payload_digest'] and p['contract']==CONTRACT,'exact known primary correction payload')
        need(all(p[k]==m[k] for k in ('instrument','capture_key','original_record_id','current_fiscal_end','prior_asset_fiscal_end','publication_day')) and p['original_source_sha256']==result['source_sha256'],'primary correction original identity/period')
        docs=p['documents'];need(type(docs) is list and len(docs)==2 and len({d['sha256'] for d in docs})==2 and all(re.fullmatch('[a-f0-9]{64}',d['sha256']) and d['pages'] and all(type(n) is int and n>0 for n in d['pages']) for d in docs),'both original correction PDF/page identities')
        before,after,numerator=map(amount,(p['before_assets_CNY'],p['after_assets_CNY'],p['unchanged_numerator_CNY']))
        need(before>0 and after>0 and before!=after and before==amount(result['lagged_assets_CNY']) and numerator==amount(result['operating_profit_CNY']) and Fraction(result['score_fraction'])==Fraction(numerator)/Fraction(before),'correction binds original exact factor inputs')
        need(amount(p['revenue_delta_CNY'])==amount(p['cost_delta_CNY'])!=0 and p['selling_admin_unchanged'] is True,'only equal revenue/cost correction preserves this numerator')
        original_id=result['record_id'];original_public=result['publication_day'];result.update(lagged_assets_CNY=p['after_assets_CNY'],score_fraction=str(Fraction(numerator)/Fraction(after)),original_record_id=original_id,original_publication_day=original_public,publication_day=p['publication_day'],amendment_payload_digest=m['payload_digest'],amendment_visibility_mode=mode)
        result['record_id']=digest({'original_record_id':original_id,'amendment_payload_digest':m['payload_digest'],'corrected_score_fraction':result['score_fraction']})
        receipts.append({'instrument':result['instrument'],'original_record_id':original_id,'effective_record_id':result['record_id'],'amendment_payload_digest':m['payload_digest'],'publication_day':p['publication_day'],'as_of':as_of,'visibility_mode':mode})
    return result,receipts

def selections(scores):return {NAMES[0]:rank_decile(scores),NAMES[1]:tuple(sorted(scores)),NAMES[2]:rank_decile(scores,lowest=True)}

def reform_receipts(receipts,metadata,loader,mode):
    targets={n:{} for n in NAMES};out=[];seen=set()
    for original in receipts:
        r=deepcopy(original);d=day(r['formation_asof']);execution=day(r['execution_session']);need(d<execution and d.strftime('%Y-%m')!=execution.strftime('%Y-%m') and execution.isoformat() not in seen,'unique next-month formation');seen.add(execution.isoformat())
        at=datetime.combine(d,time(15,5),ZoneInfo('Asia/Shanghai')).isoformat();old=r['ranked_source'];scores={c:Fraction(v['score_fraction']) for c,v in old.items()}
        expected=selections(scores);need(set(r['selections'])==set(NAMES) and all(list(expected[n])==list(r['selections'][n]) for n in NAMES),'reproduce every original frozen selection before patch')
        updated={};changes=[]
        for code,v in old.items():
            need(v['instrument']==code,'factor issuer matches ranking key');updated[code],rs=apply_known_amendments(v,at,metadata,loader,mode);changes.extend(rs)
        choices=selections({c:Fraction(v['score_fraction']) for c,v in updated.items()});r.update(ranked_source=updated,selections={k:list(v) for k,v in choices.items()},known_amendment_receipts=changes);out.append(r)
        for n,codes in choices.items():targets[n][execution.isoformat()]={'as_of':d.isoformat(),'weights':{c:.95/len(codes) for c in codes}}
    return targets,out
