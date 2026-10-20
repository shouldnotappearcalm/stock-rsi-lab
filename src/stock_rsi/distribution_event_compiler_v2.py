"""Primary-notice precision completion without rewriting frozen vendor rows.

The caller authenticates original packets, reviewed proofs and PDF bytes.
This contract does not certify source completeness, arrival time or tax settlement.
"""
from dataclasses import replace
from decimal import Decimal,ROUND_DOWN
import re

from stock_rsi.broker import money
from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler import compile_distribution_events
from stock_rsi.stock_distribution_account import StockDistributionAccount

CONTRACT='PRIMARY_NOTICE_CASH_PRECISION_V1'


def compile_distribution_events_v2(packets,proofs,calendar):
    corrections=proofs.get('cash_overrides',{})
    if not isinstance(corrections,dict):raise ValueError('cash precision proofs must be keyed by source event')
    if corrections and proofs.get('cash_override_contract')!=CONTRACT:
        raise ValueError('unsupported cash precision source contract')
    # The original compiler remains the authority for all unchanged economics.
    events,receipts=compile_distribution_events(packets,{**proofs,'cash_overrides':{}},calendar)
    if not corrections:return events,receipts
    documents={d['file']:d for d in proofs['documents']}
    vendor_rows={code+'|'+row['dividOperateDate']:row for code,packet in packets.items()
                 for row in packet['distributions']}
    consumed=set();result=[];evidence=[]
    for event,receipt in zip(events,receipts):
        key=event.instrument+'|'+event.ex_date.isoformat()
        proof=corrections.get(key)
        if proof is None:
            result.append(event);evidence.append(receipt);continue
        row=vendor_rows.get(key);doc=documents.get(proof['source_file'])
        if (row is None or receipt['source_kind']!='VENDOR_DISTRIBUTION'
                or proof.get('verified') is not True or proof.get('kind')!='PRIMARY_NOTICE_CASH_PRECISION'
                or proof['source_row_sha256']!=digest(row)
                or doc is None or doc['sha256']!=proof['source_sha256']
                or doc['instrument']!=event.instrument or doc['day']!=row['dividPlanDate']):
            raise ValueError('cash precision proof does not bind original row, security and announcement')
        if event.stock_per_share!=0 or event.capital_per_share!=0 or event.listed is not None:
            raise ValueError('cash precision contract only supports cash-only distributions')
        texts=(row['dividCashPsBeforeTax'],proof['expected_vendor_cash_per_share'],proof['effective_cash_per_share'])
        if any(not isinstance(t,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',t) for t in texts):
            raise ValueError('plain positive decimal cash source values required')
        vendor,expected,effective=map(money,texts)
        quantum=Decimal(1).scaleb(vendor.as_tuple().exponent)
        if (vendor<=0 or vendor!=expected or effective<=vendor
                or effective.quantize(quantum,rounding=ROUND_DOWN)!=vendor):
            raise ValueError('primary cash value is not a precision completion of the source amount')
        consumed.add(key)
        proof_sha=digest(proof)
        identity={'original_event_id':event.event_id,'source_kind':'PRIMARY_CASH_PRECISION_CORRECTION',
            'source_row_sha256':digest(row),'primary_source_sha256':doc['sha256'],
            'cash_precision_proof_sha256':proof_sha,'vendor_cash_per_share':str(vendor),
            'effective_cash_per_share':str(effective)}
        updated=replace(event,event_id=digest(identity),cash_per_share=effective)
        result.append(updated)
        evidence.append({**receipt,'event_id':updated.event_id,'original_event_id':event.event_id,
            'source_kind':'PRIMARY_CASH_PRECISION_CORRECTION',
            'primary_source_sha256':sorted(set(receipt['primary_source_sha256']+[doc['sha256']])),
            'vendor_cash_per_share':str(vendor),'effective_cash_per_share':str(effective),
            'cash_precision_proof_sha256':proof_sha})
    if consumed!=set(corrections):raise ValueError('orphan cash precision proof outside vendor distributions')
    StockDistributionAccount(calendar,'1',result,tax_reserve_rate='.2')
    return tuple(result),tuple(evidence)
