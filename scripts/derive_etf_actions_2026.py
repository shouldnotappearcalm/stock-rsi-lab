"""Post-freeze offline interim2026 actions from already retained original bytes.

Only 2026-01-01..2026-10-20 action rows; no price/ROI/network. Original parser,
source artifacts and old per10 derivation remain immutable.
"""
import argparse,hashlib,json,re
import bs4
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from bs4 import BeautifulSoup
from scripts.capture_etf_action_sources import table_grid
from scripts.fundamental_query_journal import file_sha,write_packet_once
START='2026-01-01';END='2026-10-20'

def extract_actions(raw,code):
    if code not in ('SH510300','SH510500','SZ159915'):raise ValueError('unregistered ETF')
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    soup=BeautifulSoup(text,'html.parser')
    if soup.title is None or code[2:] not in soup.title.get_text():raise ValueError('fund identity missing from page title')
    divheader=['年份','权益登记日','除息日','每份分红','分红发放日'];splitheader=['年份','拆分折算日','拆分类型','拆分折算比例']
    grids=[table_grid(t) for t in soup.find_all('table')];selected={}
    for kind,header in [('dividends',divheader),('share_changes',splitheader)]:
        matches=[g for g in grids if g and g[0]==header]
        if len(matches)!=1:raise ValueError('unique source '+kind+' table missing')
        selected[kind]=matches[0][1:]
        if not selected[kind]:raise ValueError('empty source action table has unknown history')
    result={'instrument':code,'window':[START,END],'dividends':[],'share_changes':[],
      'provider_asserts_no_dividends':False,'provider_asserts_no_share_changes':False,'outside_window_rows_excluded':0,
      'primary_event_truth_certified':False,'historical_arrival_certified':False,'tax_treatment_certified':False,
      'auxiliary_page_data_excluded_from_decisions':True}
    for kind,rows in selected.items():
        marker='暂无分红信息' if kind=='dividends' else '暂无拆分信息'
        if len(rows)==1 and any(marker in cell for cell in rows[0]):
            result['provider_asserts_no_'+kind]=True;continue
        for row in rows:
            if len(row)!=(5 if kind=='dividends' else 4):raise ValueError('source action row layout changed')
            at=row[2] if kind=='dividends' else row[1]
            date.fromisoformat(at)
            if not START<=at<=END:result['outside_window_rows_excluded']+=1;continue
            if kind=='dividends':
                recorded,pay=row[1],row[4];date.fromisoformat(recorded);date.fromisoformat(pay)
                match=re.fullmatch(r'每份派现金([0-9]+(?:\.[0-9]+)?)元',row[3])
                if not match or not recorded<=at<=pay or D(match[1])<=0:raise ValueError('cash distribution unit or timing unknown')
                result[kind].append({'recorded':recorded,'ex_date':at,'pay_date':pay,'cash_per_unit':match[1]})
            else:result[kind].append({'day':at,'kind_provider_raw':row[2],'ratio_provider_raw':row[3]})
        result[kind].sort(key=lambda r:r['ex_date'] if kind=='dividends' else r['day'])
        ids=[r['ex_date'] if kind=='dividends' else r['day'] for r in result[kind]]
        if len(ids)!=len(set(ids)):raise ValueError('ambiguous duplicate event date')
    return result



