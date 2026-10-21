"""Evaluator-only primary composition/zero completion; immutable vendor inputs.

The caller authenticates packet/PDF bytes and the substantive primary review.
This module binds that evidence and derives a view; it grants no tax, historical
arrival, registry rounding or source-completeness certification. Old compilers
and account settlement rules remain unchanged.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import PurePath
import re

from stock_rsi.data import digest
from stock_rsi.distribution_event_compiler_v2 import compile_distribution_events_v2

CONTRACT = 'PRIMARY_EVENT_COMPONENT_COMPLETION_V1'
CASH_KIND = 'PRIMARY_TWO_CASH_COMPONENT_SUM'
ZERO_KIND = 'PRIMARY_STOCK_ZERO_CAPITAL'
DATES = {'publication_day':'dividPlanDate','record_date':'dividRegistDate',
         'ex_date':'dividOperateDate','cash_payment_date':'dividPayDate',
         'stock_listing_date':'dividStockMarketDate'}
COMMON = {'verified','version','kind','instrument','source_file','source_sha256',
          'primary_pages','stock_per_original_share','capital_per_original_share',*DATES}
ROW_FIELDS = {'code','dividCashPsBeforeTax','dividStocksPs','dividReserveToStockPs',*DATES.values()}


def _day(value, *, optional=False):
    if optional and value is None:return None
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('canonical primary date required')
    return value


def _amount(value, *, positive=False):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value):
        raise ValueError('plain nonnegative decimal component required')
    result=Decimal(value)
    if not result.is_finite() or positive and result<=0:
        raise ValueError('positive finite component required')
    return result


def _documents(proofs):
    result={}
    for doc in proofs['documents']:
        name=doc['file']
        if (not isinstance(name,str) or not name or PurePath(name).name!=name or '\\' in name
                or name in result or not isinstance(doc['sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',doc['sha256'])
                or not re.fullmatch('(SH|SZ)[0-9]{6}',doc['instrument'])):
            raise ValueError('unique primary document identity required')
        _day(doc['day']);result[name]=doc
    return result


def _bind(proof, key, rows, documents):
    kind=proof.get('kind')
    extra=({'components','combined_cash_per_original_share'} if kind==CASH_KIND
           else {'source_row_sha256','cash_per_original_share'} if kind==ZERO_KIND else None)
    if (extra is None or set(proof)!=COMMON|extra or proof['verified'] is not True
            or type(proof['version']) is not int or proof['version']!=1):
        raise ValueError('explicit versioned component proof with exact fields required')
    code,ex=key.split('|')
    if proof['instrument']!=code or proof['ex_date']!=ex:
        raise ValueError('component proof issuer/event key changed')
    doc=documents.get(proof['source_file'])
    if (doc is None or doc['sha256']!=proof['source_sha256'] or doc['instrument']!=code
            or doc['day']!=proof['publication_day']):
        raise ValueError('component proof not bound to original PDF/security/publication')
    pages=proof['primary_pages']
    if (not isinstance(pages,list) or not pages or any(type(p) is not int or p<1 for p in pages)
            or pages!=sorted(set(pages))):
        raise ValueError('explicit unique positive primary pages required')
    for field in DATES:_day(proof[field],optional=field in ('cash_payment_date','stock_listing_date'))
    for row in rows:
        if not ROW_FIELDS<=set(row) or row['code']!=code[:2].lower()+'.'+code[2:]:
            raise ValueError('original source issuer/fields changed')
        for field,source in DATES.items():
            at=row[source] or None
            if field in ('publication_day','record_date','ex_date') and at is None:
                raise ValueError('original mandatory event date missing')
            if proof[field]!=at:raise ValueError('original and primary event dates differ')
    return doc


def _cash_view(rows, proof):
    if len(rows)!=2 or len({digest(r) for r in rows})!=2:
        raise ValueError('exactly two distinct original cash components required')
    components=proof['components']
    if (not isinstance(components,list) or len(components)!=2
            or any(set(c)!={'source_row_sha256','cash_per_original_share'} for c in components)
            or len({c['source_row_sha256'] for c in components})!=2):
        raise ValueError('exactly two unique source-row component bindings required')
    by_hash={c['source_row_sha256']:c for c in components}
    if set(by_hash)!={digest(r) for r in rows}:raise ValueError('missing or rewritten cash component')
    if (_amount(proof['stock_per_original_share'])!=0 or _amount(proof['capital_per_original_share'])!=0
            or proof['stock_listing_date'] is not None or proof['cash_payment_date'] is None):
        raise ValueError('primary composition is cash only with no listing')
    amounts=[]
    for row in rows:
        amount=_amount(row['dividCashPsBeforeTax'],positive=True)
        if (amount!=_amount(by_hash[digest(row)]['cash_per_original_share'],positive=True)
                or _amount(row['dividStocksPs'])!=0
                or row['dividReserveToStockPs']!='' and _amount(row['dividReserveToStockPs'])!=0
                or row['dividStockMarketDate']!=''):
            raise ValueError('cash component amount or cash-only economics changed')
        amounts.append(Fraction(amount))
    combined=_amount(proof['combined_cash_per_original_share'],positive=True)
    if sum(amounts,Fraction(0))!=Fraction(combined):
        raise ValueError('declared combined entitlement must equal exact component sum, not price reference')
    result=deepcopy(rows[0])
    result.update(dividCashPsBeforeTax=proof['combined_cash_per_original_share'],
                  dividReserveToStockPs='0',dividCashStock='PRIMARY_NOTICE_TWO_CASH_COMPONENT_SUM')
    if 'dividCashPsAfterTax' in result:result['dividCashPsAfterTax']=''
    return result


def _zero_view(rows, proof):
    if len(rows)!=1 or proof['source_row_sha256']!=digest(rows[0]):
        raise ValueError('one exact original stock row required')
    row=rows[0]
    if (row['dividReserveToStockPs']!='' or _amount(proof['capital_per_original_share'])!=0
            or _amount(row['dividStocksPs'],positive=True)!=_amount(proof['stock_per_original_share'],positive=True)
            or _amount(row['dividCashPsBeforeTax'])!=_amount(proof['cash_per_original_share'])
            or proof['stock_listing_date'] is None):
        raise ValueError('only blank capital may be completed; original stock/cash must match primary')
    result=deepcopy(row);result['dividReserveToStockPs']='0'
    return result


def project_primary_event_components(packets, proofs):
    """Return a deep-copied evaluator view and proof-bound projection receipts."""
    # V2 cannot consume V3-only precision proofs, even on unrelated events.
    # Validate before the empty-completion fast path to avoid silent omission.
    precision=proofs.get('component_precision_overrides',{})
    if not isinstance(precision,dict) or precision:
        raise ValueError('V3 component precision proofs are unsupported by this V2 adapter')
    corrections=proofs.get('primary_event_components',{})
    if not isinstance(corrections,dict):raise ValueError('component proofs must be keyed by event')
    if not corrections:return deepcopy(packets),()
    if proofs.get('primary_event_component_contract')!=CONTRACT:
        raise ValueError('unsupported primary component contract')
    # This contract cannot authorize a tax basis or compose another correction.
    for field in ('capital_tax','stock_dividend_tax_bases','cash_overrides'):
        if set(corrections)&set(proofs.get(field,{})):
            raise ValueError('component completion and other per-event contracts cannot overlap')
    for supplement in proofs.get('supplementary_distributions',[]):
        if supplement['instrument']+'|'+supplement['record']['dividOperateDate'] in corrections:
            raise ValueError('derived vendor completion cannot also be a primary supplement')
    documents=_documents(proofs);groups={}
    for code,packet in packets.items():
        if not re.fullmatch('(SH|SZ)[0-9]{6}',code) or packet['instrument']!=code:
            raise ValueError('original packet security identity changed')
        for row in packet['distributions']:
            groups.setdefault(code+'|'+row['dividOperateDate'],[]).append(row)
    if not set(corrections)<=set(groups):raise ValueError('orphan primary component proof')
    views={};receipts=[]
    for key,proof in corrections.items():
        rows=groups[key];doc=_bind(proof,key,rows,documents)
        derived=_cash_view(rows,proof) if proof['kind']==CASH_KIND else _zero_view(rows,proof)
        views[key]=derived
        receipt={'contract':CONTRACT,'version':1,'event_key':key,'source_kind':proof['kind'],
            'original_source_row_sha256':[digest(r) for r in rows],'derived_source_row_sha256':digest(derived),
            'primary_source_sha256':doc['sha256'],'source_file':doc['file'],'primary_pages':deepcopy(proof['primary_pages']),
            'primary_component_proof_sha256':digest(proof),'original_source_rows_modified':False,
            'stock_tax_basis_granted':False,'capital_tax_exemption_granted':False}
        if proof['kind']==CASH_KIND:
            receipt.update(combined_cash_per_original_share=proof['combined_cash_per_original_share'],
                cash_settlement_contract='ONE_COMBINED_PER_REGISTERED_SHARE_EVENT_ACCOUNT_EXISTING_AGGREGATE_ROUNDING',
                separate_component_cent_settlement_equivalence_certified=False)
        receipts.append(receipt)
    result=deepcopy(packets)
    for code,packet in result.items():
        emitted=set();rows=[]
        for row in packet['distributions']:
            key=code+'|'+row['dividOperateDate']
            if key not in views:rows.append(row)
            elif key not in emitted:rows.append(deepcopy(views[key]));emitted.add(key)
        packet['distributions']=rows
    return result,tuple(receipts)


def compile_primary_event_components(packets, proofs, calendar):
    """Use unchanged V2 physics/precision, then relabel only newly derived events."""
    projected,projection=project_primary_event_components(packets,proofs)
    events,receipts=compile_distribution_events_v2(projected,proofs,calendar)
    if not projection:return events,receipts
    by_key={r['event_key']:r for r in projection};result=[];evidence=[];consumed=set()
    for event,receipt in zip(events,receipts):
        key=event.instrument+'|'+event.ex_date.isoformat();record=by_key.get(key)
        if record is None:result.append(event);evidence.append(receipt);continue
        if (receipt['source_kind']!='VENDOR_DISTRIBUTION'
                or receipt['source_row_sha256']!=record['derived_source_row_sha256']
                or event.stock_tax_basis_verified or event.capital_tax_exempt_verified
                or event.stock_taxable_income_per_share!=0):
            raise ValueError('canonical derived view unexpectedly carries a different contract or tax flag')
        identity={'source_kind':record['source_kind'],'canonical_derived_event_id':event.event_id,
                  'projection_receipt_sha256':digest(record)}
        updated=replace(event,event_id=digest(identity));result.append(updated);consumed.add(key)
        evidence.append({**receipt,'event_id':updated.event_id,'source_kind':record['source_kind'],
            'canonical_derived_event_id':event.event_id,
            'original_source_row_sha256':record['original_source_row_sha256'],
            'derived_source_row_sha256':record['derived_source_row_sha256'],
            'primary_source_sha256':sorted(set(receipt['primary_source_sha256']+[record['primary_source_sha256']])),
            'projection_receipt_sha256':digest(record),'projection_receipt':deepcopy(record)})
    if consumed!=set(by_key):raise ValueError('derived projection missing canonical compiled event')
    return tuple(result),tuple(evidence)
