import copy
import importlib.util
import unittest
from pathlib import Path


class SeparateReconstructionAuditTests(unittest.TestCase):
    def setUp(self):
        p=Path(__file__).resolve().parents[1]/'experiments/qlib/audit_sources/2026-10-23-asset-expansion-source-reconstruction-audit.py'
        s=importlib.util.spec_from_file_location('separate_source_audit',p);self.m=importlib.util.module_from_spec(s);s.loader.exec_module(self.m)
        self.days=['2023-12-29','2026-03-30','2026-03-31']
        self.old={'instrument':'SH603056','window':['2023-12-29','2026-03-30'],
            'bars':[self.bar(d) for d in self.days[:2]],'distributions':[],'adjustments':[],'quarantine':[]}
        self.observed={'daily':{'fields':list(self.m.BAR),'rows':[list(self.bar(self.days[-1]).values())]},
            'dividend2026':{'fields':list(self.m.DIV),'rows':[]},'adjustments':{'fields':list(self.m.ADJ),'rows':[]}}
        self.actual=copy.deepcopy(self.old);self.actual['window'][-1]='2026-03-31';self.actual['bars'].append(self.bar(self.days[-1]))

    def bar(self,d):
        return dict(zip(self.m.BAR,[d,'sh.603056','10','11','9','10.5','10','10000','102000','3','1','0']))

    def test_independent_full_source_composition_and_coverage(self):
        c=self.m.check_packet(self.actual,self.old,self.observed,self.days)
        self.assertEqual(c,{'active_source_sessions':3,'active_end':'2026-03-31',
            'global_session_count':3,'post_exit_sessions_not_synthesized':0})

    def test_exit_window_requires_all_active_rows_and_never_synthesizes_quote(self):
        d=copy.deepcopy(self.observed);d['daily']['rows']=[]
        proof={'effective_date':'2026-03-31','primary_document_sha256':'a'*64}
        c=self.m.check_packet(self.old,self.old,d,self.days,proof)
        self.assertEqual(c['post_exit_sessions_not_synthesized'],1)
        broken=copy.deepcopy(self.old);broken['bars'].pop()
        with self.assertRaises(ValueError):self.m.check_packet(broken,self.old,d,self.days,proof)
        with self.assertRaises(ValueError):self.m.check_packet(self.actual,self.old,self.observed,self.days,proof)

    def test_semantic_mutations_rejected_without_file_hash_checks(self):
        for mutate in (lambda p:p['bars'][0].update(isST='1'),lambda p:p['bars'][-1].update(close='9'),
                       lambda p:p['bars'].append(p['bars'][-1]),lambda p:p.update(quarantine=[{'unresolved':True}])):
            p=copy.deepcopy(self.actual);mutate(p)
            with self.subTest(packet=p),self.assertRaises(ValueError):self.m.check_packet(p,self.old,self.observed,self.days)

    def test_numeric_source_overlap_and_after_tax_literals_are_separate(self):
        old=copy.deepcopy(self.old);a=copy.deepcopy(self.actual);d=copy.deepcopy(self.observed)
        r={k:'' for k in self.m.DIV};r.update(code='sh.603056',dividOperateDate='2026-03-30',
            dividCashPsBeforeTax='0.1',dividCashPsAfterTax='0.09或0.1',dividStocksPs='0',dividReserveToStockPs='0')
        old['distributions']=[r];a['distributions']=copy.deepcopy(old['distributions'])
        new={**r,'dividCashPsBeforeTax':'0.1000'};d['dividend2026']['rows']=[[new[k] for k in self.m.DIV]]
        self.m.check_packet(a,old,d,self.days)
        d['dividend2026']['rows'][0][10]='0.090或0.1'
        with self.assertRaises(ValueError):self.m.check_packet(a,old,d,self.days)


if __name__=='__main__':unittest.main()
