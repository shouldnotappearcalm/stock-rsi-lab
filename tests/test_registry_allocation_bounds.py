"""Synthetic metadata/Fraction tests, without files, market sources or accounts."""
import copy
import importlib
import unittest
from fractions import Fraction

class RegistryAllocationBoundsTests(unittest.TestCase):
    def api(self):return importlib.import_module('stock_rsi.registry_allocation_bounds')
    def proof(self):
        return {'contract':'PRIMARY_LARGEST_REMAINDER_LOCAL_ENVELOPE_V1',
                'issuer':'SZ002831','event_id':'synthetic-capital-event',
                'record_date':'2024-06-03','ex_date':'2024-06-04','component':'capital',
                'source_file':'synthetic-original.pdf','source_sha256':'a'*64,
                'published_on':'2024-05-28','available_at':'2024-05-29T00:00:00+08:00',
                'actual_arrival_verified':False,'eligible_count':10000000,
                'declared_total_shares':4019063,'quoted_per10':'4.019063',
                'fraction_method':'LARGEST_REMAINDER_DESC_RANDOM_TIES',
                'quoted_precision_bound':'ONE_LAST_DIGIT_SYMMETRIC_ENGINEERING_ASSUMPTION'}
    def run_bounds(self,proof=None,q=900,as_of='2024-06-04T09:25:00+08:00'):
        return self.api().allocation_bounds(self.proof() if proof is None else proof,q,as_of=as_of)
    def fraction(self,pair):return Fraction(int(pair[0]),int(pair[1]))

    def test_900_entire_registered_account_two_candidates_and_exact_math(self):
        result=self.run_bounds();self.assertEqual(result['possible_integer_shares'],[361,362])
        self.assertEqual(self.fraction(result['lower_ratio']),Fraction(4019062,10000000))
        self.assertEqual(self.fraction(result['upper_ratio']),Fraction(4019064,10000000))
        self.assertEqual(self.fraction(result['exact_total_ratio_entitlement']),Fraction(36171567,100000))
        self.assertEqual(self.fraction(result['lower_entitlement']),Fraction(18085779,50000))
        self.assertEqual(self.fraction(result['upper_entitlement']),Fraction(4521447,12500))
        self.assertEqual(result['candidate_reason'],'ALL_INTEGERS_FROM_FLOOR_LOWER_TO_CEIL_UPPER_ENTIRE_REGISTERED_ACCOUNT')
        for k in ('actual_registry_allocation_certified','probabilities_certified','globally_jointly_feasible','portfolio_return_ordering_claimed'):
            self.assertIs(result[k],False)

    def test_zero_quantity_and_integer_exact_total_do_not_hide_display_uncertainty(self):
        self.assertEqual(self.run_bounds(q=0)['possible_integer_shares'],[0])
        p=self.proof();p.update(quoted_per10='4.000000',declared_total_shares=4000000)
        result=self.run_bounds(p,q=1000)
        self.assertEqual(self.fraction(result['exact_total_ratio_entitlement']),400)
        self.assertEqual(result['possible_integer_shares'],[399,400,401])

    def test_aggregate_ratio_within_display_envelope_need_not_equal_display_literal(self):
        p=self.proof();p.update(eligible_count=100000000,declared_total_shares=40190635)
        result=self.run_bounds(p)
        self.assertEqual(self.fraction(result['exact_total_ratio_minus_quoted_ratio']),Fraction(1,20000000))
        self.assertEqual(result['possible_integer_shares'],[361,362])
        for total in (40190620,40190640):
            p['declared_total_shares']=total;self.assertEqual(self.run_bounds(p)['possible_integer_shares'],[361,362])
        for total in (40190619,40190641):
            p['declared_total_shares']=total
            with self.subTest(total=total),self.assertRaises(ValueError):self.run_bounds(p)

    def test_exact_schema_boolean_counts_and_quantities_rejected(self):
        for key,value in [('eligible_count',True),('eligible_count',0),('eligible_count',100.0),
                          ('declared_total_shares',False),('declared_total_shares',0),
                          ('component','cash'),('actual_arrival_verified',True),('actual_arrival_verified',0),
                          ('fraction_method','ROUND_DOWN'),('quoted_precision_bound','CERTIFIED'),('contract','OTHER')]:
            p=self.proof();p[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.run_bounds(p)
        for q in (True,-1,10000001,1.0,'900',None):
            with self.subTest(q=q),self.assertRaises(ValueError):self.run_bounds(q=q)
        p=self.proof();p['extra_rule']='override'
        with self.assertRaises(ValueError):self.run_bounds(p)
        p=self.proof();del p['source_sha256']
        with self.assertRaises(ValueError):self.run_bounds(p)

    def test_per10_canonical_positive_decimal_and_exact_precision_budget(self):
        for text in ('NaN','Infinity','1e-6','+4.019063','04.019063','4.',' 4.019063','0','-1',4.019063):
            p=self.proof();p['quoted_per10']=text
            with self.subTest(text=text),self.assertRaises(ValueError):self.run_bounds(p)
        p=self.proof();p.update(quoted_per10='4',declared_total_shares=4000000)
        with self.assertRaisesRegex(ValueError,'three'):self.run_bounds(p,q=100)
        self.assertEqual(self.run_bounds(p,q=10)['possible_integer_shares'],[3,4,5])

    def test_document_identity_dates_and_future_availability_fail_closed(self):
        cases=[('issuer','sz002831'),('issuer','US123456'),('event_id',''),('source_file','../issuer.pdf'),
               ('source_file','/issuer.pdf'),('source_file','dir\\issuer.pdf'),('source_sha256','a'*63),
               ('record_date','2024-6-03'),('record_date','2024-06-04'),('published_on','2024-06-04'),
               ('available_at','2024-05-27T00:00:00+08:00'),('available_at','2024-06-04T10:00:00+08:00'),
               ('available_at','2024-05-29T00:00:00')]
        for key,value in cases:
            p=self.proof();p[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.run_bounds(p)
        with self.assertRaises(ValueError):self.run_bounds(as_of='2024-06-04T09:25:00')

    def test_no_mutation_determinism_provenance_and_stock_component(self):
        p=self.proof();p['component']='stock';before=copy.deepcopy(p)
        first=self.run_bounds(p);second=self.run_bounds(copy.deepcopy(p))
        self.assertEqual(first,second);self.assertEqual(p,before)
        self.assertEqual(first['proof'],p);self.assertEqual(first['registered_quantity'],900)
        self.assertEqual(len(first['proof_sha256']),64)
        self.assertEqual(first['rounding_scope'],'ENTIRE_REGISTERED_ACCOUNT_NOT_FIFO_LOTS')
        first['proof']['issuer']='SH600000';self.assertEqual(p,before)

    def test_impossible_global_quantity_upper_bound_rejects_without_clipping(self):
        p=self.proof()
        with self.assertRaises(ValueError):self.run_bounds(p,q=p['eligible_count'])
        p.update(eligible_count=10,declared_total_shares=4,quoted_per10='4')
        with self.assertRaisesRegex(ValueError,'declared total'):self.run_bounds(p,q=10)

if __name__=='__main__':unittest.main()
