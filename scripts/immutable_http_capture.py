"""One reserved logical HTTP attempt per resource, preserving raw response bytes.
No retry, resume, credentials, alternate endpoint or unregistered resource.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_once(path, value):
    try:
        with Path(path).open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException as exc:
        exc.capture_evidence_persistence_error = True
        raise


def now():
    return datetime.now(timezone.utc).isoformat()


class ImmutableHttpCapture:
    def __init__(self, root, resources, *, max_attempts, max_body_bytes, opener=urlopen):
        self.root, self.resources = Path(root), json.loads(json.dumps(resources))
        need(type(max_attempts) is int and 0 < max_attempts == len(resources), 'exact resource attempt budget required')
        need(type(max_body_bytes) is int and max_body_bytes > 0, 'positive raw body limit required')
        need(all(type(k) is str for k in resources), 'named frozen resources required')
        need(len({digest(v) for v in resources.values()}) == len(resources), 'duplicate logical HTTP resource forbidden')
        for identity in resources.values():
            parsed = urlsplit(identity['url'])
            need(parsed.scheme == 'https' and parsed.hostname in ('www.cninfo.com.cn', 'static.cninfo.com.cn')
                 and parsed.username is None and parsed.password is None,
                 'explicit official HTTPS resource required')
            need(identity['method'] in ('GET', 'POST') and (identity['payload'] is None) == (identity['method'] == 'GET'),
                 'explicit GET or form POST resource required')
        self.max_attempts, self.max_body_bytes, self.opener = max_attempts, max_body_bytes, opener
        self.root.mkdir()
        self.attempts = 0

    def fetch(self, resource):
        need(resource in self.resources, 'resource outside frozen HTTP scope')
        identity = self.resources[resource]
        folder = self.root / digest({'resource': resource, 'identity': identity})
        need(not folder.exists(), 'logical resource already reserved; retry forbidden')
        need(self.attempts < self.max_attempts, 'logical HTTP attempt budget exhausted')
        folder.mkdir()
        write_once(folder / 'request.json', {'resource': resource, **identity})
        write_once(folder / 'reservation.json', {'resource': resource, 'identity_sha256': digest(identity),
                    'attempt': 1, 'reserved_at_utc': now(), 'maximum_logical_attempts': 1})
        self.attempts += 1
        body, primary, received = None, None, None
        result = {'resource': resource, 'identity_sha256': digest(identity), 'started_at_utc': now(),
                  'request_sha256': file_sha(folder / 'request.json'),
                  'reservation_sha256': file_sha(folder / 'reservation.json')}
        try:
            form = None if identity['payload'] is None else urlencode(identity['payload']).encode()
            request = Request(identity['url'], data=form, method=identity['method'], headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/',
                **({'Content-Type': 'application/x-www-form-urlencoded'} if form is not None else {})})
            try:
                response = self.opener(request, timeout=20)
            except HTTPError as exc:
                response = exc  # Preserve HTTP error bytes too; semantic admission is separate.
            with response:
                result.update(http_status=response.status, final_url=response.url,
                              content_type=response.headers.get('Content-Type'),
                              content_length_header=response.headers.get('Content-Length'))
                body = response.read(self.max_body_bytes + 1)
                received = now()
                try:
                    with (folder / 'body.bin').open('xb') as stream:
                        stream.write(body)
                        stream.flush()
                        os.fsync(stream.fileno())
                except BaseException as exc:
                    exc.capture_evidence_persistence_error = True
                    raise
                result.update(body_sha256=file_sha(folder / 'body.bin'), body_bytes=len(body),
                              body_complete=len(body) <= self.max_body_bytes, captured_at_utc=received)
                need(len(body) <= self.max_body_bytes, 'raw response exceeds frozen body cap; prefix preserved')
                length = result['content_length_header']
                if length is not None:
                    need(type(length) is str and length.isdigit(), 'invalid original Content-Length')
                    if int(length) != len(body):
                        result['body_complete'] = False
                        raise ValueError('incomplete declared raw response; received bytes preserved')
                final = urlsplit(response.url)
                need(final.scheme == 'https' and final.hostname == urlsplit(identity['url']).hostname,
                     'official response redirected outside frozen host')
                result['status'] = 'RAW_HTTP_RESPONSE_CAPTURED_NOT_ADMITTED'
        except BaseException as exc:
            primary = exc
            result.update(status='FETCH_OR_PERSISTENCE_ERROR', error_type=type(exc).__name__, error=str(exc))
        result['finished_at_utc'] = now()
        try:
            write_once(folder / 'response.json', result)
        except BaseException as exc:
            if primary is not None:
                primary.add_note('HTTP response metadata persistence error: ' + type(exc).__name__)
                raise primary from exc
            raise
        if primary is not None:
            raise primary
        return {'folder': str(folder.relative_to(self.root.parent)), 'record': result,
                'response_sha256': file_sha(folder / 'response.json')}, folder / 'body.bin'
