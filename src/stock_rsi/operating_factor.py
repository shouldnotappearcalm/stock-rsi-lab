"""Visibility-first approved operating sources; exact current-period ratios only."""
from fractions import Fraction
import re

from stock_rsi import annual_operating as op, operating_source_bridge as bridge
from stock_rsi.data import digest
from stock_rsi.profitability_availability import public_end


def unproved(value):
    for key in ('historical_arrival_verified','financial_cross_issuer_comparability_verified','investment_factor_admitted'):
        op.need(value.get(key,False) is False,'source support does not establish historical or investment assurances')


def money(cell):
    value=op.amount_CNY(cell['literal'],cell['unit'])
    op.need(value.is_finite() and cell['value_CNY']==format(value,'f'),'source literal/unit normalization')
    return Fraction(value)


def decimal_text(value):
    # CNY source arithmetic has terminating decimals; retain two monetary decimals.
    from decimal import Decimal,localcontext
    with localcontext() as context:
        context.prec=60;return format(Decimal(value.numerator)/Decimal(value.denominator),'.2f')


def source_observation(document,case_reader,legacy_reader,approved_ids,as_of,*,mode=op.OBSERVED):
    op.need(mode in (op.OBSERVED,op.RECONSTRUCTED),'explicit observed/reconstructed source mode')
    clock=op.aware(as_of);public=public_end(document);observed=op.aware(document['captured_at_utc'])
    op.need(public<=observed,'coherent publication/capture clocks')
    if clock<(max(public,observed) if mode==op.OBSERVED else public):return None
    key=document['capture_key'];year=document['effective_fiscal_year'];period=f'{year}-12-31';prior=f'{year-1}-12-31'
    op.need(type(year) is int and re.fullmatch(r'(SH|SZ)[0-9]{6}',document['instrument'])
        and re.fullmatch('[a-f0-9]{64}',document['source_sha256']),'visible original source identity')
    case=case_reader(key);unproved(case)
    op.need(case['capture_key']==key and case['instrument']==document['instrument'] and case['fiscal_year']==year
        and case['source_sha256']==document['source_sha256'] and case['effective_record_id']==approved_ids[key],
        'same proved original case and approved source ID')
    status=case['effective_source_status']
    if status==bridge.STILL_UNSUPPORTED:
        op.need(case['effective_record_id'] is None and case['source_record'] is None,'failed latest has no operating payload');return None
    if status==bridge.LEGACY_SUPPORTED:
        old=legacy_reader(key)
        op.need(case['source_record'] is None and case['asset_bridge'] is None and old['status']=='OPERATING_CELLS_SUPPORTED_PENDING_SOURCE_QA'
            and all(old[k]==case[k] for k in ('capture_key','instrument','fiscal_year','source_sha256')),'unchanged approved legacy source')
        record=old['operating_report'];payload=record['payload'];op.validate_parsed(payload['parsed'],year)
        rebuilt=op.make_report(record['instrument'],year,record['publication_day'],record['observed_at'],payload['document_sha256'],payload['announcement_id'],payload['parsed'])
        op.need(rebuilt==record,'complete unchanged legacy record')
        income=payload['parsed']['income'];asset=payload['parsed']['balances'][prior];denominator=money(asset);asset_id=None
    else:
        op.need(status==bridge.SUPPORTED,'known supported source status')
        record=case['source_record'];payload=record['payload'];asset=payload['asset_bridge']
        op.need(record['contract']==bridge.CONTRACT and type(asset) is dict and asset==case['asset_bridge']
            and asset['contract']=='CN_ANNUAL_SUMMARY_PRIOR_YEAR_END_ASSET_WORDS_V1'
            and asset['record_id']==digest({k:v for k,v in asset.items() if k!='record_id'}),'nonnull validated source asset bridge')
        unproved(asset)
        op.need(payload['income_origin']=='CONSOLIDATED_INCOME_STATEMENT' and payload['asset_origin']=='MAIN_ACCOUNTING_DATA_SUMMARY_YEAR_END'
            and asset['source_sha256']==document['source_sha256'] and asset['report_year']==year and asset['publication_day']==document['day']
            and asset['normative_basis']==bridge.geometry.basis() and '2021-06-28'<=document['day']<'2025-07-01'
            and asset['same_edition_primary_reconciliation'] is True,'same-edition original asset definition and regulatory version')
        groups=asset['columns_by_year'];current=asset['current'];previous=asset['prior']
        op.need(len(groups[str(year)])==1 and current==groups[str(year)][0] and previous==groups[str(year-1)][-1]
            and current['fiscal_end']==period and previous['fiscal_end']==prior,'correct explicit current/prior source asset dates')
        op.need(current['adjustment']=='AS_REPORTED' and previous['adjustment']==('AFTER_ADJUSTMENT' if len(groups[str(year-1)])==2 else 'AS_REPORTED'),
            'correct prior adjusted source column')
        unit=re.fullmatch(r'总资产[（(](元|万元)[）)]',op.compact(asset['row_label_word']['text']))
        op.need(unit is not None and all(c['unit']==unit.group(1) for c in (current,previous)),'literal summary asset row units')
        primary=asset['primary'];control=primary['cell'];values=op.row_values(control['row_text'],r'^资产总计\s*',control['header_line'])
        op.need(primary['source_sha256']==document['source_sha256'] and primary['report_year']==year
            and control['statement']=='合并资产负债表' and control['fiscal_end']==period and control['column_index']==0
            and control['row_text_sha256']==digest(control['row_text']) and control['literal']==values[0]
            and money(current)==money(control) and money(previous)==Fraction(op.amount_CNY(values[1],control['unit'])),
            'same-PDF primary current/opening asset reconciliation')
        denominator=money(previous);asset_id=asset['record_id'];income=payload['income']
        op.need(set(income)=={period,prior},'both annual income columns retained')
        for p,fields in income.items():
            op.need(set(fields)==set(op.FIELDS),'five explicit signed income source fields')
            for field,cell in fields.items():
                column=year-int(p[:4]);values=op.row_values(cell['row_text'],op.LABELS[field],cell['header_line'])
                op.need(cell['statement']=='合并利润表' and cell['fiscal_end']==p and cell['column_index']==column
                    and op.compact(cell['header_line']).endswith(f'{year}年度{year-1}年度') and cell['row_text_sha256']==digest(cell['row_text'])
                    and cell['literal']==values[column],'same consolidated income year/column/literal')
                op.validate_unit_evidence(cell,year);money(cell)
    unproved(record)
    op.need(record['record_id']==case['effective_record_id']==digest({k:v for k,v in record.items() if k!='record_id'})
        and record['instrument']==document['instrument'] and record['report_year']==year and record['publication_day']==document['day']
        and op.aware(record['public_day_end_at'])==public and op.aware(record['observed_at'])==observed
        and payload['document_sha256']==document['source_sha256'] and payload['announcement_id']==document['announcement_id'],
        'approved whole-record original source identity and exact clocks')
    op.need(denominator>0,'strictly positive same-edition prior assets')
    fields=income[period];amounts={f:money(fields[f]) for f in op.FIELDS}
    numerator=amounts['revenue']-amounts['cost_of_sales']-amounts['selling_expenses']-amounts['administrative_expenses']
    return {'instrument':document['instrument'],'capture_key':key,'record_id':record['record_id'],'source_sha256':document['source_sha256'],
        'asset_record_id':asset_id,'current_fiscal_end':period,'prior_asset_fiscal_end':prior,'publication_day':document['day'],
        'score_fraction':str(numerator/denominator),'operating_profit_CNY':decimal_text(numerator),'lagged_assets_CNY':decimal_text(denominator),
        'research_expenses_CNY':decimal_text(amounts['research_expenses']),'visibility_mode':mode,
        'historical_arrival_verified':False,'investment_factor_admitted':False}
