"""Separate stdlib reconstruction of fixed12 raw CNINFO metadata; no price/PDF/ROI."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re


def need(v, message):
    if not v:
        raise AssertionError(message)


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def independently_select(code, data):
    need(type(data['totalAnnouncement']) is int and 0 <= data['totalAnnouncement'] <= 30
         and data.get('hasMore') in (False, None), 'one complete raw metadata page')
    raw = data.get('announcements') or []
    need(len(raw) == data['totalAnnouncement'], 'metadata count conservation')
    normalized, selected, seen = [], [], set()
    suffixes = {'', '全文', '（全文）', '(全文)', '（修订）', '（修订版）', '(修订)', '(修订版)',
                '（修订稿）', '(修订稿)', '（更正后）', '(更正后)', '（更新后）', '(更新后)', '（中文版）', '(中文版)'}
    for row in raw:
        need(row['secCode'] == code[2:] and type(row['announcementTime']) is int, 'raw issuer/date identity')
        day = datetime.fromtimestamp(row['announcementTime']/1000, timezone(timedelta(hours=8))).date().isoformat()
        need('2023-01-01' <= day <= '2023-12-31', 'raw announcement outside2023')
        identity, title, path = str(row['announcementId']), row['announcementTitle'], row.get('adjunctUrl')
        need(identity.isdigit() and identity not in seen and type(title) is str, 'unique raw announcement')
        seen.add(identity)
        kind = 'OTHER_ANNUAL_CATEGORY_NOTICE'
        if '摘要' in title: kind = 'SUMMARY'
        elif '英文' in title: kind = 'ENGLISH_EDITION'
        elif '可视' in title: kind = 'VISUAL_EDITION'
        else:
            text = ''.join(title.split())
            matches = list(re.finditer(r'2022年?年度报告', text))
            if matches and text[matches[-1].end():] in suffixes:
                kind = 'FULL_2022_ANNUAL_REPORT'
                need(type(path) is str and re.fullmatch(r'finalpage/\d{4}-\d{2}-\d{2}/'+re.escape(identity)+r'\.[pP][dD][fF]',path), 'original safe PDF identity')
        r = {'instrument': code, 'fiscal_year': 2022 if kind == 'FULL_2022_ANNUAL_REPORT' else None,
             'title': title, 'day': day, 'timestamp_ms': row['announcementTime'],
             'announcement_id': identity, 'pdf_path': path, 'classification': kind}
        normalized.append(r)
        if kind == 'FULL_2022_ANNUAL_REPORT': selected.append(r)
    need(1 <= len(selected) <= 2, 'no arbitrary edition selection')
    return normalized, selected


def main():
    parser=argparse.ArgumentParser()
    for name in ('repo-root','source-root','request','expected-request-sha256','run-dir','output'):
        parser.add_argument('--'+name,required=True)
    a=parser.parse_args();root,base,run,out=map(lambda p:Path(p).resolve(),(a.repo_root,a.source_root,a.run_dir,a.output));reqpath=Path(a.request).resolve()
    need(not out.exists() and not out.is_relative_to(root) and not out.is_relative_to(base),'new external report only')
    need(sha(reqpath)==a.expected_request_sha256,'frozen request identity');req=read(reqpath)
    need(req['status']=='FROZEN_BEFORE_FIXED12_INITIAL2022_ANNUAL_METADATA_CAPTURE'
         and len(req['codes'])==len(set(req['codes']))==12 and req['max_logical_attempts']==12
         and req['per_resource_attempts']==1 and req['page_cap']==1 and req['PDF_download_permitted'] is False
         and req['ranking_or_portfolio_returns_permitted'] is False,'frozen source-only attempt scope')
    expected={**req['input_sha256'],'frozen_source_request':a.expected_request_sha256}
    paths={k:(root if k.startswith('repo/') else base)/k.split('/',1)[1] for k in req['input_sha256']};paths['frozen_source_request']=reqpath
    need(len(paths)==23,'complete23 inputs')
    for k,p in paths.items():need(sha(p)==expected[k],'actual input hash')
    original_outputs={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()}
    need(len(original_outputs)==65,'exact65 complete metadata capture outputs')
    cases=read(run/'case_results.json');summary=read(run/'summary.json');selected_by_code={};allids=[]
    for code in req['codes']:
        identity=req['resources'][code];key=digest({'resource':code,'identity':identity});folder=run/'http'/key
        need({p.name for p in folder.iterdir()}=={'request.json','reservation.json','body.bin','response.json'},'exact four HTTP artifacts')
        need(read(folder/'request.json')=={'resource':code,**identity},'original HTTP request')
        reservation=read(folder/'reservation.json');need(reservation['resource']==code and reservation['attempt']==1 and reservation['maximum_logical_attempts']==1 and reservation['identity_sha256']==digest(identity),'one immutable reservation')
        response=read(folder/'response.json');need(response['resource']==code and response['identity_sha256']==digest(identity)
            and response['status']=='RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED' and response['http_status']==200
            and response['body_complete'] is True and response['request_sha256']==sha(folder/'request.json')
            and response['reservation_sha256']==sha(folder/'reservation.json') and response['body_sha256']==sha(folder/'body.bin')
            and response['body_bytes']==(folder/'body.bin').stat().st_size,'raw HTTP identity/body/budget chain')
        normalized,selected=independently_select(code,read(folder/'body.bin'))
        receipt={'folder':'http/'+key,'record':response,'response_sha256':sha(folder/'response.json')}
        stated={'status':'INITIAL2022_FULL_REPORT_METADATA_CAPTURED','receipt':receipt,'all_normalized_rows':normalized,'selected_full_reports':selected}
        need(read(run/(code+'.json'))==stated==cases[code]==summary['results_by_code'][code],'all literal metadata classifications independently reconstructed')
        selected_by_code[code]=selected;allids.extend(r['announcement_id'] for r in selected)
    need(len(allids)==len(set(allids)),'unique selected document identities')
    need(summary['status']=='INITIAL2022_METADATA_CAPTURE_COMPLETE' and summary['successful_issuers']==12
        and summary['rejected_issuers']==0 and summary['logical_attempts']==12 and summary['input_count']==23
        and summary['request_sha256']==a.expected_request_sha256 and summary['all_inputs_unchanged'] is True
        and summary['PDFs_downloaded']==0 and summary['investment_factor_admitted'] is False
        and summary['portfolio_returns_computed'] is False and summary['objective_achieved'] is False,'complete metadata-only summary')
    need(read(run/'input-before.json')==expected,'input-before exact binding')
    post={'all_inputs_unchanged':True,'count':23,'mismatches':[],'source_request_rehashed_after_processing':True}
    need(read(run/'input-postcheck.json')==post,'source postcheck')
    terminal=read(run/'terminal.json');need(terminal['logical_attempts']==12 and terminal['completed_issuers']==12 and terminal['pending']==[]
        and terminal['original_error'] is None and terminal['postcheck']==post and terminal['persistence_errors']==[],'successful terminal')
    for k,p in paths.items():need(sha(p)==expected[k],'actual input after reconstruction')
    need(original_outputs=={str(p.relative_to(run)):sha(p) for p in sorted(run.rglob('*')) if p.is_file()},'all output bytes unchanged during audit')
    report={'status':'PASS_SEPARATE_FIXED12_INITIAL2022_METADATA_AUDIT','audit_code_sha256':sha(__file__),
        'request_sha256':a.expected_request_sha256,'summary_sha256':sha(run/'summary.json'),'all23_input_sha256':expected,
        'all65_output_sha256':original_outputs,'all12_issuer_classifications_reconstructed':True,'selected_full_reports_by_code':selected_by_code,
        'selected_full_report_count':len(allids),'logical_HTTP_attempts':12,'raw_HTTP_bodies':12,'production_modules_imported':False,
        'blinded_audit_claimed':False,'PDF_downloaded_or_financial_values_decoded':False,'new_2026_market_or_financial_values_decoded':False,
        'historical_arrival_verified':False,'financial_version_history_complete':False,'investment_factor_admitted':False,
        'security_ranking_or_portfolio_returns_computed':False,'objective_achieved':False}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(report['status'],sha(out),len(allids))
if __name__=='__main__':main()
