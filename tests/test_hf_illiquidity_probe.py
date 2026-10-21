import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from scripts import probe_hf_illiquidity_minutes_pre2026 as probe


class HfIlliquidityProbeTests(unittest.TestCase):
    def test_redirect_is_never_implicitly_followed_and_response_body_is_retained(self):
        handler=probe.NoRedirect()
        request=Request('https://huggingface.co/object')
        self.assertIsNone(handler.redirect_request(request,None,302,'redirect',{},'https://unregistered.test/secret'))
        error=HTTPError(request.full_url,302,'redirect',Message(),BytesIO(b'source redirect body'))
        with patch.object(probe,'build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(probe.SourceResponseFailure) as caught:probe.read_bytes(request,100)
            self.assertEqual(caught.exception.body,b'source redirect body')
            self.assertEqual(opener.return_value.open.call_count,1)

    def test_public_error_redacts_mixed_case_signed_action_urls(self):
        for scheme in ['https','HTTPS','hTtPs']:
            result=probe.safe_error(RuntimeError(scheme+'://huggingface.co/object?token=PRIVATE_SIGNED_TOKEN'))
            self.assertNotIn('PRIVATE_SIGNED_TOKEN',result['error'])
            self.assertIn('[redacted source URL]',result['error'])

    def setup_fixture(self, tmp):
        repo=Path(tmp)/'repo';base=Path(tmp)/'base';base.mkdir()
        pairs=sorted([['SH603056',f'{y}-{m:02d}-01'] for y in (2024,2025) for m in range(1,13)]
                     +[['SZ002505',f'2024-{m:02d}-01'] for m in range(3,8)])
        admission=repo/probe.ADMISSION;admission.parent.mkdir(parents=True)
        admission.write_text(json.dumps({'exceptions':[{'instrument':c,'day':d} for c,d in pairs]}))
        methods={}
        for name in probe.METHODS:
            p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic method binding\n');methods[name]=probe.sha(p)
        source={}
        for c,n in probe.RAW.items():
            p=base/n;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({'bars':[{'date':d} for code,d in pairs if code==c]}));source[n]=probe.sha(p)
        plan={'dataset':probe.REPO,'revision':probe.REV,'objects':copy.deepcopy(probe.OBJECTS),
              'maximum_logical_requests':3,'max_attempts_per_identity':1,'portfolio_replay_allowed':False,
              'output_relative':probe.OUTPUT,'raw_packet_relative':copy.deepcopy(probe.RAW),
              'source_file_sha256':source,'method_code_sha256':methods,'pairs':pairs,
              'admission_sha256':probe.sha(admission)}
        request=repo/'request.json';request.write_text(json.dumps(plan));out=base/probe.OUTPUT
        args=['--source-root',str(base),'--request',str(request),'--expected-request-sha256',probe.sha(request),'--output-dir',str(out)]
        return repo,base,plan,out,args

    def test_fixed_source_budget_pairs_and_content_objects_cannot_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,_,plan,_,_=self.setup_fixture(tmp);probe.validate_request(plan,repo)
            for key,value in [('maximum_logical_requests',4),('maximum_logical_requests',True),
                              ('max_attempts_per_identity',True),
                              ('portfolio_replay_allowed',True),('revision','other'),('pairs',plan['pairs'][:-1])]:
                changed=copy.deepcopy(plan);changed[key]=value
                with self.subTest(key=key),self.assertRaises(ValueError):probe.validate_request(changed,repo)

    def test_batch_transport_failure_is_consumed_and_all_sources_postchecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,_,_,out,args=self.setup_fixture(tmp)
            with patch.object(probe,'__file__',str(repo/'scripts/probe.py')),patch.object(probe,'read_bytes',side_effect=OSError('synthetic TLS failure')) as fetch:
                self.assertEqual(probe.main(args),2)
            self.assertEqual(fetch.call_count,1)
            summary=json.loads((out/'summary.json').read_text());self.assertEqual(summary['logical_requests_reserved'],1)
            self.assertEqual(summary['terminal_error']['error_type'],'OSError')
            self.assertTrue(summary['all_bound_inputs_unchanged']);self.assertFalse(summary['portfolio_returns_computed'])

    def test_bad_content_hash_keeps_both_original_objects_and_never_calls_parser(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,_,_,out,args=self.setup_fixture(tmp)
            objects=[dict(oid=s['oid'],size=s['size'],actions={'download':{'href':'https://huggingface.co/test?secret=temporary'}}) for s in probe.OBJECTS.values()]
            with patch.object(probe,'__file__',str(repo/'scripts/probe.py')), \
                 patch.object(probe,'read_bytes',side_effect=[json.dumps({'objects':objects}).encode(),b'first',b'second']), \
                 patch.object(probe,'selected_parquet_rows') as parser:
                self.assertEqual(probe.main(args),2)
            parser.assert_not_called()
            self.assertEqual((out/'SH603056.parquet').read_bytes(),b'first')
            self.assertEqual((out/'SZ002505.parquet').read_bytes(),b'second')
            s=json.loads((out/'summary.json').read_text());self.assertEqual(s['logical_requests_reserved'],3)
            self.assertEqual(len(s['source_failures']),2)
            self.assertNotIn('temporary',(out/'summary.json').read_text())

    def test_interrupt_stops_requests_but_retains_original_failure_and_postcheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,_,_,out,args=self.setup_fixture(tmp)
            with patch.object(probe,'__file__',str(repo/'scripts/probe.py')),patch.object(probe,'read_bytes',side_effect=KeyboardInterrupt('stop')) as fetch:
                self.assertEqual(probe.main(args),2)
            self.assertEqual(fetch.call_count,1)
            s=json.loads((out/'summary.json').read_text());self.assertEqual(s['terminal_error']['error_type'],'KeyboardInterrupt')
            self.assertTrue(s['all_bound_inputs_unchanged'])

    def test_first_write_failure_still_checks_source_bytes_before_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo,_,_,out,args=self.setup_fixture(tmp);real=probe.write
            def fail_first(path,value):
                if path.name=='input-before.json':raise OSError('initial persistence failure')
                real(path,value)
            with patch.object(probe,'__file__',str(repo/'scripts/probe.py')),patch.object(probe,'write',side_effect=fail_first),patch.object(probe,'read_bytes') as fetch:
                self.assertEqual(probe.main(args),2)
            fetch.assert_not_called()
            s=json.loads((out/'summary.json').read_text());self.assertTrue(s['all_bound_inputs_unchanged'])
            self.assertEqual(s['logical_requests_reserved'],0)


if __name__=='__main__':unittest.main()
