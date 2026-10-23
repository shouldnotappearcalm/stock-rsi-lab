import copy
import importlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


class RawHorizonInventoryTests(unittest.TestCase):
    def setUp(self):
        self.m = importlib.import_module('scripts.inventory_asset_expansion_raw_horizon')
        self.days = ['2023-12-29', '2024-01-02', '2026-10-20']
        self.code = 'SH600066'

    def packet(self, end=None):
        days = [d for d in self.days if d <= (end or self.days[-1])]
        bars = [dict(zip(self.m.BAR_FIELDS, [d, 'sh.600066', '10', '11', '9', '10.5',
                '10', '10000', '102000', '3', '1', '0'])) for d in days]
        div = {k: '' for k in self.m.DIVIDEND_FIELDS}
        div.update(code='sh.600066', dividOperateDate='2024-01-02', dividRegistDate='2023-12-29',
                   dividPayDate='2024-01-02', dividCashPsBeforeTax='0.1', dividStocksPs='0',
                   dividReserveToStockPs='0')
        adj = dict(zip(self.m.ADJUST_FIELDS, ['sh.600066', '2024-01-02', '0.99', '1.01', '1.01']))
        return {'instrument':self.code, 'window':[self.days[0], days[-1]], 'bars':bars,
                'distributions':[div], 'adjustments':[adj], 'quarantine':[]}

    def test_valid_prefix_and_numeric_formatting_compare_equal(self):
        old=self.packet('2024-01-02'); new=self.packet()
        new['bars'][0]['close']='10.500000'
        self.m.validate_packet(old,self.code,self.days[:2],old['window'])
        self.m.validate_packet(new,self.code,self.days,new['window'])
        self.assertEqual(self.m.compare_packets(old,new),[])

    def test_conflicts_include_market_state_cash_actions_and_adjustments(self):
        for field,key,value in [('bars','preclose','9'),('bars','isST','1'),
                                ('distributions','dividCashPsBeforeTax','9'),
                                ('adjustments','backAdjustFactor','9')]:
            a=self.packet(); b=copy.deepcopy(a); b[field][0][key]=value
            with self.subTest(field=field,key=key):
                conflicts=self.m.compare_packets(a,b)
                self.assertEqual(len(conflicts),1)
                self.assertEqual(conflicts[0]['field'],field)
                self.assertNotEqual(conflicts[0]['left_sha256'],conflicts[0]['right_sha256'])
        b=self.packet(); b['distributions']=[]
        self.assertTrue(self.m.compare_packets(self.packet(),b))

    def test_schema_and_clock_corruption_fail_closed(self):
        for mutate in [lambda p:p['bars'].pop(),
                       lambda p:p['bars'].append(p['bars'][-1]),
                       lambda p:p['bars'][0].update(close='NaN'),
                       lambda p:p['bars'][0].update(code='sh.600067'),
                       lambda p:p['bars'][0].update(adjustflag='2'),
                       lambda p:p['bars'][0].pop('preclose'),
                       lambda p:p['bars'][0].update(extra='ignored?'),
                       lambda p:p['bars'][0].update(date='2026-10-21'),
                       lambda p:p['distributions'][0].update(dividOperateDate='2026-10-21'),
                       lambda p:p['adjustments'][0].update(backAdjustFactor='0')]:
            p=self.packet(); mutate(p)
            with self.subTest(p=p),self.assertRaises((ValueError,KeyError)):
                self.m.validate_packet(p,self.code,self.days,[self.days[0],self.days[-1]])

    def test_distribution_operation_dates_are_ordered_unique_and_actual_sessions(self):
        original=self.packet()
        earlier=copy.deepcopy(original['distributions'][0]);earlier['dividOperateDate']='2023-12-29'
        for rows in ([original['distributions'][0],earlier],
                     [original['distributions'][0],{**original['distributions'][0],'dividCashPsBeforeTax':'0.10'}],
                     [{**original['distributions'][0],'dividOperateDate':'2024-01-03'}]):
            p=copy.deepcopy(original);p['distributions']=rows
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                self.m.validate_packet(p,self.code,self.days,p['window'])

    def fixture(self, root):
        names=['cache-raw-a','cache-raw-b']; entries=[]; manifests={}
        for name in names:
            d=root/name; (d/'codes').mkdir(parents=True)
            p=self.packet('2024-01-02' if name.endswith('a') else None)
            packet=d/'codes'/f'{self.code}.json';packet.write_text(json.dumps(p))
            calendar=d/'calendar.json';calendar.write_text(json.dumps({'sessions':[r['date'] for r in p['bars']]}))
            manifest=d/'manifest.json';manifest.write_text(json.dumps({'window':p['window'],
                'calendar_sha256':self.m.sha(calendar),'per_code_sha256':{self.code:self.m.sha(packet)}}))
            manifests[name]={'manifest_sha256':self.m.sha(manifest),'window':p['window']}
            entries.append({'cache':name,'manifest_window':p['window'],
                'packet_sha256_in_manifest':self.m.sha(packet),
                'actual_opaque_packet_sha256':self.m.sha(packet),'packet_present_and_byte_matched':True})
        return {'all47_dependency_candidates':{self.code:entries},'cache_manifests':manifests}

    def test_audit_retains_all_dependencies_and_selects_longest_identical_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inv=self.fixture(root)
            inv['all47_dependency_candidates']['SZ000001']=[]
            result=self.m.audit_inventory(inv,root)
            self.assertEqual(set(result['items']),{self.code,'SZ000001'})
            self.assertEqual(result['items'][self.code]['route']['cache'],'cache-raw-b')
            self.assertIsNone(result['items']['SZ000001']['route'])
            self.assertEqual(result['unresolved_codes'],['SZ000001'])
            self.assertFalse(result['source_admitted_for_replay'])

    def test_all_alternatives_conflicts_block_even_a_long_complete_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); inv=self.fixture(root)
            path=root/'cache-raw-a'/'codes'/f'{self.code}.json'
            p=json.loads(path.read_text());p['bars'][0]['isST']='1';path.write_text(json.dumps(p))
            self.rebind(inv,root,'cache-raw-a')
            result=self.m.audit_inventory(inv,root)
            self.assertIsNone(result['items'][self.code]['route'])
            self.assertTrue(result['items'][self.code]['conflicts'])

    def rebind(self,inv,root,name):
        d=root/name; manifest=json.loads((d/'manifest.json').read_text())
        manifest['per_code_sha256'][self.code]=self.m.sha(d/'codes'/f'{self.code}.json')
        manifest['calendar_sha256']=self.m.sha(d/'calendar.json')
        (d/'manifest.json').write_text(json.dumps(manifest))
        inv['cache_manifests'][name]['manifest_sha256']=self.m.sha(d/'manifest.json')
        row=next(r for r in inv['all47_dependency_candidates'][self.code] if r['cache']==name)
        row['actual_opaque_packet_sha256']=row['packet_sha256_in_manifest']=manifest['per_code_sha256'][self.code]

    def test_quarantine_and_calendar_conflict_block_reuse(self):
        for issue in ('quarantine','calendar'):
            with self.subTest(issue=issue),tempfile.TemporaryDirectory() as td:
                root=Path(td);inv=self.fixture(root);d=root/'cache-raw-a'
                if issue=='quarantine':
                    p=json.loads((d/'codes'/f'{self.code}.json').read_text())
                    p['quarantine']=[{'reason':'MISSING_OPERATE_DATE','record':{}}]
                    (d/'codes'/f'{self.code}.json').write_text(json.dumps(p))
                else:
                    (d/'calendar.json').write_text(json.dumps({'sessions':['2023-12-29','2024-01-03']}))
                self.rebind(inv,root,'cache-raw-a')
                result=self.m.audit_inventory(inv,root)
                self.assertIsNone(result['items'][self.code]['route'])
                self.assertIn(self.code,result['unresolved_codes'])
                if issue=='calendar':self.assertTrue(result['calendar_errors'])

    def test_original_hash_mismatch_rejected_before_packet_decoding(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inv=self.fixture(root)
            (root/'cache-raw-a'/'codes'/f'{self.code}.json').write_text('malformed changed source')
            result=self.m.audit_inventory(inv,root)
            self.assertIsNone(result['items'][self.code]['route'])
            self.assertIn('checksum',result['items'][self.code]['errors'][0]['error'])

    def test_interrupt_preserves_completed_identity_and_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);inv=self.fixture(root); inv['all47_dependency_candidates']['SZ000001']=[]
            seen=[]
            def completed(code,item):
                seen.append(code)
                if code==self.code:raise KeyboardInterrupt('synthetic interruption')
            with self.assertRaises(KeyboardInterrupt):self.m.audit_inventory(inv,root,on_complete=completed)
            self.assertEqual(seen,[self.code])


    def runner_fixture(self,root):
        repo=root/'repo';base=root/'source';base.mkdir();repo.mkdir()
        codes=['SH'+str(600001+i) for i in range(47)]
        inv={'all47_dependency_candidates':{c:[] for c in codes},'cache_manifests':{},'manifest_cache_count':13}
        local={}
        for i in range(13):
            name='fixture-raw-'+str(i);d=base/name;(d/'codes').mkdir(parents=True)
            hashes={}
            for code in codes if i==0 else codes[:1]:
                p=self.packet();p['instrument']=code
                for field in ('bars','distributions','adjustments'):
                    for row in p[field]:row['code']=self.m.issuer(code)
                path=d/'codes'/(code+'.json');path.write_text(json.dumps(p));h=self.m.sha(path)
                hashes[code]=h;local[str(path.relative_to(base))]=h
                inv['all47_dependency_candidates'][code].append({'cache':name,'manifest_window':p['window'],
                    'packet_sha256_in_manifest':h,'actual_opaque_packet_sha256':h,'packet_present_and_byte_matched':True})
            (d/'calendar.json').write_text(json.dumps({'sessions':self.days}))
            (d/'manifest.json').write_text(json.dumps({'window':[self.days[0],self.days[-1]],
                'calendar_sha256':self.m.sha(d/'calendar.json'),'per_code_sha256':hashes}))
            inv['cache_manifests'][name]={'manifest_sha256':self.m.sha(d/'manifest.json'),
                'window':[self.days[0],self.days[-1]]}
            for f in ('manifest.json','calendar.json'):local[name+'/'+f]=self.m.sha(d/f)
        data={self.m.INVENTORY:inv,self.m.TARGET:{self.m.CANDIDATE:{str(i):{'weights':{c:1/47 for c in codes}} for i in range(34)}},
            self.m.SUMMARY:{'primary_target_union':codes,'completed_formations':34},self.m.PLAN:'synthetic test plan'}
        for name,value in data.items():
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
        audit={'formations_checked':34,'pre2026_full_target_receipt_parity':24,'summary_sha256':self.m.sha(repo/self.m.SUMMARY)}
        (repo/self.m.AUDIT).write_text(json.dumps(audit))
        for name in self.m.METHODS:
            path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic method evidence')
        r={'status':'FROZEN_ASSET_EXPANSION_ALL47_RAW_OVERLAP_CHECK','window':[self.m.START,self.m.END],
            'network_query_budget':0,'output_directory':'asset-expansion-raw-overlap-20261023',
            'strategy_changes_allowed':False,'portfolio_returns_to_compute':False,'codes':codes,
            'method_sha256':{n:self.m.sha(repo/n) for n in self.m.METHODS},
            'public_evidence_sha256':{n:self.m.sha(repo/n) for n in data|{self.m.AUDIT:audit}},'local_source_sha256':local}
        request=root/'request.json';request.write_text(json.dumps(r))
        return request,self.m.sha(request),repo,base,base/r['output_directory']

    def test_frozen_runner_retains_all47_items_and_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.runner_fixture(Path(td));result=self.m.execute(*args);out=args[-1]
            self.assertEqual(len(result['completed_codes']),47)
            self.assertEqual(result['pending_codes'],[])
            self.assertTrue(result['input_postcheck']['all_inputs_unchanged'])
            self.assertEqual(result['unresolved_codes'],[])
            self.assertEqual(len(list((out/'items').glob('*.json'))),47)
            self.assertFalse(result['portfolio_returns_computed'])
            with self.assertRaises(ValueError):self.m.execute(*args)

    def test_frozen_runner_refuses_changed_original_before_decoding(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.runner_fixture(Path(td));(args[3]/'fixture-raw-0/codes/SH600001.json').write_text('changed malformed')
            with self.assertRaisesRegex(ValueError,'frozen method/source bytes changed'):self.m.execute(*args)
            self.assertFalse(args[-1].exists())

    def test_interrupted_runner_keeps_original_exception_and_pending_items(self):
        with tempfile.TemporaryDirectory() as td:
            args=self.runner_fixture(Path(td));original=self.m.save
            def interrupted(path,value):
                if path.name=='SH600002.json':raise KeyboardInterrupt('synthetic stop')
                return original(path,value)
            with patch.object(self.m,'save',side_effect=interrupted),self.assertRaises(KeyboardInterrupt):self.m.execute(*args)
            terminal=json.loads((args[-1]/'terminal.json').read_text())
            self.assertEqual(terminal['completed_codes'],['SH600001'])
            self.assertEqual(len(terminal['pending_codes']),46)
            self.assertEqual(terminal['original_error']['error_type'],'KeyboardInterrupt')
            self.assertTrue((args[-1]/'items/SH600001.json').is_file())

    def test_posthash_and_summary_write_failures_are_retained(self):
        for issue in ('mutation','summary'):
            with self.subTest(issue=issue),tempfile.TemporaryDirectory() as td:
                args=self.runner_fixture(Path(td));original=self.m.save
                def failing(path,value):
                    if issue=='summary' and path.name=='summary.json':
                        path.write_text('{partial')
                        raise OSError('synthetic disk error after partial write')
                    result=original(path,value)
                    if issue=='mutation' and path.name=='SH600001.json':
                        (args[3]/'fixture-raw-0/codes/SH600001.json').write_text('mutated after read')
                    return result
                with patch.object(self.m,'save',side_effect=failing),self.assertRaises(ValueError):self.m.execute(*args)
                terminal=json.loads((args[-1]/'terminal.json').read_text())
                if issue=='mutation':self.assertFalse(terminal['input_postcheck']['all_inputs_unchanged'])
                else:
                    self.assertFalse(terminal['summary_persisted'])
                    self.assertEqual(terminal['persistence_errors'][0]['file'],'summary.json')


if __name__=='__main__':unittest.main()
