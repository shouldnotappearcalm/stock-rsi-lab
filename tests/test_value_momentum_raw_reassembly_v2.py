import copy
import json
import tempfile
import unittest
from pathlib import Path
from scripts.fundamental_query_journal import digest, file_sha, write_packet_once
from tests.test_value_momentum_raw_extension_sources import packet, prefix, DAYS, CODE, envelope
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS
try:
    from scripts import reassemble_value_momentum_raw_extension_v2 as subject
except ImportError:
    subject = None


def adjustment(day,fore,back):
    return dict(code='sz.000001',dividOperateDate=day,foreAdjustFactor=fore,backAdjustFactor=back,adjustFactor=back)


def fixtures():
    old=packet(DAYS[:3]);old['window'][1]='2026-10-16'
    old['adjustments']=[adjustment('2026-04-28','0.900000','9.000000'),adjustment('2026-07-01','1.000000','10.000000')]
    fresh=packet(DAYS[2:]);fresh['window'][0]='2026-01-01'
    fresh['adjustments']=[adjustment('2026-04-28','0.818182','9.000000'),adjustment('2026-07-01','0.909091','10.000000'),adjustment('2026-10-20','1.000000','11.000000')]
    review={'instrument':CODE,'file':CODE+'.pdf','sha256':'a'*64,'publication_day':'2026-10-13','record_date':'2026-10-19','ex_date':'2026-10-20','cash_payment_date':'2026-10-20','cash_per_original_share_CNY':'0.1','stock_per_original_share':'0','capital_per_original_share':'0','primary_pages':[1]}
    return old,fresh,review


