"""Synthetic primary-source capture: no real HTTP, SDK or account invocation."""
import base64
import copy
import importlib
import json
import tempfile
import unittest
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch


class PrimaryCaptureTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.capture_low_market_residual_vol_primary_pre2026')
        except ModuleNotFoundError:self.fail('bounded primary capture module missing')

    def cases(self,m):
        return [dict(case_id=c+'|'+ex,instrument=c,publication_day=pub,ex_date=ex,kind=kind,
                     organization_id='ORG'+c[2:],source_packet_sha256='a'*64,
                     source_distributions=[],source_adjustments=[],reference_gap_bars=[])
                for c,pub,ex,kind in m.CASE_SCOPE]

    def request(self,m):
        return {'cases':self.cases(m),'maximum_http_query_reservations':24,
                'minimum_interval_seconds':.3,'max_attempts_per_identity':1,
                'maximum_consecutive_failed_cases':3,'max_pages_per_exact_day':2}

    def wire(self,url,data):
        if not isinstance(data,bytes):data=json.dumps(data).encode()
        return ['http_response'],[dict(status=200,content_type='application/pdf',final_url=url,
            body_base64=base64.b64encode(data).decode(),body_truncated=False,body_complete=True,
            read_error_type=None,read_error=None)]

    def fetcher(self,m,mode=None,mutate=None):
        calls=[]
        def fetch(url,payload):
            calls.append((url,copy.deepcopy(payload)))
            if mode=='fail':raise OSError('synthetic source failure')
            if mode=='interrupt':raise KeyboardInterrupt('synthetic interrupt')
            if payload is not None:
                c=next(x for x in self.cases(m) if x['instrument'][2:]==payload['stock'].split(',')[0] and x['publication_day']==payload['seDate'].split('~')[0])
                stamp=int(datetime.fromisoformat(c['publication_day']+'T12:00:00+08:00').timestamp()*1000)
                row={'secCode':c['instrument'][2:],'announcementTitle':'2024年度利润分配实施的公告','announcementTime':stamp,'announcementId':c['instrument'][2:],'adjunctUrl':'finalpage/'+c['publication_day']+'/'+c['instrument'][2:]+'.PDF'}
                if mode=='two_pages':
                    records=[dict(row,announcementTitle='年度报告',announcementId=str(1000+i)) for i in range(30)] if payload['pageNum']=='1' else [row]
                    return self.wire(url,{'totalAnnouncement':31,'announcements':records})
                return self.wire(url,{'totalAnnouncement':1,'announcements':[row]})
            if mutate:mutate()
            return self.wire(url,b'not PDF' if mode=='badpdf' else b'%PDF-1.4 synthetic original')
        return fetch,calls

    def capture(self,m,d,mode=None,mutate=None):
        original=Path(d)/'input.json';original.write_text('{}')
        r=self.request(m);auth={'known_hashes':{str(original):m.sha256_file(original)},'cases':r['cases']}
        fetch,calls=self.fetcher(m,mode,lambda:mutate(original) if mutate else None)
        out=Path(d)/m.OUTPUT
        with patch.object(m.time,'sleep'):
            result=m.capture(r,auth,out,fetch,request_bytes=b'{}',request_sha='a'*64)
        return result,out,calls

    def test_selector_accepts_pailin_but_rejects_ambiguity_proposal_security_path(self):
        m=self.api();case=self.cases(m)[4];day=case['publication_day']
        row={'code':'000403','day':day,'title':'派林生物：2024年度利润分配实施的公告','announcement_id':'123','pdf_path':'finalpage/'+day+'/123.PDF'}
        self.assertEqual(m.select_implementation_notice([row],case),row)
        for rows in ([row,dict(row,announcement_id='124',pdf_path='finalpage/'+day+'/124.PDF')],
                     [dict(row,title='2024年度利润分配预案')],[dict(row,code='000404')],
                     [dict(row,pdf_path='https://evil/123.PDF')],[dict(row,pdf_path='finalpage/'+day+'/124.PDF')],
                     [dict(row,title='关于2024年度利润分配实施公告的更正公告')]):
            with self.assertRaises(ValueError):m.select_implementation_notice(rows,case)

    def test_all_eight_only_exact_api_pdf_journal_and_false_admission(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d)
            self.assertTrue(result['capture_complete']);self.assertEqual(len(result['documents']),8)
            self.assertEqual(result['HTTP_query_reservations'],16);self.assertEqual(len(calls),16)
            self.assertFalse(result['documents_financially_reviewed']);self.assertFalse(result['admitted_for_account_replay'])
            for c in calls:
                self.assertTrue(c[0].startswith('https://www.cninfo.com.cn/') if c[1] else c[0].startswith('https://static.cninfo.com.cn/finalpage/202'))
            self.assertTrue((out/'manifest.json').exists());self.assertTrue((out/'input-postcheck.json').exists())

    def test_bad_pdf_response_retained_and_three_failures_stop(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d,'badpdf')
            self.assertFalse(result['capture_complete']);self.assertEqual(len(result['errors']),3)
            self.assertEqual(result['HTTP_query_reservations'],6);self.assertEqual(len(result['pending_cases']),5)
            self.assertEqual(len(list(out.glob('queries/*/response-1.json'))),6)
            self.assertEqual(len(list(out.glob('*.pdf'))),3);self.assertTrue((out/'first-error.json').exists())
            self.assertTrue((out/'stopped.json').exists())

    def test_interrupt_always_leaves_terminal_manifest_and_unanswered_reservation(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d,'interrupt')
            self.assertFalse(result['capture_complete']);self.assertEqual(result['HTTP_query_reservations'],1)
            self.assertEqual(result['abnormal_exit']['error_type'],'KeyboardInterrupt')
            self.assertTrue((out/'terminal-error.json').exists());self.assertTrue((out/'first-error.json').exists())
            self.assertFalse(list(out.glob('queries/*/response-1.json')))

    def test_source_error_reservations_permanent_and_postcheck_change_not_complete(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d,'fail')
            self.assertEqual(result['HTTP_query_reservations'],3);self.assertEqual(len(result['errors']),3)
            self.assertFalse(list(out.glob('queries/*/reserved-2.json')))
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d,mutate=lambda p:p.write_text('changed'))
            self.assertFalse(result['capture_complete']);self.assertFalse(result['source_inputs_unchanged_after_capture']);self.assertTrue((out/'first-error.json').exists())

    def test_existing_output_wrong_sha_and_preflight_never_capture(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);out=base/m.OUTPUT;req=base/'request.json';req.write_text('{}')
            args=['--request',str(req),'--expected-request-sha256','0'*64,'--source-root',d,'--output-dir',str(out),'--source-preflight-only']
            with self.assertRaises(ValueError):m.main(args)
            self.assertFalse(out.exists());args[3]=m.sha256_file(req)
            with patch.object(m,'load_inputs',return_value={'known_hashes':{},'cases':[]}),patch.object(m,'capture',side_effect=AssertionError('capture forbidden')) as cap,patch.object(m,'read_wire',side_effect=AssertionError('HTTP forbidden')) as wire:
                self.assertEqual(m.main(args),0);cap.assert_not_called();wire.assert_not_called()
            self.assertFalse(out.exists());out.mkdir()
            with patch.object(m,'load_inputs',side_effect=AssertionError('input read forbidden')):
                with self.assertRaises(ValueError):m.main(args)

    def test_exact_two_pages_plus_one_pdf_uses24_reservations(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            result,out,calls=self.capture(m,d,'two_pages')
            self.assertTrue(result['capture_complete']);self.assertEqual(result['HTTP_query_reservations'],24)
            self.assertEqual(len(calls),24);self.assertEqual(len(list(out.glob('queries/*/reserved-1.json'))),24)
            self.assertTrue(all(len(doc['HTTP_listing_receipts'])==2 for doc in result['documents'].values()))

    def source_fixture(self,m):
        packets={};orgs={}
        for c,pub,ex,kind in m.CASE_SCOPE:
            p=packets.setdefault(c,dict(instrument=c,window=['2023-12-29','2025-12-31'],bars=[],distributions=[],adjustments=[]))
            vendor=c[:2].lower()+'.'+c[2:];orgs[c]='ORG'+c[2:]
            for at in ((date.fromisoformat(ex)-timedelta(days=1)).isoformat(),ex):
                p['bars'].append(dict(date=at,code=vendor,adjustflag='3',tradestatus='1',close='10',preclose='9'))
            p['adjustments'].append(dict(code=vendor,dividOperateDate=ex))
            for amount in (['0.286','0.091'] if kind=='CONFLICTING_CASH_ROWS' else ['.3'] if kind=='NONCASH' else []):
                p['distributions'].append(dict(code=vendor,dividOperateDate=ex,dividPlanDate=pub,
                    dividCashPsBeforeTax=amount,dividStocksPs='.2' if kind=='NONCASH' else '0',dividReserveToStockPs=''))
        for p in packets.values():p['bars'].sort(key=lambda x:x['date'])
        return packets,orgs

    def test_actual_source_case_rules_preserve_double_cash_and_reject_missing_gap_or_rewritten_rows(self):
        m=self.api();packets,orgs=self.source_fixture(m)
        cases=m.build_source_cases(packets,orgs,packet_hashes={c:'a'*64 for c in packets})
        self.assertEqual(len(cases),8);self.assertEqual(len(cases[5]['source_distributions']),2)
        self.assertEqual(cases[6]['source_distributions'],[]);self.assertEqual(len(cases[6]['reference_gap_bars']),2)
        for change in ('double_row_dropped','added_cash','gap_removed','wrong_publication','wrong_org'):
            p,o=copy.deepcopy(packets),dict(orgs)
            if change=='double_row_dropped':p['SH601966']['distributions'].pop()
            if change=='added_cash':p['SH601966']['distributions'].append(dict(p['SH601966']['distributions'][0],dividOperateDate='2025-10-23'))
            if change=='gap_removed':p['SZ000728']['bars'][-1]['preclose']='10'
            if change=='wrong_publication':p['SH600763']['distributions'][0]['dividPlanDate']='2024-07-02'
            if change=='wrong_org':o['SZ000403']='../wrong'
            with self.subTest(change=change),self.assertRaises(ValueError):m.build_source_cases(p,o)

    def test_exact_maps_budget_and_source_scope_cannot_be_omitted_or_broadened(self):
        m=self.api();r=self.request(m)
        r.update(status='FROZEN_LOW_MARKET_RESIDUAL_VOL1M_EIGHT_PRIMARY_PRE2026',candidate='low_market_residual_vol_1m',
            window=['2023-12-29','2025-12-31'],protocol_file=m.PROTOCOL,output_relative=m.OUTPUT,
            method_code_sha256={n:'a'*64 for n in m.METHOD_FILES},public_evidence_sha256={n:'b'*64 for n in m.PUBLIC_FILES},local_source_sha256={n:'c'*64 for n in m.LOCAL_FILES})
        m.check_scope(r)
        for k,v in [('method_code_sha256',{}),('public_evidence_sha256',{}),('local_source_sha256',{}),('maximum_http_query_reservations',25),('max_attempts_per_identity',True),('cases',r['cases'][:-1])]:
            wrong=copy.deepcopy(r);wrong[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):m.check_scope(wrong)

    def test_financial_and_target_actual_bytes_bound_before_and_after(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);account=root/'low-market-residual-vol1m-budgeted-pre2026-development-20261021';account.mkdir()
            target=account/'targets.json';target.write_text('original frozen target')
            hashes={}
            for extra in (20,40):
                for family in ('eligible_equal_weight','low_total_vol_1m_control','low_market_residual_vol_1m'):
                    for name in ('days.csv','decision_intents.json','holdings.csv','orders.csv','positions.pkl','report.pkl','suspension_mark_audit.json'):
                        rel=f'{extra}/{family}/{name}';p=account/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'original financial bytes');hashes[rel]=m.sha256_file(p)
            audit={'old42_financial_sha256':hashes}
            known=m.bind_financial_inputs(root,audit,m.sha256_file(target));self.assertEqual(len(known),43)
            bad=dict(audit,old42_financial_sha256={})
            with self.assertRaises(ValueError):m.bind_financial_inputs(root,bad,m.sha256_file(target))
            p=account/next(iter(hashes));p.write_bytes(b'changed old finance')
            with self.assertRaises(ValueError):m.bind_financial_inputs(root,audit,m.sha256_file(target))
            with self.assertRaises(ValueError):m.verify_inputs(known)
            p.write_bytes(b'original financial bytes');target.write_text('changed target')
            with self.assertRaises(ValueError):m.verify_inputs(known)

    def test_strict_page_completeness_before_selector(self):
        m=self.api();case=self.cases(m)[0]
        for value in ({'totalAnnouncement':True,'announcements':[]},{'totalAnnouncement':31,'announcements':[]},{'totalAnnouncement':1,'announcements':[]}):
            with self.assertRaises(ValueError):m.validate_listing(value,case,1,None)

if __name__=='__main__':unittest.main()
