import copy,importlib.util,struct
from pathlib import Path
import tempfile
import unittest

from stock_rsi import asset_expansion_horizon as signal
from tests import test_asset_expansion_horizon as fixtures


class HorizonTargetAuditTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-targets-audit.py'
        self.assertTrue(p.exists(),'separate horizon rank checker missing')
        spec=importlib.util.spec_from_file_location('separate_horizon_qa',p);self.qa=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.qa)
        self.f=fixtures.AssetExpansionHorizonTests().fixture();f=self.f
        targets,receipts=signal.build_targets(*f[:4],f[4].__getitem__,start='2026-01-05',end='2026-01-30')
        self.targets=self.qa.canonical({n:t['2026-01-05'] for n,t in targets.items()});self.receipt=self.qa.canonical(receipts[0])
        class Quotes:
            def value(self,code,field,day,*,as_of):
                if day!=as_of:raise AssertionError('native quote clock mismatch')
                return f[0].value(code,field,day)
        self.quotes=Quotes()

    def check(self,targets,receipt):
        f=self.f
        return self.qa.check_formation(targets,receipt,f[3]['2026-01-05'],f[4],f[2],f[1],self.quotes,
            '2026-01-05','2025-12-31')

    def test_independent_rational_ranks_and_all_receipts_match(self):self.check(self.targets,self.receipt)

    def test_weight_expansion_coverage_and_future_quote_receipt_are_rejected_without_hash_gate(self):
        for kind in ('weight','expansion','eligible','future'):
            t,r=copy.deepcopy(self.targets),copy.deepcopy(self.receipt)
            if kind=='weight':t[signal.PRIMARY]['weights'][self.f[2][0]]=.94
            elif kind=='expansion':r['ranked_source'][self.f[2][0]]['expansion_fraction']='999'
            elif kind=='eligible':r['eligible']=99
            else:r['latest_factor_price_read']='2026-01-05'
            with self.assertRaises(ValueError):self.check(t,r)

    def test_newly_failed_source_cannot_retain_its_old_rank(self):
        self.f[4]['1'].update(status='COVER_IDENTITY_UNVERIFIED',asset_report=None)
        with self.assertRaises(ValueError):self.check(self.targets,self.receipt)

    def test_native_scalar_reader_rejects_execution_day_and_reads_exact_prior_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'calendars').mkdir();(root/'calendars/day.txt').write_text('2025-12-31\n2026-01-05\n')
            p=root/'features/sh600001';p.mkdir(parents=True);(p/'close.day.bin').write_bytes(struct.pack('<3f',0.,2.,9999.))
            q=self.qa.NativeQuotes(root)
            self.assertEqual(q.value('SH600001','close','2025-12-31',as_of='2025-12-31'),2.)
            with self.assertRaises(ValueError):q.value('SH600001','close','2026-01-05',as_of='2025-12-31')


if __name__=='__main__':unittest.main()
