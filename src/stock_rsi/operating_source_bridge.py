"""Separate same-edition operating source record; no ratio or strategy decision."""
import copy
from datetime import date,datetime,time,timezone
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_operating as op
from stock_rsi import asset_geometry as geometry
from stock_rsi.data import digest

CONTRACT='CN_OPERATING_INCOME_AND_SUMMARY_PRIOR_ASSETS_SOURCE_V1'
SUPPORTED='SUMMARY_SOURCE_RECOVERED_NOT_INVESTMENT_ADMITTED'
STILL_UNSUPPORTED='STILL_UNSUPPORTED'
LEGACY_SUPPORTED='UNCHANGED_LEGACY_OPERATING_SOURCE_SUPPORTED'


def recover_source_record(document,text_pages,geometry_pages,primary_cell,*,normative_basis):
    year=document['effective_fiscal_year'];public=date.fromisoformat(document['day']);observed=op.aware(document['captured_at_utc'])
    op.need(re.fullmatch(r'(SH|SZ)[0-9]{6}',document['instrument']) and re.fullmatch(r'[0-9]+',document['announcement_id'])
            and document['day']==public.isoformat() and observed.astimezone(ZoneInfo('Asia/Shanghai')).date()>=public,'coherent original annual source identity and clocks')
    assets=geometry.parse_summary_assets(geometry_pages,year,document['day'],document['source_sha256'],
        {'source_sha256':document['source_sha256'],'report_year':year,'cell':primary_cell},normative_basis=normative_basis)
    op.need(type(text_pages) in (list,tuple) and text_pages and all(type(p) is str for p in text_pages),
            'authenticated physical page text required')
    source_words=[assets['row_label_word'],*assets['primary_row_words']]
    for columns in assets['columns_by_year'].values():
        for cell in columns:
            source_words.extend(w for w in (cell['amount_word'],cell['year_word'],cell['adjustment_word']) if w is not None)
    op.need(all(1<=w['page']<=len(text_pages) and op.compact(w['text']) in op.compact(text_pages[w['page']-1]) for w in source_words),
            'original geometry words must match authenticated cached physical pages')
    grammar=op.grammar;lines,context=grammar.forms.prior.financial_context(text_pages)
    grammar.prior.reject_local_currency_conflicts(lines);currency=grammar.forms.reporting_currency(text_pages)
    income,metadata=grammar.table(lines,context,currency,text_pages,op.CAS19_REFERENCE,'合并利润表','母公司利润表',year,True)
    metadata['parser_contract']=op.CONTRACT
    by_field={field:op.extract_signed_row(income,metadata,label,field,year) for field,label in op.LABELS.items()}
    parsed={f'{y}-12-31':{field:by_field[field][f'{y}-12-31'] for field in op.FIELDS} for y in (year,year-1)}
    for period,fields in parsed.items():
        for field,cell in fields.items():
            op.validate_unit_evidence(cell,year)
            op.need(cell['statement']=='合并利润表' and cell['fiscal_end']==period
                and cell['column_index']==year-int(period[:4]) and cell['value_CNY']==format(op.amount_CNY(cell['literal'],cell['unit']),'f'),
                'same-edition signed income cell and unit')
    result={'contract':CONTRACT,'instrument':document['instrument'],'report_year':year,'publication_day':document['day'],
        'public_day_end_at':datetime.combine(public,time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).isoformat(),
        'observed_at':observed.isoformat(),'payload':{'document_sha256':document['source_sha256'],'announcement_id':document['announcement_id'],
          'income':parsed,'asset_bridge':assets,'income_origin':'CONSOLIDATED_INCOME_STATEMENT','asset_origin':'MAIN_ACCOUNTING_DATA_SUMMARY_YEAR_END'},
        'historical_arrival_verified':False,'financial_cross_issuer_comparability_verified':False,'investment_factor_admitted':False}
    result['record_id']=digest(result);return result


def augment_coverage(view,case_reader):
    result=copy.deepcopy(view)
    for row in result['classifications']:
        key=row.get('selected_capture_key')
        if key is None:
            row['effective_source_status']=row['annual_status'];continue
        case=case_reader(key)
        op.need(case['capture_key']==key and case['instrument']==row['instrument']
                and case['source_sha256']==row['selected_source_sha256'],'same original visible filing selection')
        status=case['effective_source_status'];record_id=case['effective_record_id']
        op.need(status in (SUPPORTED,STILL_UNSUPPORTED,LEGACY_SUPPORTED)
                and ((record_id is None) if status==STILL_UNSUPPORTED else type(record_id) is str and re.fullmatch('[a-f0-9]{64}',record_id)),
                'explicit supported/failed source pointer')
        row.update(effective_source_status=status,effective_record_id=record_id)
    result.update(source_only_no_monetary_values_exposed=True,investment_factor_admitted=False,
        historical_arrival_verified=False,operating_ratios_or_portfolio_returns_computed=False)
    return result
