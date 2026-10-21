import copy,unittest
from stock_rsi.data import digest
try:
 from stock_rsi.listing_anchor_source import project_primary_listing_anchor
except ImportError:project_primary_listing_anchor=None


class PrimaryListingAnchorTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(project_primary_listing_anchor)
  self.sessions=['2024-03-28','2024-03-29','2024-04-01','2024-04-02','2024-04-03']
  self.packet={'instrument':'SZ001389','bars':[{'date':d,'code':'sz.001389','preclose':'17.43'} for d in self.sessions[3:]],
   'distributions':[],'quarantine':[],'adjustments':[{'code':'sz.001389','dividOperateDate':'2024-04-02',
    'foreAdjustFactor':'0.98','backAdjustFactor':'1.000000','adjustFactor':'1.000000'}]}
  self.proof={'kind':'PRIMARY_LISTING_UNIT_ADJUSTMENT_ANCHOR','instrument':'SZ001389','listed_on':'2024-04-02',
   'issue_price':'17.43','verified_primary_listing':True,'source_file':'SZ001389-2024-04-01.pdf',
   'primary_document_sha256':'a'*64,'primary_listing_page':13,'primary_issue_price_page':29,
   'source_packet_digest':digest(self.packet),'initial_adjustment_row_sha256':digest(self.packet['adjustments'][0])}
 def run_projection(self):return project_primary_listing_anchor(self.packet,self.proof,self.sessions)
 def rebind(self):
  self.proof['source_packet_digest']=digest(self.packet)
  self.proof['initial_adjustment_row_sha256']=digest(self.packet['adjustments'][0])
 def test_primary_unit_anchor_keeps_original_bytes_and_creates_no_entitlement(self):
  original=copy.deepcopy((self.packet,self.proof));view,receipt=self.run_projection()
  self.assertEqual((self.packet,self.proof),original)
  self.assertEqual(view['bars'],self.packet['bars']);self.assertEqual(view['distributions'],[])
  self.assertEqual(view['adjustments'],[]);self.assertEqual(receipt['separated_anchor_row'],self.packet['adjustments'][0])
  self.assertEqual(receipt['prelisting_missing_sessions'],self.sessions[:3])
  self.assertFalse(receipt['entitlement_inferred']);self.assertFalse(receipt['zero_distribution_certified'])
 def test_primary_and_original_packet_binding_are_required(self):
  original=copy.deepcopy(self.proof)
  for key,value in [('verified_primary_listing',False),('instrument','SZ002508'),('source_packet_digest','b'*64),
   ('initial_adjustment_row_sha256','b'*64),('listed_on','2024-04-01'),('issue_price','18'),
   ('primary_document_sha256',''),('source_file','../notice.pdf'),('primary_listing_page',True)]:
   self.proof=copy.deepcopy(original);self.proof[key]=value
   with self.assertRaises(ValueError):self.run_projection()
 def test_nonunit_or_noninitial_anchors_and_unexplained_calendar_gaps_fail(self):
  original=copy.deepcopy((self.packet,self.proof))
  def nonunit():self.packet['adjustments'][0]['adjustFactor']='1.1'
  def later():self.packet['adjustments'][0]['dividOperateDate']='2024-04-03'
  def duplicate():self.packet['adjustments'].append(copy.deepcopy(self.packet['adjustments'][0]))
  def before_listing():self.packet['bars'].insert(0,{'date':'2024-04-01','preclose':'17.43'})
  def missing_after_listing():self.packet['bars'].pop()
  def first_day_cash():self.packet['distributions'].append({'dividOperateDate':'2024-04-02'})
  for mutate in (nonunit,later,duplicate,before_listing,missing_after_listing,first_day_cash):
   self.packet,self.proof=copy.deepcopy(original);mutate();self.rebind()
   with self.assertRaises(ValueError):self.run_projection()

if __name__=='__main__':unittest.main()
