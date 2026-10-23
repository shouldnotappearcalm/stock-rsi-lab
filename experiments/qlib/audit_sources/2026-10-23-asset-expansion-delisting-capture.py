"""Archive one discovered issuer original; no lifecycle/account admission."""
import argparse,base64,json,subprocess
from pathlib import Path
from scripts.fundamental_query_journal import QueryJournal,file_sha,write_packet_once

URL='https://static.cninfo.com.cn/finalpage/2026-03-26/1225030503.PDF'


def main():
    p=argparse.ArgumentParser()
    for n in ('request','expected-request-sha256','source-root','output-dir'):p.add_argument('--'+n,required=True)
    a=p.parse_args();repo=Path(__file__).resolve().parents[3];base=Path(a.source_root);out=Path(a.output_dir);request=Path(a.request)
    if out.exists() or file_sha(request)!=a.expected_request_sha256:raise ValueError('fresh exact source request required')
    r=json.loads(request.read_text())
    if (r['status']!='FROZEN_ONE_SH603056_DELISTING_ORIGINAL_CAPTURE' or r['URL']!=URL
            or r['maximum_new_requests']!=1 or out.resolve()!=(base/r['output_directory']).resolve()):
        raise ValueError('one exact issuer original only')
    bound={str(request.resolve()):a.expected_request_sha256}
    for field,root in (('method_sha256',repo),('public_evidence_sha256',repo),('original_source_sha256',base)):
        for name,h in r[field].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or file_sha(root/name)!=h:raise ValueError('bound original changed')
            bound[str(root/name)]=h
    out.mkdir();(out/'request.json').write_bytes(request.read_bytes());write_packet_once(out/'inputs-before.json',bound)
    def fetch():
        c=subprocess.run(['curl','--proto','=https','--max-redirs','0','--max-time','25','--connect-timeout','10',
            '--max-filesize','2097152','--silent','--show-error','--dump-header',str(out/'HTTP-headers.txt'),
            '--output',str(out/'HTTP-body.bin'),'--write-out','%{http_code}',URL],capture_output=True,timeout=30)
        data=(out/'HTTP-body.bin').read_bytes() if (out/'HTTP-body.bin').exists() else b''
        return ['original_http_response'],[{'url':URL,'curl_returncode':c.returncode,'http_status':c.stdout.decode(),
            'stderr':c.stderr.decode(errors='replace'),'body_base64':base64.b64encode(data).decode()}]
    complete=False;error=None;receipt=None;original=None
    try:
        payload,receipt=QueryJournal(out,max_queries=1,max_attempts=1).query(
            {'source':'CNINFO_ORIGINAL_HTTP','instrument':'SH603056','url':URL,'request_sha256':a.expected_request_sha256},fetch)
        v=payload['rows'][0];data=base64.b64decode(v['body_base64'],validate=True)
        if v['curl_returncode']!=0 or v['http_status']!='200' or not data.startswith(b'%PDF') or len(data)>2097152:
            raise ValueError('original PDF response unsuccessful/incomplete')
        (out/'SH603056-original.pdf').write_bytes(data);complete=True
    except BaseException as exc:error={'error_type':type(exc).__name__,'error':str(exc)};original=exc
    changed=[n for n,h in bound.items() if not Path(n).is_file() or file_sha(n)!=h]
    result={'status':'ONE_ISSUER_ORIGINAL_CAPTURED_REVIEW_SEPARATE','request_sha256':a.expected_request_sha256,'URL':URL,
        'capture_complete':complete and not changed,'error':error,'HTTP_receipt':receipt,'changed_inputs':changed,
        'consumed_input_files':len(bound),'PDF_sha256':file_sha(out/'SH603056-original.pdf') if complete else None,
        'lifecycle_boundary_or_account_admitted':False,'portfolio_returns_computed':False,'objective_achieved':False}
    write_packet_once(out/'manifest.json',result)
    if original is not None:raise original
    print('one original archived',result['capture_complete'],'bytes',len(data),'input changes',len(changed),flush=True)
    return 0 if result['capture_complete'] else 2


if __name__=='__main__':raise SystemExit(main())
