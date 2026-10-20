"""Compile separately authenticated vendor/primary rows without editing them.

The caller must verify the frozen packet, reviewed-manifest and PDF hashes.
Proofs and receipts belong to the evaluator, never the decision snapshot.
No adjustment factor is an input to an entitlement calculation.
"""
from datetime import date
from decimal import Decimal
from pathlib import PurePath
import re
from stock_rsi.broker import money
from stock_rsi.data import digest
from stock_rsi.stock_distribution_account import StockDistribution,StockDistributionAccount


def _day(text):
    if not isinstance(text,str):raise ValueError('canonical event date required')
    value=date.fromisoformat(text)
    if value.isoformat()!=text:raise ValueError('canonical event date required')
    return value


def compile_distribution_events(packets,proofs,calendar):
    if proofs.get('cash_overrides'):
        raise ValueError('cash override needs a separately supported source contract')
    documents={}
    for doc in proofs['documents']:
        name=doc['file'];sha=doc['sha256']
        if (not isinstance(name,str) or PurePath(name).name!=name or name in documents
                or not re.fullmatch('[0-9a-f]{64}',sha) or _day(doc['day'])>calendar.days[-1]):
            raise ValueError('unique pre-cutoff primary document identity required')
        documents[name]=doc
    source=[]
    for code,packet in sorted(packets.items()):
        if not re.fullmatch('(SH|SZ)[0-9]{6}',code) or packet['instrument']!=code:
            raise ValueError('raw distribution instrument identity changed')
        source.extend((code,row,'VENDOR_DISTRIBUTION',None) for row in packet['distributions'])
    for supplement in proofs.get('supplementary_distributions',[]):
        code=supplement['instrument']
        if code not in packets:raise ValueError('supplement outside authenticated source universe')
        source.append((code,supplement['record'],'PRIMARY_NOTICE_SUPPLEMENT',supplement))
    stock_proofs=proofs.get('stock_dividend_tax_bases',{});capital_proofs=proofs.get('capital_tax',{})
    consumed_stock=set();consumed_capital=set();seen=set();events=[];receipts=[]

    def bind(proof,code,row):
        doc=documents.get(proof['source_file'])
        if (doc is None or doc['sha256']!=proof['source_sha256'] or doc['instrument']!=code
                or doc['day']!=row['dividPlanDate']):
            raise ValueError('primary proof is not bound to original instrument and announcement')
        return doc['sha256']

    for code,row,origin,supplement in source:
        if row['code']!=code[:2].lower()+'.'+code[2:]:raise ValueError('provider distribution security identity changed')
        key=code+'|'+row['dividOperateDate']
        if key in seen:raise ValueError('same-date distributions need separate primary resolution')
        seen.add(key);primary=[]
        if supplement:primary.append(bind(supplement,code,row))
        if not row['dividCashPsBeforeTax'] or not row['dividStocksPs']:
            raise ValueError('unknown cash or stock distribution component')
        cash=money(row['dividCashPsBeforeTax']);stock=money(row['dividStocksPs'])
        tax=stock_proofs.get(key);income=Decimal(0);stock_verified=False
        if tax is not None:
            consumed_stock.add(key);primary.append(bind(tax,code,row))
            if (tax.get('verified') is not True or stock<=0
                    or stock!=money(tax['expected_stock_per_original_share'])):
                raise ValueError('stock-tax proof no longer matches original stock ratio')
            income=money(tax['taxable_income_per_original_share']);stock_verified=True
            if income<=0:raise ValueError('positive verified taxable stock income required')
        capital_text=row['dividReserveToStockPs']
        if not capital_text:
            display=row.get('dividCashStock','')
            cash_only=(cash>0 and stock==0 and display.startswith('10派') and '送' not in display
                       and '转' not in display and not row['dividStockMarketDate'])
            verified_stock_only=(stock_verified and display.startswith('10送') and '转' not in display)
            if not (cash_only or verified_stock_only):raise ValueError('unknown capital-transfer component')
            capital_text='0'
        capital=money(capital_text);capital_verified=False
        exemption=capital_proofs.get(key)
        if exemption is not None:
            consumed_capital.add(key);primary.append(bind(exemption,code,row))
            if capital<=0 or exemption.get('verified_exempt') is not True:
                raise ValueError('capital exemption does not match a positive capital transfer')
            capital_verified=True
        announced,recorded,ex_date=map(_day,(row['dividPlanDate'],row['dividRegistDate'],row['dividOperateDate']))
        paid=_day(row['dividPayDate']) if row['dividPayDate'] else None
        listed=_day(row['dividStockMarketDate']) if row['dividStockMarketDate'] else None
        if recorded not in calendar.days or ex_date not in calendar.days:
            raise ValueError('record and ex dates need observed explicit source sessions')
        identity={'instrument':code,'source_kind':origin,'source_distribution':row,
                  'primary_source_sha256':sorted(set(primary)),
                  'effective_stock_taxable_income_per_original_share':str(income),
                  'capital_tax_exempt_verified':capital_verified,'stock_tax_basis_verified':stock_verified}
        event=StockDistribution(digest(identity),code,announced,recorded,ex_date,paid,listed,cash,capital,
            capital_verified,stock_per_share=stock,stock_taxable_income_per_share=income,
            stock_tax_basis_verified=stock_verified)
        events.append(event)
        receipts.append({'event_id':event.event_id,'instrument':code,'ex_date':ex_date.isoformat(),
            'source_kind':origin,'source_row_sha256':digest(row),'primary_source_sha256':sorted(set(primary)),
            'blank_capital_resolved_as_zero':not bool(row['dividReserveToStockPs']),
            'requires_zero_record_ownership_if_tax_unverified':bool(capital>0 and not capital_verified
                or stock>0 and not stock_verified)})
    if consumed_stock!=set(stock_proofs) or consumed_capital!=set(capital_proofs):
        raise ValueError('orphan tax proof outside original distributions')
    # Reuse the account's timing/finite-value checks without running prices or ROI.
    StockDistributionAccount(calendar,'1',events,tax_reserve_rate='.2')
    return tuple(events),tuple(receipts)
