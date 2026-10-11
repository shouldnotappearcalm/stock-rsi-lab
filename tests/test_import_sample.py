import importlib.util
import unittest
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'scripts/fetch_real_price_smoke.py'
if PATH.exists():
    spec=importlib.util.spec_from_file_location('sample_import',PATH)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
else:
    module=None


class SampleImportTests(unittest.TestCase):
    def test_raw_day_import_preserves_prices_and_marks_assumptions(self):
        self.assertIsNotNone(module,'real-price importer missing')
        body={'code':0,'data':{'sh600519':{'day':[['2024-01-02','1685.01','1685.01','1713','1678','32110']]}}}
        data=module.convert(body,'600519','2024-01-01','2024-03-31',{'source':'literal transport fixture'})
        self.assertEqual(data['records'][0]['payload']['close'],1685.01)
        self.assertEqual(data['records'][0]['payload']['volume_provider_raw'],'32110')
        self.assertEqual(data['evidence_level'],'REAL_PRICE_ENGINEERING_ONLY')
        self.assertIn('UNVERIFIED',data['provenance']['availability'])

    def test_adjusted_only_response_cannot_silently_replace_raw(self):
        self.assertIsNotNone(module,'real-price importer missing')
        with self.assertRaises(ValueError):
            module.convert({'code':0,'data':{'sh600519':{'qfqday':[['2024-01-02','1550','1550','1570','1540','32110']]}}},'600519','2024-01-01','2024-03-31',{})


if __name__=='__main__':unittest.main()
