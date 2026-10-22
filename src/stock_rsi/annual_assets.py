"""Consolidated balance-only source editions; no stock ranks or investment rule."""
import copy
from datetime import date, datetime, time, timezone
import re
from zoneinfo import ZoneInfo

from stock_rsi import annual_profitability_v7 as grammar
from stock_rsi.annual_profitability import amount_CNY, aware, compact, OBSERVED, RECONSTRUCTED
from stock_rsi.data import digest

CONTRACT='CONSOLIDATED_ANNUAL_TOTAL_ASSETS_EDITION_V1'
CAS19_REFERENCE=grammar.CAS19_REFERENCE


def need(ok,why):
    if not ok:raise ValueError(why)


def reject_balance_currency_conflicts(lines):
    starts=[i for i,(_,text) in enumerate(lines) if grammar.forms.v2.title(text)=='合并资产负债表']
    ends=[i for i,(_,text) in enumerate(lines) if grammar.forms.v2.title(text)=='母公司资产负债表']
    need(len(starts)==len(ends)==1 and starts[0]<ends[0],'unique ordered consolidated/parent balance tables')
    for _,text in lines[starts[0]:min(ends[0],starts[0]+12)]:
        plain=compact(text).replace('：',':')
        if '币种:' in plain:
            need(plain.split('币种:',1)[1].split('单位:',1)[0]=='人民币','conflicting balance currency')
        need(not re.search(r'单位[：:](?:美元|港币|欧元|日元|USD|HKD|EUR|JPY)',compact(text),re.I),
             'explicit non-CNY balance unit unsupported')


def parse_balance_only(pages,report_year,*,normative_basis=None):
    need(type(report_year) is int and 1900<=report_year<=9998,'explicit annual report year')
    need(type(pages) in (list,tuple) and pages and all(type(p) is str for p in pages),'ordered original physical page text')
    # Preserve the existing full-report primary-section boundaries. Income title
    # boundaries may establish that section; income numeric fields are not read.
    lines,context=grammar.forms.prior.financial_context(pages)
    reject_balance_currency_conflicts(lines)
    currency=grammar.forms.reporting_currency(pages)
    selected,metadata=grammar.table(lines,context,currency,pages,normative_basis,
        '合并资产负债表','母公司资产负债表',report_year,False)
    metadata['parser_contract']=CONTRACT
    years=(report_year,report_year-1) if metadata['reported_comparative_balance_date']==f'{report_year-1}-12-31' else (report_year,)
    return grammar.extract_row(selected,metadata,r'^资产总计\s*','total_assets',report_year,years)


def make_report(instrument,report_year,publication_day,observed_at,document_sha256,announcement_id,balances):
    need(type(instrument) is str and re.fullmatch(r'(SH|SZ)[0-9]{6}',instrument),'canonical source instrument')
    need(type(report_year) is int and 1900<=report_year<=9998,'explicit source report year')
    publication=date.fromisoformat(publication_day);observed=aware(observed_at)
    need(publication.isoformat()==publication_day and publication>date(report_year,12,31)
         and observed.astimezone(ZoneInfo('Asia/Shanghai')).date()>=publication,'annual disclosure/arrival chronology')
    need(type(document_sha256) is str and re.fullmatch('[a-f0-9]{64}',document_sha256)
         and type(announcement_id) is str and re.fullmatch('[0-9]+',announcement_id),'original PDF and announcement identity')
    current=f'{report_year}-12-31';previous=f'{report_year-1}-12-31'
    need(type(balances) is dict and current in balances and set(balances)<={current,previous},'current balance required; only explicit adjacent annual columns')
    for period,cell in balances.items():
        need(cell['fiscal_end']==period and cell['column_index']==report_year-date.fromisoformat(period).year
             and cell['statement']=='合并资产负债表' and cell['row_text_sha256']==digest(cell['row_text']),
             'coherent consolidated literal balance cell')
        amount=amount_CNY(cell['literal'],cell['unit'])
        need(amount>0 and format(amount,'f')==cell['value_CNY'],'positive normalized asset amount matches literal/unit')
        header=compact(cell['header_line'])
        if period==previous:
            comparison=cell.get('reported_comparative_balance_date')
            if 'reported_comparative_balance_date' in cell:need(comparison==previous,'prior balance needs explicit priorDecember31')
            else:need(f'{report_year}年12月31日{report_year-1}年12月31日' in header,'audited legacy prior header must literally name both year ends')
        if cell.get('current_column_date_is_inferred_from_explicit_statement_date'):
            anchor=cell['balance_current_date_anchor']
            need(period==current and anchor['date']==current and compact(anchor['literal'])==f'{report_year}年12月31日'
                 and cell['comparative_date_is_unresolved'] is True,'generic current anchor; no invented prior date')
        else:need(f'{report_year}年12月31日' in header,'literal current calendar date in original balance header')
    public_end=datetime.combine(publication,time.max,ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)
    record={'contract':CONTRACT,'instrument':instrument,'report_year':report_year,
        'publication_day':publication_day,'public_day_end_at':public_end.isoformat(),'observed_at':observed.isoformat(),
        'payload':{'scope':'CONSOLIDATED','document_sha256':document_sha256,'announcement_id':announcement_id,
                   'balances':copy.deepcopy(balances)},'financial_version_history_complete':False,
        'historical_arrival_verified':False,'financial_reporting_compatibility_verified':False,'investment_factor_admitted':False}
    record['record_id']=digest(record);return record


def visible_reports(reports,as_of,*,mode=OBSERVED):
    """All visible supported editions,never a latest-report eligibility selector.

    Latest unsupported editions must still be consulted in the full case
    inventory before any investment decision; this source view cannot replace it.
    """
    need(mode in (OBSERVED,RECONSTRUCTED),'explicit source availability mode')
    clock=aware(as_of);visible=[]
    for report in reports:
        public,observed=aware(report['public_day_end_at']),aware(report['observed_at'])
        if clock<(max(public,observed) if mode==OBSERVED else public):continue
        need(report['contract']==CONTRACT and report['record_id']==digest({k:v for k,v in report.items() if k!='record_id'}),
             'visible asset report identity changed')
        visible.append(copy.deepcopy(report))
    return {'as_of':clock.isoformat(),'visibility_mode':mode,'reports':visible,
        'all_visible_supported_editions_not_latest_eligibility':True,'historical_arrival_verified':False,
        'financial_version_history_complete':False,'investment_factor_admitted':False}