class ReassemblyTests(unittest.TestCase):
    def setUp(self):self.assertIsNotNone(subject,'separate local-only V2 module required')

    def test_rational_rounding_explains_every_common_fore_change_without_mutation(self):
        old,fresh,review=fixtures();before=copy.deepcopy((old,fresh))
        proof=subject.verify_coordinate_transition(fresh,old,review)
        self.assertEqual(len(proof['common_fore_coordinate_checks']),2)
        self.assertEqual(proof['old_latest_back'],'10.000000');self.assertEqual(proof['new_latest_back'],'11.000000')
        self.assertEqual(proof['ratio_exact'],'10/11');self.assertEqual((old,fresh),before)
        bad=copy.deepcopy(fresh);bad['adjustments'][0]['foreAdjustFactor']='0.818184'
        with self.assertRaisesRegex(ValueError,'rounding'):subject.verify_coordinate_transition(bad,old,review)

    def test_nonfore_core_cash_date_deletion_and_duplicate_changes_all_fail(self):
        old,fresh,review=fixtures()
        mutations=[lambda v:v['adjustments'][0].update(backAdjustFactor='9.000001'),
          lambda v:v['adjustments'][0].update(adjustFactor='9.000001'),
          lambda v:v['bars'][0].update(volume='999'),lambda v:v['adjustments'].pop(0),
          lambda v:v['adjustments'].insert(0,copy.deepcopy(v['adjustments'][0])),
          lambda v:v['adjustments'][0].update(dividOperateDate='2026-04-29'),
          lambda v:v['distributions'].append({'dividOperateDate':'2026-06-01','cash':'new'})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                bad=copy.deepcopy(fresh);mutate(bad)
                with self.assertRaises(ValueError):subject.verify_coordinate_transition(bad,old,review)

    def test_notice_must_match_cash_only_issuer_ex_date_and_positive_cash(self):
        old,fresh,review=fixtures()
        for changed in ({'instrument':'SZ000002'},{'ex_date':'2026-10-19'},{'stock_per_original_share':'.1'},
                        {'capital_per_original_share':'.1'},{'cash_per_original_share_CNY':'0'},
                        {'publication_day':'2026-10-21'},{'primary_pages':[]}):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):subject.verify_coordinate_transition(fresh,old,{**review,**changed})
        bad=copy.deepcopy(fresh);bad['adjustments'].append(adjustment('2026-10-19','1.000000','10.500000'))
        with self.assertRaises(ValueError):subject.verify_coordinate_transition(bad,old,review)

    def test_fixed_six_decimal_positive_coordinate_only(self):
        old,fresh,review=fixtures()
        for value in ('NaN','1','0.000000','-1.000000','0.9090911'):
            with self.subTest(value=value):
                bad=copy.deepcopy(fresh);bad['adjustments'][1]['foreAdjustFactor']=value
                with self.assertRaises(ValueError):subject.verify_coordinate_transition(bad,old,review)

    def test_original_prefix_must_preserve_every_raw_field_and_sequence(self):
        old=prefix();assembled=packet();subject.verify_original_prefix(assembled,old)
        bad=copy.deepcopy(assembled);bad['bars'][0]['close']='10.0000'
        with self.assertRaises(ValueError):subject.verify_original_prefix(bad,old)
        bad=copy.deepcopy(assembled);bad['bars'][:2]=list(reversed(bad['bars'][:2]))
        with self.assertRaises(ValueError):subject.verify_original_prefix(bad,old)

    def test_readonly_journal_validates_hashes_and_never_fetches_or_reserves(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);identity={'test':'fixed'};q=root/'queries'/digest(identity);q.mkdir(parents=True)
            write_packet_once(q/'request.json',identity)
            write_packet_once(q/'reserved-1.json',{'identity_sha256':q.name,'attempt':1})
            fields,rows=envelope(BAR_FIELDS,[]);payload={'fields':fields,'rows':rows,'captured_at_utc':'fixed'}
            write_packet_once(q/'response-1.json',{'identity_sha256':q.name,'reservation_sha256':file_sha(q/'reserved-1.json'),'status':'CAPTURED','payload':payload,'payload_sha256':digest(payload)})
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            journal=subject.ReadOnlyJournal(root)
            value,receipt=journal.query(identity,lambda:self.fail('network fallback called'))
            self.assertEqual(value,payload);self.assertEqual(receipt['response_sha256'],file_sha(q/'response-1.json'))
            with self.assertRaises(ValueError):journal.query({'test':'missing'},lambda:self.fail('network fallback called'))
            self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
            v=json.loads((q/'response-1.json').read_text());v['payload']['rows'][0]['final_error_code']='99'
            (q/'response-1.json').write_text(json.dumps(v))
            with self.assertRaises(ValueError):journal.query(identity,None)

    def test_copy_accepted_packet_is_byte_exact_and_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'original.json';target=Path(d)/'copy.json';source.write_bytes(b'{"x": 1}\n\n')
            subject.copy_exact(source,target,file_sha(source));self.assertEqual(source.read_bytes(),target.read_bytes())
            with self.assertRaises(FileExistsError):subject.copy_exact(source,target,file_sha(source))
            with self.assertRaises(ValueError):subject.copy_exact(source,Path(d)/'bad.json','0'*64)

    def test_entry_refuses_existing_output_before_request_or_source_read(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'existing'):
                subject.main(['--source-root',d,'--request','absent','--expected-request-sha256','none','--output-dir',d])


    def test_main_copies_exact_bytes_and_rechecks_inputs_before_success_manifest(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);v1=root/subject.V1;(v1/'codes').mkdir(parents=True)
            keep='SZ000002';bad=subject.REJECTED[0]
            old_bytes=b'{"instrument": "SZ000002", "untouched": true}\n\n'
            (v1/'codes'/f'{keep}.json').write_bytes(old_bytes)
            (v1/'calendar.json').write_text('{"sessions": []}\n')
            (v1/'manifest.json').write_text('{"original": true}\n')
            (root/subject.PRIMARY).mkdir();(root/subject.PRIMARY/'manifest.json').write_text('{}')
            review=root/'review.json';review.write_text('{}');request=root/'request.json';request.write_text('{}')
            m={'calendar_sha256':file_sha(v1/'calendar.json'),'per_code_sha256':{keep:file_sha(v1/'codes'/f'{keep}.json')},'errors_sha256':{bad:'originalerror'}}
            context=(None,None,None,dict.fromkeys(range(114)))
            args=['--source-root',d,'--request',str(request),'--expected-request-sha256',file_sha(request),'--output-dir',str(root/subject.OUTPUT)]
            authenticated=({},context,m,None,{})
            with patch.object(subject,'authenticate_v2',return_value=authenticated) as auth, patch.object(subject,'prepare_packets',return_value=({keep:{},bad:{'rebuilt':True}},{})), patch.object(subject,'REVIEW',str(review)):
                self.assertEqual(subject.main(args),0);self.assertEqual(auth.call_count,2)
            out=root/subject.OUTPUT
            self.assertEqual((out/'codes'/f'{keep}.json').read_bytes(),old_bytes)
            self.assertEqual((v1/'codes'/f'{keep}.json').read_bytes(),old_bytes)
            self.assertFalse(json.loads((out/'manifest.json').read_text())['admitted_for_account_replay'])

    def test_postwrite_auth_failure_preserves_outputs_and_never_publishes_success(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);v1=root/subject.V1;v1.mkdir();(v1/'calendar.json').write_text('{}')
            request=root/'request.json';request.write_text('{}')
            m={'calendar_sha256':file_sha(v1/'calendar.json')};context=(None,None,None,{})
            with patch.object(subject,'authenticate_v2',side_effect=[({},context,m,None,{}),ValueError('original financial file changed')]), patch.object(subject,'prepare_packets',return_value=({},{})):
                with self.assertRaisesRegex(ValueError,'financial'):
                    subject.main(['--source-root',d,'--request',str(request),'--expected-request-sha256',file_sha(request),'--output-dir',str(root/subject.OUTPUT)])
            out=root/subject.OUTPUT;self.assertTrue((out/'failure.json').exists());self.assertTrue((out/'request.json').exists())
            self.assertFalse((out/'manifest.json').exists());self.assertEqual((v1/'calendar.json').read_text(),'{}')

if __name__=='__main__':unittest.main()
