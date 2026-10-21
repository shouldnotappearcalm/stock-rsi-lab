"""Separate a primary-bound initial unit anchor for coverage validation only.

The caller authenticates original packet/PDF bytes and the content review.
This projection never supplies account prices or creates corporate entitlements.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
from stock_rsi.broker import money
from stock_rsi.data import digest


def project_primary_listing_anchor(packet,proof,sessions):
    code=packet['instrument'];listed=proof['listed_on']
    if (proof['kind']!='PRIMARY_LISTING_UNIT_ADJUSTMENT_ANCHOR'
            or proof['instrument']!=code or proof['verified_primary_listing'] is not True
            or not re.fullmatch(r'(SH|SZ)[0-9]{6}',code)
            or not re.fullmatch('[0-9a-f]{64}',proof['primary_document_sha256'])
            or proof['source_packet_digest']!=digest(packet)
            or any(type(proof[k]) is not int or proof[k]<1 for k in ('primary_listing_page','primary_issue_price_page'))):
        raise ValueError('authenticated original packet and explicit primary listing/price evidence required')
    filename=proof['source_file']
    match=re.fullmatch(re.escape(code)+r'-(\d{4}-\d{2}-\d{2})\.pdf',filename)
    if match is None or date.fromisoformat(match[1]).isoformat()!=match[1] or match[1]>listed:
        raise ValueError('pre-listing original primary document identity required')
    if (date.fromisoformat(listed).isoformat()!=listed or sessions!=sorted(set(sessions))
            or any(date.fromisoformat(s).isoformat()!=s for s in sessions) or listed not in sessions):
        raise ValueError('explicit canonical listing and exchange sessions required')
    expected=[s for s in sessions if s>=listed]
    if [r['date'] for r in packet['bars']]!=expected:
        raise ValueError('only the exact prelisting prefix may be absent')
    price=money(proof['issue_price'])
    if price<=0 or price!=price.quantize(Decimal('.01')) or money(packet['bars'][0]['preclose'])!=price:
        raise ValueError('initial raw reference must equal independently verified issue price')
    anchors=[r for r in packet['adjustments'] if r['dividOperateDate']==listed]
    if (len(anchors)!=1 or packet['adjustments'][0]!=anchors[0]
            or anchors[0]['code']!=code[:2].lower()+'.'+code[2:]
            or money(anchors[0]['backAdjustFactor'])!=1 or money(anchors[0]['adjustFactor'])!=1
            or money(anchors[0]['foreAdjustFactor'])<=0
            or digest(anchors[0])!=proof['initial_adjustment_row_sha256']
            or any(r['dividOperateDate']<=listed for r in packet['distributions'])):
        raise ValueError('one bound initial unit anchor without a conflicting distribution required')
    view=deepcopy(packet)
    view['adjustments'].pop(0)
    receipt={'kind':'COVERAGE_VALIDATION_ONLY_PRIMARY_LISTING_UNIT_ANCHOR','instrument':code,
        'listed_on':listed,'primary_document_sha256':proof['primary_document_sha256'],
        'source_packet_digest':digest(packet),'validation_projection_digest':digest(view),
        'initial_adjustment_row_sha256':digest(anchors[0]),'separated_anchor_row':deepcopy(anchors[0]),
        'prelisting_missing_sessions':[s for s in sessions if s<listed],
        'postlisting_observed_sessions':len(expected),'account_uses_original_bars':True,
        'entitlement_inferred':False,'zero_distribution_certified':False,'synthetic_prices_created':0}
    return view,receipt
