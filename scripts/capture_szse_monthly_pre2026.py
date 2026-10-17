"""Capture24 original exchange tables, independent of investment returns."""
import argparse
import base64
import fcntl
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen

from scripts.fundamental_query_journal import QueryJournal,write_packet_once
from scripts.capture_cninfo_csi500_reports_pre2026 import atomic_json,sha256_file
from stock_rsi.szse_monthly import decode_source,discover_transaction_url,month_shift,parse_transactions,url_build_day

MONTHS=tuple(month_shift('2023-11',i) for i in range(24))
METHOD_FILES=('scripts/capture_szse_monthly_pre2026.py','scripts/fundamental_query_journal.py',
    'scripts/capture_cninfo_csi500_reports_pre2026.py','src/stock_rsi/szse_monthly.py')


def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.szse.cn/'}),timeout=20) as response:
        data=response.read(10*1024*1024+1)
    if len(data)>10*1024*1024:raise ValueError('registered original HTML size bound exceeded')
    return ['base64_original_bytes'],[[base64.b64encode(data).decode('ascii')]]


def source_query(journal,url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('www.szse.cn','docs.static.szse.cn') or parsed.username or parsed.password:
        raise ValueError('registered public exchange host required')
    if not '2023-01-01'<=url_build_day(url)<='2025-12-31':raise ValueError('source URL exceeds pre2026 cap')
    value,receipt=journal.query({'public_get':url},lambda:fetch(url))
    if value['fields']!=['base64_original_bytes'] or len(value['rows'])!=1:raise ValueError('source journal schema changed')
    return base64.b64decode(value['rows'][0][0],validate=True),receipt


def raw_once(path,data):
    if path.exists():
        if path.read_bytes()!=data:raise ValueError('original HTML would be overwritten')
    else:
        with path.open('xb') as stream:stream.write(data)


def main(argv=None):
    parser=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','index-file','output-dir'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--resume',action='store_true');args=parser.parse_args(argv)
    req=json.loads(Path(args.request).read_text());root=Path(__file__).resolve().parents[1];out=Path(args.output_dir)
    if (sha256_file(args.request)!=args.expected_request_sha256 or sha256_file(args.index_file)!=req['discovery_index_sha256']
            or list(req['months'])!=list(MONTHS) or req['max_query_attempt_reservations']!=96
            or req['per_query_max_attempts']!=2 or set(req['method_sha256'])!=set(METHOD_FILES)
            or any(sha256_file(root/n)!=h for n,h in req['method_sha256'].items())):
        raise ValueError('registered exchange capture boundary or method changed')
    if args.resume:
        if (out/'request.json').read_bytes()!=Path(args.request).read_bytes():raise ValueError('resume identity changed')
    else:
        if out.exists():raise ValueError('capture output already exists')
        (out/'original').mkdir(parents=True);(out/'months').mkdir();(out/'request.json').write_bytes(Path(args.request).read_bytes())
    with (out/'capture.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        journal=QueryJournal(out,max_queries=96,max_attempts=2);months={}
        for month in MONTHS:
            parent=req['months'][month]['article_url'];raw,article_receipt=source_query(journal,parent)
            html,_=decode_source(raw)
            import re
            title=re.sub(r'<[^>]+>',' ',html)
            if not re.search(str(int(month[:4]))+r'年\s*0?'+str(int(month[5:]))+r'月\s*深圳证券交易所市场统计月报',title):
                raise ValueError('source parent title differs from requested month')
            article_file=f'original/{month}-article.html';raw_once(out/article_file,raw)
            table_url=discover_transaction_url(html,parent);table,table_receipt=source_query(journal,table_url)
            table_file=f'original/{month}-transactions.html';raw_once(out/table_file,table)
            parsed=parse_transactions(table,month)
            packet={**parsed,'article_build_day':url_build_day(parent),'table_build_day':url_build_day(table_url)}
            normalized_file=f'months/{month}.json';write_packet_once(out/normalized_file,packet)
            months[month]={'article_url':parent,'table_url':table_url,'article_file':article_file,
                'article_sha256':sha256_file(out/article_file),'table_file':table_file,'table_sha256':sha256_file(out/table_file),
                'normalized_file':normalized_file,'normalized_sha256':sha256_file(out/normalized_file),
                'mainboard_rows':len(parsed['stocks']),'all_security_rows':parsed['all_security_rows'],
                'query_receipts':[article_receipt,table_receipt]}
            print('SZSE monthly captured '+month+' '+str(len(months))+'/24',flush=True)
        manifest={'status':'PRE2026_SZSE_MONTHLY_ORIGINAL_TABLES_CAPTURED','request_sha256':args.expected_request_sha256,
            'source_reader_sha256':sha256_file(root/'src/stock_rsi/szse_monthly.py'),'months':months,
            'journal_artifact_sha256':{str(p.relative_to(out)):sha256_file(p) for p in sorted((out/'queries').rglob('*.json'))},
            'query_attempt_reservations':len(list(out.rglob('reserved-*.json'))),'historical_arrival_verified':False,
            'filename_date_is_measured_publication':False,'2026_market_values_queried':False,'strategy_returns_computed':False,
            'claim_status':'ORIGINAL_MONTHLY_TABLES_WITH_DECLARED_AVAILABILITY_CONVENTION_NOT_VERIFIED_PIT',
            'objective_achieved':False}
        atomic_json(out/'manifest.json',manifest)
    return 0


if __name__=='__main__':raise SystemExit(main())
