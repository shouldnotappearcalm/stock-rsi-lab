import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.capture_low_risk_raw_account_data import BAR_FIELDS,DIVIDEND_FIELDS,ADJUST_FIELDS
from scripts.fundamental_query_journal import digest,file_sha,write_packet_once


class HorizonSourceTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.low_beta60_horizon_sources')
        except ModuleNotFoundError:self.fail('fixed Oct20 horizon source adapter is absent')

    def bar(self,day,code='SH600000'):
        return dict(zip(BAR_FIELDS,[day,code[:2].lower()+'.'+code[2:],'10','11','9','10','10','1000','10000','3','1','0']))

    def dividend(self,code='SH600000',day='2026-10-15'):
        row={f:'' for f in DIVIDEND_FIELDS};row.update(code=code[:2].lower()+'.'+code[2:],dividPlanDate='2026-10-09',
            dividRegistDate='2026-10-14',dividOperateDate=day,dividPayDate=day,dividCashPsBeforeTax='0.2',
            dividStocksPs='0',dividReserveToStockPs='0',dividCashStock='10派2元')
        return row

    def wire(self,fields,rows):
        return ['provider_response'],[{'initial_error_code':'0','initial_error_msg':'success','fields':list(fields),
            'rows':rows,'iteration_error_type':None,'iteration_error':None,'final_error_code':'0','final_error_msg':'success'}]

    def inputs(self,codes=('SH600000',)):
        return {c:{'instrument':c,'window':['2023-12-29','2026-10-13'],'bars':[self.bar('2026-10-13',c)],
            'distributions':[],'adjustments':[],'quarantine':[]} for c in codes}

    def fetch(self,code,component,parameters):
        if component=='calendar':return self.wire(['calendar_date','is_trading_day'],[[f'2026-10-{d}',str(int(d not in (17,18)))] for d in range(14,21)])
        if component=='daily':
            days=['2026-10-14','2026-10-15','2026-10-16','2026-10-19','2026-10-20']
            return self.wire(BAR_FIELDS,[[self.bar(d,code)[f] for f in BAR_FIELDS] for d in days if d>=parameters['start_date']])
        if component=='dividend2026':return self.wire(DIVIDEND_FIELDS,[[self.dividend(code)[f] for f in DIVIDEND_FIELDS]])
        if component=='adjustments':return self.wire(ADJUST_FIELDS,[[code[:2].lower()+'.'+code[2:],'2026-10-15','0.98','1.02','1.02']])
        self.fail('unexpected source component')

    # A legacy Oct16 cap, duplicate tail, lost quarantine promotion or source overwrite must fail.
    def test_calendar_and_tail_are_observed_and_old_rows_preserved_with_explicit_quarantine_promotion(self):
        api=self.api();original=self.inputs();event=self.dividend();original['SH600000']['quarantine']=[{'reason':'AFTER_EXTENSION_CUTOFF','record':event}]
        tails={'SH600000':{'bars':[self.bar(d) for d in ('2026-10-14','2026-10-15','2026-10-16')],
            'distributions':[event],'adjustments':[dict(zip(ADJUST_FIELDS,['sh.600000','2026-10-15','0.98','1.02','1.02']))]}}
        before=copy.deepcopy((original,tails));calls=[]
        def fetch(code,component,parameters):calls.append((code,component,parameters));return self.fetch(code,component,parameters)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out';m=api.capture_horizon(out,original,tails,{},['2026-10-13'],fetch,request_bytes=b'fixed',maximum_queries=4)
            self.assertTrue(m['capture_complete']);self.assertEqual(4,m['query_reservations_consumed'])
            p=json.loads((out/'codes/SH600000.json').read_text());self.assertEqual(original['SH600000']['bars'],p['bars'][:1])
            self.assertEqual(['2026-10-13','2026-10-14','2026-10-15','2026-10-16','2026-10-19','2026-10-20'],[r['date'] for r in p['bars']])
            self.assertEqual(1,len(p['promoted_original_quarantine']));self.assertEqual([],p['quarantine'])
            self.assertEqual('2026-10-17',calls[1][2]['start_date']);self.assertEqual(before,(original,tails))
            self.assertFalse(m['portfolio_returns_computed']);self.assertFalse(m['admitted_for_account_replay'])
            with self.assertRaises(ValueError):api.capture_horizon(out,original,tails,{},['2026-10-13'],fetch,request_bytes=b'fixed',maximum_queries=4)
            self.assertEqual(4,len(calls))

    def reused(self,base,*,at='2026-10-21T00:00:00+00:00',parameters=None):
        identity={'source':'BaoStock','instrument':'SH600000','component':'dividend2026',
            'parameters':parameters or {'year':'2026','yearType':'operate'},'low_beta60_extension_request_sha256':'1'*64}
        folder=base/'queries'/digest(identity);folder.mkdir(parents=True)
        payload={'fields':['provider_response'],'rows':self.wire(DIVIDEND_FIELDS,[[self.dividend()[f] for f in DIVIDEND_FIELDS]])[1],'captured_at_utc':at}
        write_packet_once(folder/'request.json',identity);write_packet_once(folder/'reserved-1.json',{'identity_sha256':folder.name,'attempt':1,'reserved_at_utc':'2026-10-21T00:00:00+00:00'})
        write_packet_once(folder/'response-1.json',{'identity_sha256':folder.name,'reservation_sha256':file_sha(folder/'reserved-1.json'),'status':'CAPTURED','payload':payload,'payload_sha256':digest(payload)})
        receipt={}
        for field,name in (('request','request.json'),('reserved','reserved-1.json'),('response','response-1.json')):
            receipt[field+'_file']=str((folder/name).relative_to(base));receipt[field+'_sha256']=file_sha(folder/name)
        return {'instrument':'SH600000','source_query_receipts':{'dividend2026':receipt}}

    # Re-querying a complete post-cutoff annual response wastes budget; stale or altered responses must never qualify.
    def test_authenticated_post_cutoff_full_year_response_reuse_saves_a_query_and_rejects_stale_or_tampered_sources(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);packet=self.reused(base);value=api.load_dividend_reuse(base,packet,'1'*64)
            original=self.inputs();calls=[]
            def fetch(code,component,parameters):
                self.assertNotEqual('dividend2026',component);calls.append(component);return self.fetch(code,component,parameters)
            m=api.capture_horizon(base/'out',original,{}, {'SH600000':value},['2026-10-13'],fetch,request_bytes=b'fixed',maximum_queries=3)
            self.assertTrue(m['capture_complete']);self.assertEqual(['calendar','daily','adjustments'],calls)
            f=base/packet['source_query_receipts']['dividend2026']['response_file'];f.write_bytes(f.read_bytes()+b' ')
            with self.assertRaises(ValueError):api.load_dividend_reuse(base,packet,'1'*64)
        for changes in ({'at':'2026-10-19T00:00:00+00:00'},{'parameters':{'year':'2025','yearType':'operate'}}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as d:
                base=Path(d);packet=self.reused(base,**changes)
                with self.assertRaises(ValueError):api.load_dividend_reuse(base,packet,'1'*64)

    # Missing calendar flags cannot be replaced by inferred weekdays; bad calendar stops before stock queries.
    def test_missing_or_invalid_calendar_is_retained_and_stops_before_any_stock_query(self):
        api=self.api()
        for invalid in ('missing','flag'):
            with self.subTest(invalid=invalid),tempfile.TemporaryDirectory() as d:
                def fetch(code,component,parameters):
                    self.assertEqual('calendar',component)
                    fields,rows=self.fetch(code,component,parameters)
                    if invalid=='missing':rows[0]['rows'].pop()
                    else:rows[0]['rows'][0][1]='unknown'
                    return fields,rows
                m=api.capture_horizon(Path(d)/'out',self.inputs(),{}, {},['2026-10-13'],fetch,request_bytes=b'fixed',maximum_queries=4)
                self.assertFalse(m['capture_complete']);self.assertIn('__calendar__',m['errors_sha256'])
                self.assertEqual(['SH600000'],m['pending_codes']);self.assertEqual(1,m['query_reservations_consumed'])

    # Incorrect budgets or cached issuer/price rows must be rejected before reserving even the calendar request.
    def test_budget_and_bad_cached_rows_reject_before_output_or_network(self):
        api=self.api()
        def forbidden(*args):self.fail('unvalidated source caused a network request')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out'
            for bad in (True,3,5,215):
                with self.subTest(budget=bad):
                    with self.assertRaises(ValueError):api.capture_horizon(out,self.inputs(),{}, {},['2026-10-13'],forbidden,request_bytes=b'fixed',maximum_queries=bad)
                    self.assertFalse(out.exists())
            bad={'SH600000':{'bars':[self.bar('2026-10-14','SH600001')],'distributions':[],'adjustments':[]}}
            with self.assertRaises(ValueError):api.capture_horizon(out,self.inputs(),bad,{},['2026-10-13'],forbidden,request_bytes=b'fixed',maximum_queries=4)
            self.assertFalse(out.exists())

    # Three failing securities consume one attempt each; no retry or new directory can silently restart this output.
    def test_three_failures_stop_and_interruptions_leave_consumed_reservations(self):
        api=self.api();original=self.inputs(tuple('SH60000'+str(i) for i in range(4)))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out'
            def fetch(code,component,parameters):
                if component=='calendar':return self.fetch(code,component,parameters)
                raise OSError('synthetic source outage')
            m=api.capture_horizon(out,original,{}, {},['2026-10-13'],fetch,request_bytes=b'fixed',maximum_queries=13)
            self.assertEqual(4,m['query_reservations_consumed']);self.assertEqual(3,len(m['errors_sha256']))
            self.assertEqual(['SH600003'],m['pending_codes']);self.assertTrue(m['stopped_after_three_failed_codes'])
            self.assertEqual([],list(out.rglob('reserved-2.json')))
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out'
            def interrupt(code,component,parameters):
                if component=='calendar':return self.fetch(code,component,parameters)
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):api.capture_horizon(out,self.inputs(),{}, {},['2026-10-13'],interrupt,request_bytes=b'fixed',maximum_queries=4)
            m=json.loads((out/'manifest.json').read_text());self.assertTrue(m['abnormal_termination'])
            self.assertEqual(2,m['query_reservations_consumed']);self.assertFalse(m['capture_complete'])

    # A late valid corporate event must not disappear under the legacy Oct16 validator cap.
    def test_oct20_distribution_is_kept_and_future_distribution_quarantined(self):
        api=self.api();a=self.dividend(day='2026-10-20');b=self.dividend(day='2026-10-21')
        accepted,excluded=api.validate_dividends20('SH600000',DIVIDEND_FIELDS,[[r[f] for f in DIVIDEND_FIELDS] for r in (a,b)])
        self.assertEqual([a],accepted);self.assertEqual(b,excluded[0]['record'])


if __name__=='__main__':unittest.main()
