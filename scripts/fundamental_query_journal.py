"""Immutable per-query responses and conservative, restart-safe attempt budget.

Callers must serialize capture with the pilot's process lock. A reserved but
unanswered attempt remains consumed; restarting cannot erase or reuse it.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                    separators=(',', ':')).encode()).hexdigest()


def file_sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_packet_once(path, value):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text()) != value: raise ValueError('immutable source artifact differs: '+str(path))
        return
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


class QueryJournal:
    def __init__(self, root, *, max_queries, max_attempts=2):
        if max_queries < 1 or max_attempts < 1: raise ValueError('positive bounded attempt budget required')
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.max_queries, self.max_attempts = max_queries, max_attempts

    def query(self, identity, fetch):
        key = digest(identity); folder = self.root/'queries'/key; folder.mkdir(parents=True, exist_ok=True)
        request = folder/'request.json'; write_packet_once(request, identity)
        for n in range(1, self.max_attempts+1):
            reserved = folder/f'reserved-{n}.json'; response = folder/f'response-{n}.json'
            if reserved.exists():
                record = json.loads(reserved.read_text())
                if record['identity_sha256'] != key or record['attempt'] != n:
                    raise ValueError('reserved query identity changed')
            elif response.exists():
                raise ValueError('source response has no prior budget reservation')
            else:
                if len(list(self.root.rglob('reserved-*.json'))) >= self.max_queries:
                    raise ValueError('cross-restart source attempt budget exhausted')
                write_packet_once(reserved, {'identity_sha256': key, 'attempt': n,
                    'reserved_at_utc': datetime.now(timezone.utc).isoformat()})
                try:
                    fields, rows = fetch()
                except Exception as exc:
                    write_packet_once(response, {'identity_sha256': key, 'reservation_sha256': file_sha(reserved),
                        'status': 'SOURCE_ERROR', 'error_type': type(exc).__name__, 'error': str(exc)})
                else:
                    payload = {'fields': list(fields), 'rows': rows,
                               'captured_at_utc': datetime.now(timezone.utc).isoformat()}
                    write_packet_once(response, {'identity_sha256': key, 'reservation_sha256': file_sha(reserved),
                        'status': 'CAPTURED', 'payload': payload, 'payload_sha256': digest(payload)})
            if not response.exists():
                continue  # interrupted outcome unknown; preserve reservation, consume a new attempt
            record = json.loads(response.read_text())
            if record['identity_sha256'] != key or record['reservation_sha256'] != file_sha(reserved):
                raise ValueError('captured query provenance changed')
            if record['status'] == 'SOURCE_ERROR': continue
            if record['status'] != 'CAPTURED' or digest(record['payload']) != record['payload_sha256']:
                raise ValueError('captured response checksum/status changed')
            receipt = {'request_file': str(request.relative_to(self.root)), 'request_sha256': file_sha(request),
                'reserved_file': str(reserved.relative_to(self.root)), 'reserved_sha256': file_sha(reserved),
                'response_file': str(response.relative_to(self.root)), 'response_sha256': file_sha(response)}
            return record['payload'], receipt
        raise ValueError('source query attempts exhausted: '+key)
