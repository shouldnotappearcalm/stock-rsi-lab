"""One exact official-publisher PDF route after two retained CNINFO TLS errors."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
from scripts.fundamental_query_journal import QueryJournal,file_sha,write_packet_once

URL='https://www.cofco.com/uploads/soft/250811/56-250Q1162034.pdf'


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);root=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.output_dir);request=Path(a.request)
    if out.exists() or file_sha(request)!=a.expected_request_sha256:raise ValueError('fresh frozen publisher request required')
    r=json.loads(request.read_text())
    if r['status']!='FROZEN_ONE_EXACT_COFC0_PUBLISHER_PDF_ROUTE' or r['URL']!=URL or r['maximum_new_requests']!=1:
        raise ValueError('one exact publisher route required')
    for name,h in r['method_sha256'].items():
        if file_sha(root/name)!=h:raise ValueError('publisher method changed')
    for name,h in r['original_source_sha256'].items():
        if file_sha(base/name)!=h:raise ValueError('original terminal attempts changed')
    out.mkdir(parents=True);(out/'request.json').write_bytes(request.read_bytes())
    def fetch():
        response=subprocess.run(['curl','--proto','=https','--max-redirs','0','--max-time','25',
            '--connect-timeout','10','--max-filesize','10485760','--silent','--show-error',
            '--dump-header',str(out/'HTTP-headers.txt'),'--output',str(out/'HTTP-body.bin'),
            '--write-out','%{http_code}',URL],capture_output=True,timeout=30)
        data=(out/'HTTP-body.bin').read_bytes() if (out/'HTTP-body.bin').exists() else b''
        return ['publisher_http_response'],[{'URL':URL,'curl_returncode':response.returncode,
            'HTTP_status':response.stdout.decode(),'stderr':response.stderr.decode(errors='replace'),
            'body_base64':base64.b64encode(data).decode()}]
    error=None;receipt=None;complete=False
    try:
        payload,receipt=QueryJournal(out,max_queries=1,max_attempts=1).query(
            {'source':'COFCO_OFFICIAL_PUBLISHER_HTTP','url':URL,'request_sha256':a.expected_request_sha256},fetch)
        record=payload['rows'][0];data=base64.b64decode(record['body_base64'],validate=True)
        if record['curl_returncode']!=0 or record['HTTP_status']!='200' or not data.startswith(b'%PDF'):
            raise ValueError('publisher response incomplete,unsuccessful or notPDF')
        (out/'SH600737-publisher-original.pdf').write_bytes(data);complete=True
    except Exception as exc:error={'error_type':type(exc).__name__,'error':str(exc)}
    unchanged=all(file_sha(base/n)==h for n,h in r['original_source_sha256'].items())
    write_packet_once(out/'manifest.json',{'status':'COFCO_PUBLISHER_ORIGINAL_BYTES_REVIEW_SEPARATE',
        'request_sha256':a.expected_request_sha256,'URL':URL,'capture_complete':complete and unchanged,
        'original_inputs_unchanged':unchanged,'error':error,'HTTP_receipt':receipt,
        'file':'SH600737-publisher-original.pdf' if complete else None,
        'sha256':file_sha(out/'SH600737-publisher-original.pdf') if complete else None,
        'original_title_date_or_entitlements_verified':False,'new_2026_queries':False,
        'portfolio_return_computed':False,'objective_achieved':False})
    print('publisher capture',complete,'error',error,flush=True);return 0 if complete and unchanged else 2


if __name__=='__main__':raise SystemExit(main())
