"""Full-window date adapter; corporate algorithms are identical to development.

Inputs must first be authenticated by the experiment's frozen manifests.
No original vendor packet is changed. Unsupported held stock dividends fail.
"""
import copy
from datetime import date
from decimal import Decimal

from scripts.capture_reversal_raw_extension import full_target_codes as target_codes,START,END
from scripts.capture_low_risk_raw_account_data import source_code
from scripts.run_low_risk_raw_share_validation import canonical_distributions
from stock_rsi.broker import money
from stock_rsi.data import digest
from stock_rsi.raw_share_account import Distribution


def resolve_cash_components(packets,proofs):
    """Consolidate documented same-date cash parts; preserve immutable inputs."""
    result=copy.deepcopy(packets);receipts=[];seen=set()
    fields=('code','dividPlanDate','dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate')
    for rule in proofs.get('resolved_cash_components',[]):
        code,day=rule['instrument'],rule['ex_date'];key=(code,day)
        if key in seen or code not in result:raise ValueError('duplicate/unknown cash resolution')
        seen.add(key)
        rows=[r for r in result[code]['distributions'] if r['dividOperateDate']==day]
        expected=rule['source_row_digests'];actual=[digest(r) for r in rows]
        if len(rows)<2 or len(set(expected))!=len(expected) or sorted(actual)!=sorted(expected):
            raise ValueError('primary cash components no longer match frozen source rows')
        replacement=copy.deepcopy(rule['replacement_record'])
        if replacement['code']!=source_code(code) or replacement['dividOperateDate']!=day:
            raise ValueError('cash resolution security/date mismatch')
        for row in [*rows,replacement]:
            if (any(row[f]!=replacement[f] for f in fields) or money(row['dividStocksPs'])!=0
                    or money(row.get('dividReserveToStockPs') or '0')!=0):
                raise ValueError('resolution must preserve cash-only identity and payout timing')
        amount=sum((money(r['dividCashPsBeforeTax']) for r in rows),Decimal(0))
        if amount<0 or money(replacement['dividCashPsBeforeTax'])!=amount:
            raise ValueError('cash component consolidation must conserve declared total')
        if not rule.get('source_file') or not rule.get('source_sha256'):raise ValueError('primary notice reference required')
        remaining=[r for r in result[code]['distributions'] if r['dividOperateDate']!=day]
        remaining.append(replacement);result[code]['distributions']=remaining
        receipts.append({'instrument':code,'ex_date':day,'source_row_digests':actual,
            'replacement_record_digest':digest(replacement),'combined_cash_per_share':str(amount),
            'source_file':rule['source_file'],'source_sha256':rule['source_sha256']})
    return result,receipts


def prepare_events(packets,targets,proofs):
    if set(packets)!=set(target_codes(targets)):raise ValueError('exact frozen development universe required')
    merged=copy.deepcopy(packets);first={}
    for day,target in sorted(targets.items()):
        for code in target['weights']:first.setdefault(code,day)
    for supplement in proofs.get('supplementary_distributions',[]):
        code=supplement['instrument'];row=copy.deepcopy(supplement['record'])
        if code not in merged or row['code']!=source_code(code):raise ValueError('primary distribution security mismatch')
        if any(r['dividOperateDate']==row['dividOperateDate'] for r in merged[code]['distributions']):
            raise ValueError('primary supplement duplicates existing distribution')
        if not supplement.get('source_file') or not supplement.get('source_sha256'):
            raise ValueError('primary notice evidence reference required')
        merged[code]['distributions'].append(row)
    for packet in merged.values():
        dates=[r['dividOperateDate'] for r in packet['distributions']]
        if len(set(dates))!=len(dates):raise ValueError('same-date corporate components need primary resolution')
    # The shared canonicalizer intentionally does not support held stock dividends.
    # Keep these source rows in merged coverage evidence; build zero-only events
    # with the true share ratio and exemption=False, which fails if ever held.
    supported=copy.deepcopy(merged);special=[]
    for code,packet in supported.items():
        retained=[]
        for row in packet['distributions']:
            stock=money(row['dividStocksPs'])
            if stock<0:raise ValueError('negative stock dividend ratio')
            if stock==0:retained.append(row);continue
            if not row['dividRegistDate']<first[code]:
                raise ValueError('stock-dividend entitlement may exist; unsupported taxation/allocation')
            capital=row.get('dividReserveToStockPs','')
            if not capital and '转' in row.get('dividCashStock',''):raise ValueError('unresolved combined share component')
            capital=money(capital or '0')
            if capital<0:raise ValueError('negative capital ratio')
            cash=money(row['dividCashPsBeforeTax']);key=code+'|'+row['dividOperateDate']
            if key in proofs.get('cash_overrides',{}):raise ValueError('unsupported combined primary override')
            event_id=digest({'instrument':code,'source_distribution':row,'effective_cash':str(cash)})
            special.append(Distribution(event_id,code,date.fromisoformat(row['dividPlanDate']),
                date.fromisoformat(row['dividRegistDate']),date.fromisoformat(row['dividOperateDate']),
                date.fromisoformat(row['dividPayDate']) if row['dividPayDate'] else None,
                date.fromisoformat(row['dividStockMarketDate']) if row['dividStockMarketDate'] else None,
                cash,stock+capital,False))
        packet['distributions']=retained
    events=(*canonical_distributions(supported,proofs),*special)
    if any(not date.fromisoformat(START)<=e.ex_date<=date.fromisoformat(END) or e.announced>date.fromisoformat(END) for e in events):
        raise ValueError('corporate event outside development cutoff')
    if len({e.event_id for e in events})!=len(events):raise ValueError('duplicate derived corporate event')
    zero_proofs=[{'event_id':e.event_id,'instrument':e.instrument,'record_date':e.recorded.isoformat(),
        'first_possible_buy':first[e.instrument],'registered_quantity_must_be':0,
        'share_ratio_retained':str(e.capital_per_share),'event_preserved':True,
        'exemption_verified':e.capital_tax_exempt_verified}
        for e in events if e.capital_per_share>0 and e.recorded.isoformat()<first[e.instrument]]
    return merged,events,zero_proofs
