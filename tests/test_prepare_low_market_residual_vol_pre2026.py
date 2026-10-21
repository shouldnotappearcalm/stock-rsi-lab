"""Source-preflight and external-plan failures must never form targets."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import prepare_low_market_residual_vol_pre2026 as m

class FormationEntryBoundaries(unittest.TestCase):
 def test_wrong_external_checksum_fails_before_source_access(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'request.json';p.write_text('{}');out=root/m.OUTPUT
   with patch.object(m,'authenticate',side_effect=AssertionError('source must not be read')) as auth:
    with self.assertRaises(ValueError):m.main(['--provider-uri',str(root/'absent'),'--request',str(p),'--expected-request-sha256','0'*64,'--output-dir',str(out)])
    auth.assert_not_called();self.assertFalse(out.exists())
 def test_source_preflight_does_not_form_or_write(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'request.json';p.write_text('{}');h=hashlib.sha256(p.read_bytes()).hexdigest();out=root/m.OUTPUT
   with patch.object(m,'authenticate',return_value=(object(),{})),patch.object(m,'build_targets',side_effect=AssertionError('no formation in source preflight')) as form:
    self.assertEqual(m.main(['--provider-uri',str(root/'source'),'--request',str(p),'--expected-request-sha256',h,'--output-dir',str(out),'--source-preflight-only']),0)
    form.assert_not_called();self.assertFalse(out.exists())
 def test_existing_output_is_preserved_before_source_authentication(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);out=root/m.OUTPUT;out.mkdir();(out/'evidence').write_text('original');p=root/'request.json';p.write_text('{}')
   with patch.object(m,'authenticate',side_effect=AssertionError('must not reenter sources')):
    with self.assertRaises(ValueError):m.main(['--provider-uri',str(root/'source'),'--request',str(p),'--expected-request-sha256',hashlib.sha256(p.read_bytes()).hexdigest(),'--output-dir',str(out)])
   self.assertEqual((out/'evidence').read_text(),'original')
if __name__=='__main__':unittest.main()
