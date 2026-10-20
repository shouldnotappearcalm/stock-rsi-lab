"""Evaluator-only lifecycle checks. Missing prices are never synthesized.

The caller authenticates primary documents and includes every owned/pending
share, pending order and decision price dependency in required. Boundary
evidence and skipped-source audit records must not enter agent snapshots.
"""
from datetime import date
import re


def source_rows_on(bars,day,required,lifecycles):
    required=set(required)
    if type(day) is not date or not required<=set(bars):
        raise ValueError('explicit session date and complete required security universe needed')
    boundaries={}
    for code,proof in lifecycles.items():
        if (code not in bars or proof['kind'] not in ('LISTING_BEGIN','DELISTING_END')
                or proof['verified_primary_boundary'] is not True
                or not re.fullmatch('[0-9a-f]{64}',proof['primary_document_sha256'])):
            raise ValueError('authenticated primary lifecycle boundary required')
        parsed=date.fromisoformat(proof['effective_date'])
        if parsed.isoformat()!=proof['effective_date']:raise ValueError('canonical lifecycle date required')
        boundaries[code]=(proof['kind'],parsed)
    rows={};exceptions=[];label=day.isoformat()
    for code,by_day in sorted(bars.items()):
        row=by_day.get(label);boundary=boundaries.get(code);reason=None
        if row is not None and row['date']!=label:raise ValueError('source session identity changed')
        if boundary is not None:
            kind,effective=boundary
            if kind=='LISTING_BEGIN' and day<effective:
                if row is not None:raise ValueError('unexpected source bar before primary listing boundary')
                reason='BEFORE_PRIMARY_LISTING_BOUNDARY'
            elif kind=='DELISTING_END' and day>=effective:
                reason='AT_OR_AFTER_PRIMARY_DELISTING_BOUNDARY'
        if reason:
            if code in required:raise ValueError('lifecycle interval still requires shares, orders or price: '+code+' '+label)
            exceptions.append({'instrument':code,'session':label,'reason':reason,'original_row_present':row is not None,
                'primary_document_sha256':lifecycles[code]['primary_document_sha256'],'synthetic_price_created':False})
        elif row is None:raise ValueError('unexplained raw source gap: '+code+' '+label)
        else:rows[code]=row
    return rows,exceptions
