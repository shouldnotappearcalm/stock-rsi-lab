import copy,unittest
from scripts.capture_value_momentum_primary_pre2026 import validate_scope

class FixedCompositePrimaryScopeTests(unittest.TestCase):
 def test_only_two_registered_original_2024_PDFs_can_be_fetched(self):
  r={'status':'FROZEN_VALUE_MOMENTUM_TWO_PRIMARY_ORIGINALS',
   'fresh_documents':[
    {'instrument':'SZ002508','day':'2024-01-03','url':'https://static.cninfo.com.cn/finalpage/2024-01-03/1218790856.PDF','file':'SZ002508-2024-01-03.pdf'},
    {'instrument':'SZ001389','day':'2024-04-01','url':'https://static.cninfo.com.cn/finalpage/2024-04-01/1219474753.PDF','file':'SZ001389-2024-04-01.pdf'}],
   'maximum_new_HTTP_reservations':2,'max_attempts_per_identity':1}
  validate_scope(r)
  for key,value in [('maximum_new_HTTP_reservations',3),('max_attempts_per_identity',2),('status','OTHER_CANDIDATE')]:
   v=copy.deepcopy(r);v[key]=value
   with self.assertRaises(ValueError):validate_scope(v)
  for key,value in [('day','2026-04-01'),('instrument','SZ002508'),('file','../escape.pdf'),('url','https://static.cninfo.com.cn/finalpage/2026-04-01/1219474753.PDF')]:
   v=copy.deepcopy(r);v['fresh_documents'][1][key]=value
   with self.assertRaises(ValueError):validate_scope(v)

if __name__=='__main__':unittest.main()