def extract_typed_cashflows(raw,code):
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    soup=BeautifulSoup(text,'html.parser');matches=[]
    for table in soup.find_all('table'):
        grid=table_grid(table)
        if grid and grid[0] in (['年份','权益登记日','除息日','每份分红','分红发放日'],
                                ['年份','权益登记日','除息日','每10份分红','分红发放日']):matches.append((table,grid))
    if len(matches)!=1:raise ValueError('unique source cash-unit table required')
    table,grid=matches[0];denominator=10 if grid[0][3]=='每10份分红' else 1;original={}
    trs=[tr for tr in table.find_all('tr') if tr.find_parent('table') is table]
    if len(trs)!=len(grid):raise ValueError('ambiguous HTML row/grid alignment')
    if denominator==10:
        header=trs[0].find_all(['th','td'],recursive=False)
        if len(header)!=5:raise ValueError('cash unit header layout changed')
        header[3].clear();header[3].append('每份分红')
    for tr,row in zip(trs[1:],grid[1:]):
        if any('暂无分红信息' in cell for cell in row):continue
        if len(row)!=5:raise ValueError('cash unit row layout changed')
        at=row[2];date.fromisoformat(at)
        if not START<=at<=END:continue
        expected='每10份派现金' if denominator==10 else '每份派现金'
        match=re.fullmatch(expected+r'([0-9]+(?:\.[0-9]+)?)元',row[3])
        if not match:raise ValueError('row cash unit disagrees with explicit header')
        if at in original:raise ValueError('ambiguous duplicate cash event')
        original[at]=row[3]
        if denominator==10:
            cells=[c for c in tr.find_all(['td','th'],recursive=False) if re.sub(r'\s+','',c.get_text())==row[3]]
            if len(cells)!=1:raise ValueError('cash unit source cell ambiguous')
            normalized=D(match[1])/10;cells[0].clear();cells[0].append('每份派现金'+str(normalized)+'元')
    result=extract_actions(str(soup).encode('utf-8'),code)
    if set(original)!={r['ex_date'] for r in result['dividends']}:raise ValueError('cash unit derivation changed events')
    for row in result['dividends']:
        row.update(cash_provider_raw=original[row['ex_date']],cash_provider_denominator=denominator)
    result.update(derivation_version='EXPLICIT_2026_ONE_OR_TEN_UNITS_V3',original_html_sha256=hashlib.sha256(raw).hexdigest(),
        original_source_header=grid[0][3],source_bytes_modified=False,network_queries=0)
    return result



def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','capture-manifest-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);base=Path(a.source_root);source=base/'etf-actions-rules-sources-20261021';out=Path(a.output_dir)
    if out.exists():raise ValueError('offline derivation output already exists')
    if file_sha(source/'manifest.json')!=a.capture_manifest_sha256:raise ValueError('original capture identity changed')
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest['request_sha256']!='7a472a861ae24361e875d462ea00eff09574c471bc3b9c5afa66d836427e7273':raise ValueError('unexpected original source scope')
    for n,h in manifest['artifact_sha256'].items():
        if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(source/n)!=h:raise ValueError('original source bytes changed')
    rows={}
    for code in ('SH510300','SH510500','SZ159915'):
        doc=manifest['documents'][code]
        if file_sha(source/doc['file'])!=doc['sha256']:raise ValueError('original fund page changed')
        rows[code]=extract_typed_cashflows((source/doc['file']).read_bytes(),code)
    out.mkdir(parents=True)
    for code,row in rows.items():write_packet_once(out/(code+'.json'),row)
    result={'status':'THREE_ETF_2026_ACTION_TABLES_DERIVED_OFFLINE_PRIMARY_REVIEW_PENDING','original_capture_manifest_sha256':a.capture_manifest_sha256,
        'derivation_method_sha256':file_sha(__file__),'imported_parser_sha256':file_sha(Path(__file__).with_name('capture_etf_action_sources.py')),'bs4_version':bs4.__version__,'funds':rows,'network_queries':0,'original_source_bytes_modified':False,'selected_2026_window':[START,END],'investment_rule_frozen_before_access':True,
        'primary_event_truth_certified':False,'source_admitted_for_account_replay':False,'portfolio_returns_computed':False,'candidate_promoted':False,'objective_achieved':False}
    write_packet_once(out/'summary.json',result)
    print('Offline fund tables',len(rows),'; in-window cash events',sum(len(r['dividends']) for r in rows.values()),'; share changes',sum(len(r['share_changes']) for r in rows.values()),'; no network or ROI',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
