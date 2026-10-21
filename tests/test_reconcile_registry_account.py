"""Manually specified physical ledgers; no simulator, real data or scorer."""
import copy
import importlib
import json
import unittest
from datetime import date
from decimal import Decimal as D, ROUND_HALF_UP
from dataclasses import replace

from stock_rsi.stock_distribution_account import StockDistribution
from stock_rsi.registry_allocation_bounds import allocation_bounds
from scripts.run_price_delay_horizon_raw import reconcile_case as old_reconcile


def cent(value):return value.quantize(D('.01'),rounding=ROUND_HALF_UP)


class ReconcileRegistryAccountTests(unittest.TestCase):
    def api(self):
        try:return importlib.import_module('scripts.reconcile_registry_account')
        except ModuleNotFoundError:self.fail('independent registry leaf reconciler is missing')

    def fixture(self,chosen=361,*,component='capital',integer=False):
        sessions=['2024-05-28','2024-06-03','2024-06-04','2024-06-05','2024-06-06','2024-06-07']
        ratio=D('.4') if integer else D('.4019063');chosen=360 if integer else chosen
        event=StockDistribution('synthetic','SZ002831',date(2024,5,28),date(2024,6,3),date(2024,6,4),date(2024,6,4),date(2024,6,6),D('.8038127'),ratio if component=='capital' else D(0),component=='capital',stock_per_share=ratio if component=='stock' else D(0),stock_taxable_income_per_share=D('.4') if component=='stock' else D(0),stock_tax_basis_verified=component=='stock')
        proof={'contract':'PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1','issuer':'SZ002831','event_id':'synthetic','record_date':'2024-06-03','ex_date':'2024-06-04','component':component,'source_file':'synthetic.pdf','source_sha256':'a'*64,'published_on':'2024-05-28','available_at':'2024-05-29T00:00:00+08:00','actual_arrival_verified':False,'eligible_count':10000000,'declared_total_shares':4019063,'quoted_per10':'4.019063','fraction_method':'LARGEST_REMAINDER_DESC_RANDOM_TIES','quoted_precision_bound':'ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION'}
        audit=[];proofs={}
        if not integer:
            envelope=allocation_bounds(proof,900,as_of='2024-06-04T09:30:00+08:00')
            audit=[{'event_id':'synthetic','instrument':'SZ002831','recorded':'2024-06-03','ex_date':'2024-06-04','component':component,'registered_quantity':900,'ratio_per_original_share':str(ratio),'nominal_entitlement':str(ratio*900),'candidates':[361,362],'chosen_integer_quantity':chosen,'registry_proof_sha256':envelope['proof_sha256'],'as_of':'2024-06-04T09:30:00+08:00','envelope':envelope}]
            proofs={'synthetic':{component:proof}}
        gross=D('723.43');income=D('360.00') if component=='stock' else D('0.00');reserve=D('216.69') if component=='stock' else D('144.69');net=gross-reserve
        sellcost=cent(max(D(5),D(10)*chosen*D('.0015')))+cent(D(10)*chosen*D('.002'))
        fills=[{'order_id':'buy','execution_at':'2024-06-03T01:30:00+00:00','security_id':'SZ002831','action':'BUY','quantity':900,'price':'10','cost':'23.00','cash_after':'990977.00'}, {'order_id':'sell','execution_at':'2024-06-06T01:30:00+00:00','security_id':'SZ002831','action':'SELL','quantity':chosen,'price':'10','cost':str(sellcost),'cash_after':str(D('990977')+net+10*chosen-sellcost)}]
        ledger=[{'day':'2024-06-03','kind':'RECORD_DATE_OWNERSHIP','event_id':'synthetic','instrument':'SZ002831','quantity':900}, {'day':'2024-06-04','kind':'EX_DATE_ENTITLEMENT','event_id':'synthetic','instrument':'SZ002831','registered_quantity':900,'cash_gross':gross,'stress_tax_reserve':reserve,'capital_shares':chosen if component=='capital' else 0,'stock_shares':chosen if component=='stock' else 0,'taxable_stock_income':income}, {'day':'2024-06-05','kind':'NET_DIVIDEND_CASH_AVAILABLE','event_id':'synthetic','cash_delta':net}, {'day':'2024-06-06','kind':'CAPITAL_SHARES_LISTED' if component=='capital' else 'STOCK_DIVIDEND_SHARES_LISTED','event_id':'synthetic','quantity':chosen}]
        # Expected asset components are explicitly specified per session. The
        # two branches differ in physical shares, not a chosen performance score.
        components=[(D('1000000'),0,0,D(0),D(0),D(0)), (D('990977'),900,0,D(0),D('23'),D(0)), (D('990977'),900,chosen,net,D(0),D(0)), (D('990977')+net,900,chosen,D(0),D(0),net), (D('990977')+net+10*chosen-sellcost,900,0,D(0),sellcost,D(0)), (D('990977')+net+10*chosen-sellcost,900,0,D(0),D(0),D(0))]
        rows=[];ownership={};previous=D('1000000')
        for day,(cash,listed,pending,receivable,fee,paid) in zip(sessions,components):
            market=D(10)*listed;pendingvalue=D(10)*pending;equity=cash+market+pendingvalue+receivable
            rows.append({'day':day,'cash':cash,'market_value':market,'pending_stock_value':pendingvalue,'cash_receivable':receivable,'equity':equity,'fees':fee,'net_dividend_cash_available':paid,'exposure':(market+pendingvalue)/equity,'net_return':equity/previous-1})
            ownership[day]={'SZ002831':listed} if listed else {};previous=equity
        case={'days':rows,'fills':fills,'corporate_ledger':ledger,'ownership':ownership,'registry_allocation_audit':audit}
        bars={'SZ002831':{day:{'date':day,'tradestatus':'1','isST':'0','preclose':'10','open':'10','close':'10','volume':'1000000'} for day in sessions}}
        return case,(event,),bars,sessions,proofs

    def run_case(self,fixture):
        case,events,bars,sessions,proofs=fixture
        return self.api().reconcile_registry_case(case,events,bars,sessions,20,registry_proofs=proofs)

    def test_each_of_both_integer_envelope_leaves_reconciles_all_cash_and_shares(self):
        for component in ('capital','stock'):
            for chosen in (361,362):
                with self.subTest(component=component,chosen=chosen):
                    fixture=self.fixture(chosen,component=component);before=copy.deepcopy(fixture)
                    self.assertIs(self.run_case(fixture),True);self.assertEqual(fixture,before)
                    self.assertEqual(fixture[0]['ownership']['2024-06-06'],{'SZ002831':900})
                    self.assertEqual(fixture[0]['registry_allocation_audit'][0]['candidates'],[361,362])

    def test_every_fill_and_corporate_row_must_belong_to_the_explicit_calendar(self):
        for kind in ('fill','corporate'):
            fixture=self.fixture();case=fixture[0]
            if kind=='fill':
                case['fills'].append({'execution_at':'2024-06-08T01:30:00+00:00','security_id':'SZ002831','action':'BUY','quantity':999999,'price':'999','cost':'0','cash_after':'-1000000'})
            else:
                case['corporate_ledger'].append({'day':'2024-06-08','kind':'EX_DATE_ENTITLEMENT','event_id':'synthetic'})
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_case(fixture)

    def test_fill_must_match_the_bound_raw_open_and_session(self):
        for field,value in [('open','11'),('date','2024-06-04')]:
            fixture=self.fixture()
            fixture[2]['SZ002831']['2024-06-03'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.run_case(fixture)

    def test_fill_requires_a_tradable_source_and_positive_finite_cent_price(self):
        for field,value in [('tradestatus','0'),('open','0'),('open','-10'),('open','NaN'),('open','10.001')]:
            fixture=self.fixture()
            fixture[2]['SZ002831']['2024-06-03'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.run_case(fixture)

    def test_coherent_one_session_listing_delay_is_rejected(self):
        fixture=self.fixture();case=fixture[0]
        case['corporate_ledger'][3]['day']='2024-06-07'
        case['ownership']['2024-06-06']={'SZ002831':539}
        row=next(r for r in case['days'] if r['day']=='2024-06-06')
        row['market_value']=D('5390');row['pending_stock_value']=D('3610')
        # Total equity and exposure are unchanged: conservation alone cannot
        # detect the invented extra day of unlisted status.
        with self.assertRaises(ValueError):self.run_case(fixture)

    def test_missing_due_payment_cannot_be_hidden_as_a_permanent_receivable(self):
        fixture=self.fixture();case=fixture[0];net=D('578.74')
        case['corporate_ledger']=[r for r in case['corporate_ledger'] if r['kind']!='NET_DIVIDEND_CASH_AVAILABLE']
        for row in case['days']:
            if row['day']>='2024-06-05':
                row['cash']-=net;row['cash_receivable']+=net
                row['net_dividend_cash_available']=D(0)
        case['fills'][1]['cash_after']=str(D(case['fills'][1]['cash_after'])-net)
        with self.assertRaises(ValueError):self.run_case(fixture)

    def test_zero_owned_event_still_requires_exact_record_and_ex_source_coverage(self):
        for kind in ('RECORD_DATE_OWNERSHIP','EX_DATE_ENTITLEMENT'):
            fixture=self.fixture();case,events,bars,sessions,proofs=fixture
            event=replace(events[0],event_id='zero',instrument='SH600000',capital_per_share=D(0))
            # This additional issuer is never held, so both source-event
            # records have zero economics and cannot be detected from NAV.
            record={'day':'2024-06-03','kind':'RECORD_DATE_OWNERSHIP','event_id':'zero','instrument':'SH600000','quantity':0}
            ex={'day':'2024-06-04','kind':'EX_DATE_ENTITLEMENT','event_id':'zero','instrument':'SH600000','registered_quantity':0,'cash_gross':D(0),'stress_tax_reserve':D(0),'capital_shares':0,'stock_shares':0,'taxable_stock_income':D(0)}
            for row in (record,ex):
                if row['kind']!=kind:case['corporate_ledger'].append(row)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.run_case((case,events+(event,),bars,sessions,proofs))

    def test_live_date_objects_and_serialized_corporate_days_have_identical_clocks(self):
        fixture=self.fixture()
        for row in fixture[0]['corporate_ledger']:row['day']=date.fromisoformat(row['day'])
        self.assertIs(self.run_case(fixture),True)

    def test_serialized_fraction_pair_lists_preserve_the_same_envelope_semantics(self):
        fixture=self.fixture();case=fixture[0]
        case['registry_allocation_audit']=json.loads(json.dumps(case['registry_allocation_audit']))
        self.assertIs(self.run_case(fixture),True)

    def test_unknown_tax_and_stock_reserve_guards_remain_in_force(self):
        for kind in ('unknown_capital','unknown_stock','excessive_stock_tax'):
            fixture=self.fixture(component='stock' if kind!='unknown_capital' else 'capital')
            case,events,bars,sessions,proofs=fixture
            changed=replace(events[0],**({'capital_tax_exempt_verified':False} if kind=='unknown_capital' else
                {'stock_tax_basis_verified':False} if kind=='unknown_stock' else {'stock_taxable_income_per_share':D('10')}))
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.run_case((case,(changed,),bars,sessions,proofs))

    def test_integer_case_matches_old_validator_without_allocation_audit(self):
        fixture=self.fixture(integer=True);case,events,bars,sessions,proofs=fixture
        self.assertIs(old_reconcile(case,events,bars,sessions,20),True)
        self.assertIs(self.run_case(fixture),True);self.assertEqual(proofs,{})
        self.assertEqual(case['registry_allocation_audit'],[])

    def test_audit_quantity_choice_hash_clock_or_envelope_tamper_is_rejected(self):
        for key,value in [('registered_quantity',901),('registered_quantity',True),('chosen_integer_quantity',True),('chosen_integer_quantity',360),('chosen_integer_quantity',362),('registry_proof_sha256','b'*64),('as_of','2024-06-04T09:25:00+08:00'),('ratio_per_original_share','0.4'),('nominal_entitlement','361.0'),('candidates',[361]),('recorded','2024-06-02')]:
            fixture=self.fixture();fixture[0]['registry_allocation_audit'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.run_case(fixture)
        fixture=self.fixture();fixture[0]['registry_allocation_audit'][0]['envelope']['actual_registry_allocation_certified']=True
        with self.assertRaises(ValueError):self.run_case(fixture)

    def test_missing_duplicate_or_orphan_audit_and_proof_fail_closed(self):
        for kind in ('missing','duplicate','orphan_event','orphan_component','orphan_proof'):
            fixture=self.fixture();case,_,_,_,proofs=fixture
            if kind=='missing':case['registry_allocation_audit']=[]
            if kind=='duplicate':case['registry_allocation_audit'].append(copy.deepcopy(case['registry_allocation_audit'][0]))
            if kind=='orphan_event':case['registry_allocation_audit'][0]['event_id']='other'
            if kind=='orphan_component':case['registry_allocation_audit'][0]['component']='stock'
            if kind=='orphan_proof':proofs['other']=copy.deepcopy(proofs['synthetic'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_case(fixture)

    def test_tampered_fee_record_capital_payment_listing_T1_and_volume_rejected(self):
        for kind in ('fee','record','capital','payment','listing','T1','volume'):
            fixture=self.fixture();case,events,bars,sessions,_=fixture
            if kind=='fee':case['fills'][0]['cost']='23.01'
            if kind=='record':case['corporate_ledger'][0]['quantity']=901
            if kind=='capital':case['corporate_ledger'][1]['capital_shares']=362
            if kind=='payment':case['corporate_ledger'][2]['day']='2024-06-04'
            if kind=='listing':case['corporate_ledger'][3]['quantity']=362
            if kind=='T1':case['fills'][1]['execution_at']='2024-06-03T01:30:00+00:00'
            if kind=='volume':bars['SZ002831']['2024-06-06']['volume']='1'
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):self.run_case(fixture)

    def test_proof_event_ratio_dates_hash_or_availability_cannot_rebind_original_event(self):
        for key,value in [('issuer','SH600000'),('event_id','other'),('component','stock'),('record_date','2024-06-02'),('ex_date','2024-06-05'),('quoted_per10','4.019064'),('published_on','2024-05-27'),('source_sha256','bad'),('source_sha256','b'*64),('available_at','2024-06-04T10:00:00+08:00')]:
            fixture=self.fixture();fixture[-1]['synthetic']['capital'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_case(fixture)

if __name__=='__main__':unittest.main()
