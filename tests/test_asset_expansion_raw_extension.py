import copy
import importlib
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import date,timedelta
from pathlib import Path


class AssetExtensionTests(unittest.TestCase):
    def setUp(self):
        self.m=importlib.import_module('scripts.asset_expansion_extension_sources')
        self.code='SH600066'
        self.days=['2023-12-29','2026-01-05','2026-10-20','2026-10-21']

    def bar(self,at):
        return dict(zip(self.m.BAR_FIELDS,[at,'sh.600066','10','11','9','10.5','10','10000','102000','3','1','0']))

    def dividend(self,at):
        r={k:'' for k in self.m.DIVIDEND_FIELDS}
        r.update(code='sh.600066',dividOperateDate=at,dividCashPsBeforeTax='0.1',
                 dividCashPsAfterTax='0.09或0.1',dividStocksPs='0',dividReserveToStockPs='0')
        return r

    def old(self):
        return {'instrument':self.code,'window':['2023-12-29','2026-10-20'],
                'bars':[self.bar(d) for d in self.days[:-1]],'distributions':[self.dividend('2026-01-05')],
                'adjustments':[],'quarantine':[]}

    def data(self):
        return {'daily':{'fields':list(self.m.BAR_FIELDS),'rows':[list(self.bar(self.days[-1]).values())]},
                'dividend2026':{'fields':list(self.m.DIVIDEND_FIELDS),'rows':[[self.dividend('2026-01-05')[k] for k in self.m.DIVIDEND_FIELDS]]},
                'adjustments':{'fields':list(self.m.ADJUST_FIELDS),'rows':[]}}

    def calendar(self):
        first=date(2023,12,29);last=date(2026,10,21)
        return {'fields':['calendar_date','is_trading_day'],'rows':[
            [(first+timedelta(days=i)).isoformat(),'1' if (first+timedelta(days=i)).isoformat() in self.days else '0']
            for i in range((last-first).days+1)]}

    def test_calendar_uses_full_observed_flags_and_checks_all_prefixes(self):
        self.assertEqual(self.m.parse_calendar(self.calendar(),{'old':self.days[:-1]}),self.days)
        for mutate in (lambda d:d['rows'].pop(5),lambda d:d['rows'][-1].__setitem__(1,'0'),
                       lambda d:d['rows'][1].__setitem__(1,'1')):
            d=self.calendar();mutate(d)
            with self.assertRaises(ValueError):self.m.parse_calendar(d,{'old':self.days[:-1]})

    def test_append_preserves_full_original_prefix_and_literal_tax_options(self):
        old=self.old();saved=copy.deepcopy(old)
        p=self.m.assemble_packet(self.code,old,self.days,self.data())
        self.assertEqual(old,saved)
        self.assertEqual(p['bars'][:-1],old['bars'])
        self.assertEqual(p['distributions'],old['distributions'])
        self.assertEqual(p['distributions'][0]['dividCashPsAfterTax'],'0.09或0.1')
        self.assertEqual(p['window'],['2023-12-29','2026-10-21'])

    def test_missing_future_or_duplicate_daily_tail_is_not_synthesized(self):
        for mutate in (lambda d:d['daily']['rows'].clear(),
                       lambda d:d['daily']['rows'][0].__setitem__(0,'2026-10-22'),
                       lambda d:d['daily']['rows'].append(d['daily']['rows'][0]),
                       lambda d:d['daily']['fields'].pop()):
            d=self.data();mutate(d)
            with self.assertRaises(ValueError):self.m.assemble_packet(self.code,self.old(),self.days,d)

    def test_revised_missing_or_literal_changed_distribution_prefix_blocks_capture(self):
        for mutate in (lambda d:d['dividend2026']['rows'].clear(),
                       lambda d:d['dividend2026']['rows'][0].__setitem__(9,'9'),
                       lambda d:d['dividend2026']['rows'][0].__setitem__(10,'0.090或0.1')):
            d=self.data();mutate(d)
            with self.assertRaises(ValueError):self.m.assemble_packet(self.code,self.old(),self.days,d)

    def test_adjustment_tail_cannot_replace_original_event_or_accept_nonpositive_factor(self):
        original=self.old()
        original['adjustments']=[dict(zip(self.m.ADJUST_FIELDS,['sh.600066','2026-01-05','0.99','1.01','1.01']))]
        for at,factor in [('2026-01-05','1.02'),('2026-10-21','0')]:
            d=self.data();d['adjustments']['rows']=[['sh.600066',at,'1',factor,'1']]
            with self.subTest(at=at),self.assertRaises(ValueError):
                self.m.assemble_packet(self.code,original,self.days,d)

    def test_unknown_distribution_is_retained_without_entitlement(self):
        d=self.data();r=self.dividend('');d['dividend2026']['rows'].append([r[k] for k in self.m.DIVIDEND_FIELDS])
        p=self.m.assemble_packet(self.code,self.old(),self.days,d)
        self.assertEqual(p['quarantine'][0]['reason'],'MISSING_OPERATE_DATE')
        self.assertEqual(len(p['distributions']),1)

    def envelope(self,d,error='0'):
        return ['provider_response'],[{'initial_error_code':error,'initial_error_msg':'',
            'final_error_code':error,'final_error_msg':'','iteration_error_type':None,'iteration_error':None,**d}]

    def test_journaled_capture_saves_bounded_queries_and_original_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'original.json';source.write_text(json.dumps(self.old()));calls=[]
            def fetch(code,component,params):
                calls.append((code,component,params))
                return self.envelope(self.calendar() if component=='calendar' else self.data()[component])
            s=self.m.capture_extension(root/'out',{self.code:self.old()},{'old':self.days[:-1]},fetch,
                request_bytes=b'fixed fixture request',inputs={str(source):self.m.sha(source)})
            self.assertTrue(s['capture_complete']);self.assertEqual(s['query_reservations_consumed'],4)
            self.assertEqual([c[1] for c in calls],['calendar','daily','dividend2026','adjustments'])
            self.assertEqual(calls[1][2],{'start_date':'2026-10-21','end_date':'2026-10-21','frequency':'d','adjustflag':'3'})
            self.assertFalse(s['admitted_for_account_replay']);self.assertTrue(s['original_inputs_unchanged'])
            self.assertEqual(s['pending_codes'],[])
            with self.assertRaises(ValueError):self.m.capture_extension(root/'out',{self.code:self.old()},{'old':self.days[:-1]},fetch,request_bytes=b'fixed fixture request',inputs={})

    def test_source_errors_stop_after_three_without_retry_or_losing_responses(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';codes=['SH600001','SH600002','SH600003','SH600004'];calls=[]
            def fetch(code,component,params):
                calls.append((code,component))
                return self.envelope(self.calendar() if component=='calendar' else self.data()['daily'],error='0' if component=='calendar' else '100')
            olds={}
            for c in codes:
                p=self.old();p['instrument']=c
                for field in ('bars','distributions','adjustments'):
                    for row in p[field]:row['code']=c[:2].lower()+'.'+c[2:]
                olds[c]=p
            s=self.m.capture_extension(out,olds,{'old':self.days[:-1]},fetch,request_bytes=b'fixed',inputs={})
            self.assertEqual(s['names'],0);self.assertEqual(s['query_reservations_consumed'],4)
            self.assertEqual(s['pending_codes'],['SH600004']);self.assertTrue(s['stopped_after_three_failed_codes'])
            self.assertEqual(len(list(out.rglob('response-1.json'))),4)
            self.assertFalse(s['capture_complete'])

    def test_calendar_error_and_interrupt_preserve_unknown_consumed_attempt(self):
        for kind in ('calendar','interrupt'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                out=Path(td)/'out'
                def fetch(code,component,params):
                    if kind=='interrupt':raise KeyboardInterrupt('fixture stop')
                    return self.envelope({'fields':['wrong'],'rows':[]})
                if kind=='interrupt':
                    with self.assertRaises(KeyboardInterrupt):self.m.capture_extension(out,{self.code:self.old()},{'old':self.days[:-1]},fetch,request_bytes=b'fixed',inputs={})
                else:self.m.capture_extension(out,{self.code:self.old()},{'old':self.days[:-1]},fetch,request_bytes=b'fixed',inputs={})
                s=json.loads((out/'manifest.json').read_text());self.assertFalse(s['capture_complete'])
                self.assertEqual(s['query_reservations_consumed'],1)
                self.assertEqual(s['pending_codes'],[self.code])

    def test_input_mutation_is_recorded_and_prevents_capture_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'original';p.write_text('bound');inputs={str(p):self.m.sha(p)}
            def fetch(code,component,params):
                p.write_text('changed')
                return self.envelope(self.calendar() if component=='calendar' else self.data()[component])
            s=self.m.capture_extension(root/'out',{self.code:self.old()},{'old':self.days[:-1]},fetch,request_bytes=b'fixed',inputs=inputs)
            self.assertFalse(s['capture_complete']);self.assertFalse(s['original_inputs_unchanged'])


    def test_finalization_failures_retain_original_interrupt_and_independent_artifacts(self):
        for filename in ('inputs-after.json','manifest.json'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as td:
                out=Path(td)/'out';real_save=self.m.save
                def fail_one(path,value):
                    if path.name==filename:
                        path.write_text('{partial')
                        raise OSError('fixture disk failure')
                    return real_save(path,value)
                def fetch(*args):raise KeyboardInterrupt('original fixture interruption')
                with patch.object(self.m,'save',side_effect=fail_one),self.assertRaises(KeyboardInterrupt):
                    self.m.capture_extension(out,{self.code:self.old()},{'old':self.days[:-1]},fetch,request_bytes=b'fixed',inputs={})
                evidence=out/('manifest.json' if filename=='inputs-after.json' else 'finalization-error.json')
                record=json.loads(evidence.read_text())
                self.assertEqual(record['original_exception']['error_type'],'KeyboardInterrupt')
                self.assertEqual(record['persistence_errors'][0]['file'],filename)
                self.assertFalse(record['capture_complete'])


class AssetExtensionSDKTests(unittest.TestCase):
    def setUp(self):
        self.m=importlib.import_module('scripts.capture_asset_expansion_raw_extension')

    def test_sdk_only_calls_fixed_parameters_and_one_login(self):
        class Response:
            error_code='0';error_msg='';fields=[]
            def next(self):return False
        class SDK:
            def __init__(self):self.log=[]
            def login(self):self.log.append(('login',));return Response()
            def logout(self):self.log.append(('logout',));return Response()
            def query_trade_dates(self,**p):self.log.append(('calendar',p));return Response()
            def query_history_k_data_plus(self,code,fields,**p):self.log.append(('daily',code,fields,p));return Response()
        with tempfile.TemporaryDirectory() as td:
            allowed={('CN_STOCK_CALENDAR','calendar'):{'start_date':'2023-12-29','end_date':'2026-10-21'},
                     ('SH600066','daily'):{'start_date':'2026-10-21','end_date':'2026-10-21','frequency':'d','adjustflag':'3'}}
            sdk=SDK();session=self.m.SourceSession(Path(td),'fixture',sdk,allowed)
            with self.assertRaises(ValueError):session('SH600066','daily',{'start_date':'2026-10-22'})
            self.assertEqual(sdk.log,[])
            session('CN_STOCK_CALENDAR','calendar',allowed['CN_STOCK_CALENDAR','calendar'])
            session('SH600066','daily',allowed['SH600066','daily']);session.close()
            self.assertEqual([r[0] for r in sdk.log],['login','calendar','daily','logout'])
            self.assertEqual(sdk.log[2][1],'sh.600066')
            self.assertEqual(sdk.log[2][3],allowed['SH600066','daily'])
            self.assertTrue((Path(td)/'login-response-1.json').exists())
            self.assertTrue((Path(td)/'logout-response.json').exists())

    def test_partial_sdk_iteration_retains_rows_and_failure_in_envelope(self):
        class Response:
            error_code='0';error_msg='';fields=['partial'];count=0
            def next(self):
                self.count+=1
                if self.count==1:return True
                raise OSError('fixture truncated response')
            def get_row_data(self):return ['retained row']
        class SDK:
            def login(self):return Response()
            def query_trade_dates(self,**p):return Response()
        with tempfile.TemporaryDirectory() as td:
            parameters={'start_date':'2023-12-29','end_date':'2026-10-21'}
            source=self.m.SourceSession(Path(td),'fixture',SDK(),{('CN_STOCK_CALENDAR','calendar'):parameters})
            fields,rows=source('CN_STOCK_CALENDAR','calendar',parameters)
            self.assertEqual(fields,['provider_response'])
            self.assertEqual(rows[0]['rows'],[['retained row']])
            self.assertEqual(rows[0]['iteration_error_type'],'OSError')
            core=importlib.import_module('scripts.asset_expansion_extension_sources')
            with self.assertRaises(RuntimeError):core.unwrap({'fields':fields,'rows':rows})

    def test_partial_sdk_interrupt_is_journalable_then_propagates_as_interrupt(self):
        class Response:
            error_code='0';error_msg='';fields=['partial'];count=0
            def next(self):
                self.count+=1
                if self.count==1:return True
                raise KeyboardInterrupt('fixture interrupted after row')
            def get_row_data(self):return ['retained partial row']
        class SDK:
            def login(self):return Response()
            def query_trade_dates(self,**p):return Response()
        with tempfile.TemporaryDirectory() as td:
            p={'start_date':'2023-12-29','end_date':'2026-10-21'}
            source=self.m.SourceSession(Path(td),'fixture',SDK(),{('CN_STOCK_CALENDAR','calendar'):p})
            try:fields,rows=source('CN_STOCK_CALENDAR','calendar',p)
            except KeyboardInterrupt:self.fail('interruption escaped before partial envelope could be journaled')
            self.assertEqual(rows[0]['rows'],[['retained partial row']])
            self.assertEqual(rows[0]['iteration_error_type'],'KeyboardInterrupt')
            core=importlib.import_module('scripts.asset_expansion_extension_sources')
            with self.assertRaises(KeyboardInterrupt):core.unwrap({'fields':fields,'rows':rows})
            originals={'SH600066':{'instrument':'SH600066','window':['2023-12-29','2026-10-20'],
                'bars':[dict(zip(core.BAR_FIELDS,[at,'sh.600066','10','11','9','10.5','10','10000','102000','3','1','0']))
                        for at in ['2023-12-29','2026-10-20']],
                'distributions':[],'adjustments':[],'quarantine':[]}}
            out=Path(td)/'capture'
            journal_source=self.m.SourceSession(out,'fixture',SDK(),{('CN_STOCK_CALENDAR','calendar'):p})
            with self.assertRaises(KeyboardInterrupt):
                core.capture_extension(out,originals,{'old':['2023-12-29','2026-10-20']},journal_source,
                    request_bytes=b'fixed fixture',inputs={})
            response=json.loads(next(out.rglob('response-1.json')).read_text())
            self.assertEqual(response['payload']['rows'][0]['rows'],[['retained partial row']])
            self.assertEqual(response['payload']['rows'][0]['iteration_error_type'],'KeyboardInterrupt')
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertFalse(manifest['capture_complete'])
            self.assertEqual(manifest['original_exception']['error_type'],'KeyboardInterrupt')

    def test_logout_persistence_failure_preserves_capture_exception(self):
        class Source:
            def close(self):raise OSError('fixture logout record failed')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(KeyboardInterrupt,'original capture failure'):
                self.m.close_source(Source(),Path(td),KeyboardInterrupt('original capture failure'))
            r=json.loads((Path(td)/'administrative-finalization-error.json').read_text())
            self.assertEqual(r['error_type'],'OSError')
            self.assertEqual(r['original_exception_type'],'KeyboardInterrupt')

    def test_login_failure_is_retained_and_never_retried(self):
        class SDK:
            count=0
            def login(self):self.count+=1;raise OSError('fixture login failed')
            def logout(self):return type('R',(),{'error_code':'0','error_msg':''})()
        with tempfile.TemporaryDirectory() as td:
            allowed={('CN_STOCK_CALENDAR','calendar'):{'start_date':'2023-12-29','end_date':'2026-10-21'}}
            sdk=SDK();session=self.m.SourceSession(Path(td),'fixture',sdk,allowed)
            for _ in range(2):
                with self.assertRaises((OSError,RuntimeError)):session('CN_STOCK_CALENDAR','calendar',allowed['CN_STOCK_CALENDAR','calendar'])
            self.assertEqual(sdk.count,1)
            self.assertEqual(json.loads((Path(td)/'login-response-1.json').read_text())['error_type'],'OSError')


if __name__=='__main__':unittest.main()
