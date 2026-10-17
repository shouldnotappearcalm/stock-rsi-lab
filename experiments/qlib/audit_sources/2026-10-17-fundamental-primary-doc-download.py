"""Download the two preselected original annual reports; read-only sources."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

p = argparse.ArgumentParser(); p.add_argument('--request', required=True); p.add_argument('--output-dir', required=True)
a = p.parse_args(); request_file = Path(a.request); req = json.loads(request_file.read_text())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
assert sha('experiments/qlib/fundamental-value-pilot-pubdate-audit.json') == req['source_pubdate_matrix_sha256']
assert len(req['documents']) == 2 and {d['statDate'] for d in req['documents']} == {'2023-12-31', '2024-12-31'}
assert {d['instrument'] for d in req['documents']} == {'SH600166'}
out = Path(a.output_dir); assert not out.exists(); out.mkdir()
(out/'request.json').write_bytes(request_file.read_bytes()); docs = []
for doc in req['documents']:
    relative = doc['pdf_path']
    assert relative.startswith('finalpage/'+doc['day']+'/') and '..' not in relative and doc['day'] <= '2025-12-31'
    url = 'https://static.cninfo.com.cn/'+relative
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'}), timeout=30) as response:
        data = response.read(req['maximum_pdf_bytes_per_document']+1)
    assert data.startswith(b'%PDF') and len(data) <= req['maximum_pdf_bytes_per_document']
    filename = doc['instrument']+'-'+doc['statDate']+'-'+doc['announcement_id']+'.pdf'
    with (out/filename).open('xb') as stream: stream.write(data)
    docs.append({**doc, 'url': url, 'file': filename, 'sha256': sha(out/filename), 'bytes': len(data),
                 'captured_at_utc': datetime.now(timezone.utc).isoformat()})
    print('captured original annual report', doc['statDate'], len(data), flush=True)
manifest = {'status': 'ORIGINAL_ANNUAL_REPORTS_CAPTURED_NUMERIC_AUDIT_PENDING', 'request_sha256': sha(request_file),
            'capture_code_sha256': sha(__file__), 'documents': docs, 'financial_values_verified': False,
            'financial_version_history_complete': False, 'strategy_return_computed': False}
(out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
