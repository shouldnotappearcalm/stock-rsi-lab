"""Read-only, bounded raw-source overlap gate; no policy, account or network."""
import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from itertools import combinations
from pathlib import Path

START, END = '2023-12-29', '2026-10-21'
CANDIDATE = 'low_asset_expansion_decile_conditional'
INVENTORY = 'experiments/qlib/asset-expansion-2026-raw-cache-inventory.json'
TARGET = 'experiments/qlib/asset-expansion-2026-targets.json'
SUMMARY = 'experiments/qlib/asset-expansion-2026-targets-results.json'
AUDIT = 'experiments/qlib/asset-expansion-2026-targets-source-audit.json'
PLAN = 'docs/research/asset-expansion-2026-raw-overlap-plan-2026-10-23.md'
METHODS = ('scripts/inventory_asset_expansion_raw_horizon.py',
           'tests/test_asset_expansion_raw_horizon_inventory.py')
BAR_FIELDS = ('date','code','open','high','low','close','preclose','volume','amount','adjustflag','tradestatus','isST')
DIVIDEND_FIELDS = ('code','dividPreNoticeDate','dividAgmPumDate','dividPlanAnnounceDate','dividPlanDate',
    'dividRegistDate','dividOperateDate','dividPayDate','dividStockMarketDate','dividCashPsBeforeTax',
    'dividCashPsAfterTax','dividStocksPs','dividCashStock','dividReserveToStockPs')
ADJUST_FIELDS = ('code','dividOperateDate','foreAdjustFactor','backAdjustFactor','adjustFactor')
NUMERICS = {'bars': ('open','high','low','close','preclose','volume','amount'),
    'distributions': ('dividCashPsBeforeTax','dividCashPsAfterTax','dividStocksPs','dividReserveToStockPs'),
    'adjustments': ADJUST_FIELDS[2:]}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''): h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value,f,ensure_ascii=False,indent=2); f.write('\n')


def relative(root, name):
    if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('safe relative source path required')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()): raise ValueError('source path escaped root')
    return path


def day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
        raise ValueError('canonical source date required')
    return value


def number(value):
    if not isinstance(value,str): raise ValueError('original numeric string required')
    try: n = Decimal(value)
    except InvalidOperation as exc: raise ValueError('numeric source field required') from exc
    if not n.is_finite(): raise ValueError('finite source amount required')
    return n


def issuer(code):
    if (not isinstance(code,str) or len(code)!=8 or not code[2:].isdigit()
            or not code.startswith(('SH600','SH601','SH603','SH605','SZ000','SZ001','SZ002','SZ003'))):
        raise ValueError('ordinary-board issuer required')
    return code[:2].lower()+'.'+code[2:]


def canonical(row, field):
    result = dict(row)
    for k in NUMERICS[field]:
        if result[k]!='':
            f = Fraction(number(result[k])); result[k] = [f.numerator,f.denominator]
    return result


def validate_packet(packet, code, sessions, window):
    symbol = issuer(code)
    if (packet['instrument']!=code or packet['window']!=window or len(window)!=2
            or not START<=day(window[0])<=day(window[1])<=END):
        raise ValueError('bounded original issuer/window required')
    if (not sessions or sessions!=sorted(set(sessions)) or sessions[0]!=window[0]
            or sessions[-1]!=window[1] or any(not window[0]<=day(d)<=window[1] for d in sessions)):
        raise ValueError('complete explicit ordered source calendar required')
    for field, fields, atkey in (('bars',BAR_FIELDS,'date'),
            ('distributions',DIVIDEND_FIELDS,'dividOperateDate'),('adjustments',ADJUST_FIELDS,'dividOperateDate')):
        if not isinstance(packet[field],list): raise ValueError('original row list required')
        identities=set()
        for row in packet[field]:
            if (not isinstance(row,dict) or set(row)!=set(fields)
                    or any(not isinstance(v,str) for v in row.values())):
                raise ValueError('exact original '+field+' schema required')
            if row['code']!=symbol or not window[0]<=day(row[atkey])<=window[1]:
                raise ValueError('source issuer or cutoff changed')
            identity=digest(canonical(row,field))
            if identity in identities: raise ValueError('duplicate source record')
            identities.add(identity)
            for k in NUMERICS[field]:
                if row[k] and number(row[k])<0: raise ValueError('negative source amount')
            if field=='bars':
                if row['adjustflag']!='3' or row['tradestatus'] not in ('0','1') or row['isST'] not in ('0','1'):
                    raise ValueError('unadjusted/historical state identity changed')
                if row['tradestatus']=='1':
                    for k in ('open','high','low','close','preclose','volume'):
                        if not row[k] or number(row[k])<=0: raise ValueError('positive trading quote/volume required')
                    if (number(row['high'])<max(number(row['open']),number(row['close']))
                            or number(row['low'])>min(number(row['open']),number(row['close']))
                            or number(row['high'])<number(row['low'])):
                        raise ValueError('OHLC bounds inconsistent')
            elif field=='adjustments':
                if any(not row[k] or number(row[k])<=0 for k in ADJUST_FIELDS[2:]):
                    raise ValueError('positive adjustment factors required')
            else:
                for k in DIVIDEND_FIELDS[1:9]:
                    if row[k]: day(row[k])
        dates=[r[atkey] for r in packet[field]]
        if dates!=sorted(set(dates)): raise ValueError('ordered unique source dates required')
        if any(d not in sessions for d in dates): raise ValueError('source operation must be an explicit exchange session')
    if [r['date'] for r in packet['bars']]!=sessions: raise ValueError('one raw bar per explicit session required')
    if not isinstance(packet['quarantine'],list): raise ValueError('retained quarantine list required')
    for r in packet['quarantine']:
        if not isinstance(r,dict) or not isinstance(r.get('reason'),str) or not isinstance(r.get('record'),dict):
            raise ValueError('retained quarantine record identity required')


def compare_packets(left, right):
    lo=max(left['window'][0],right['window'][0]); hi=min(left['window'][1],right['window'][1])
    conflicts=[]
    for field, key in (('bars','date'),('distributions','dividOperateDate'),('adjustments','dividOperateDate')):
        groups=[]
        for p in (left,right):
            byday={}
            for row in p[field]:
                if lo<=row[key]<=hi: byday.setdefault(row[key],[]).append(canonical(row,field))
            groups.append({d:sorted(digest(r) for r in rows) for d,rows in byday.items()})
        a,b=groups
        for d in sorted(set(a)|set(b)):
            if a.get(d,[])!=b.get(d,[]):
                conflicts.append({'field':field,'date':d,'left_sha256':digest(a.get(d,[])),
                    'right_sha256':digest(b.get(d,[])),'left_rows':len(a.get(d,[])),
                    'right_rows':len(b.get(d,[])),'comparison_window':[lo,hi]})
    return conflicts


def audit_inventory(inventory, base, on_complete=None):
    calendars={}; manifests={}; calendar_errors=[]
    for name,item in sorted(inventory['cache_manifests'].items()):
        try:
            directory=relative(base,name); mpath=directory/'manifest.json'
            if sha(mpath)!=item['manifest_sha256']: raise ValueError('manifest checksum changed')
            m=read(mpath); cpath=directory/'calendar.json'; sessions=read(cpath)['sessions']
            if sha(cpath)!=m['calendar_sha256']: raise ValueError('calendar checksum changed')
            w=m['window']
            if (w!=item['window'] or w[0]!=START or not START<=day(w[1])<=END
                    or not sessions or sessions!=sorted(set(sessions))
                    or [sessions[0],sessions[-1]]!=w or any(not w[0]<=day(d)<=w[1] for d in sessions)):
                raise ValueError('bounded complete explicit calendar required')
            manifests[name]=m; calendars[name]=sessions
        except Exception as exc:
            calendar_errors.append({'cache':name,'error_type':type(exc).__name__,'error':str(exc)})
    for a,b in combinations(sorted(calendars),2):
        hi=min(calendars[a][-1],calendars[b][-1])
        if [d for d in calendars[a] if d<=hi]!=[d for d in calendars[b] if d<=hi]:
            calendar_errors.append({'caches':[a,b],'error':'overlapping source calendars disagree','through':hi})
    items={}
    for code,candidates in sorted(inventory['all47_dependency_candidates'].items()):
        errors=[]; conflicts=[]; choices=[]; packets={}
        for candidate in candidates:
            name=candidate['cache']
            try:
                if name in packets: raise ValueError('duplicate candidate cache')
                m=manifests[name]; expected=m['per_code_sha256'][code]
                path=relative(base,name)/'codes'/(code+'.json')
                if (not candidate['packet_present_and_byte_matched'] or not isinstance(expected,str)
                        or sha(path)!=expected or expected!=candidate['actual_opaque_packet_sha256']
                        or expected!=candidate['packet_sha256_in_manifest']):
                    raise ValueError('original packet checksum changed')
                packet=read(path)
                if candidate['manifest_window']!=m['window']: raise ValueError('candidate window changed')
                validate_packet(packet,code,calendars[name],m['window'])
                packets[name]=packet
                choices.append({'cache':name,'packet_sha256':expected,'window':packet['window'],
                    'bar_rows':len(packet['bars']),'distribution_rows':len(packet['distributions']),
                    'adjustment_rows':len(packet['adjustments']),'quarantine_rows':len(packet['quarantine']),
                    'quarantine_sha256':digest(packet['quarantine'])})
            except Exception as exc:
                errors.append({'cache':name,'error_type':type(exc).__name__,'error':str(exc)})
        for a,b in combinations(sorted(packets),2):
            conflicts.extend({'left_cache':a,'right_cache':b,**r} for r in compare_packets(packets[a],packets[b]))
        unresolved_quarantine=any(p['quarantine'] for p in packets.values())
        route=None
        if choices and not (errors or conflicts or calendar_errors or unresolved_quarantine):
            route=sorted(choices,key=lambda r:(-date.fromisoformat(r['window'][1]).toordinal(),r['cache']))[0]
        item={'choices':choices,'errors':errors,'conflicts':conflicts,
              'unresolved_quarantine':unresolved_quarantine,'route':route,'source_admitted_for_replay':False}
        items[code]=item
        if on_complete is not None: on_complete(code,item)
    return {'status':'RAW_OVERLAP_CHECK_COMPLETE_NOT_SOURCE_ADMISSION','items':items,
        'calendar_errors':calendar_errors,'unresolved_codes':sorted(c for c,r in items.items() if r['route'] is None),
        'source_admitted_for_replay':False,'corporate_action_completeness_verified':False,
        'historical_arrival_verified':False,'network_queries':0,'strategy_or_targets_changed':False,
        'portfolio_returns_computed':False,'objective_achieved':False}


def authenticate(request, expected, repo, base):
    if sha(request)!=expected: raise ValueError('frozen source overlap request checksum changed')
    r=read(request)
    if (r['status']!='FROZEN_ASSET_EXPANSION_ALL47_RAW_OVERLAP_CHECK'
            or r['window']!=[START,END] or r['network_query_budget']!=0
            or r['output_directory']!='asset-expansion-raw-overlap-20261023'
            or r['strategy_changes_allowed'] is not False or r['portfolio_returns_to_compute'] is not False
            or set(r['method_sha256'])!=set(METHODS)
            or set(r['public_evidence_sha256'])!={INVENTORY,TARGET,SUMMARY,AUDIT,PLAN}):
        raise ValueError('frozen bounded overlap protocol required')
    inputs={str(Path(request).resolve()):expected}
    for field,root in (('method_sha256',repo),('public_evidence_sha256',repo),('local_source_sha256',base)):
        for name,h in r[field].items():
            path=relative(root,name)
            if sha(path)!=h: raise ValueError('frozen method/source bytes changed: '+name)
            inputs[str(path)]=h
    inventory=read(repo/INVENTORY); targets=read(repo/TARGET)[CANDIDATE]; summary=read(repo/SUMMARY); audit=read(repo/AUDIT)
    codes=sorted({c for row in targets.values() for c in row['weights']})
    if (codes!=r['codes'] or len(codes)!=47 or len(targets)!=34
            or sorted(inventory['all47_dependency_candidates'])!=codes or inventory['manifest_cache_count']!=13
            or summary['primary_target_union']!=codes or summary['completed_formations']!=34
            or audit['formations_checked']!=34 or audit['pre2026_full_target_receipt_parity']!=24
            or audit['summary_sha256']!=sha(repo/SUMMARY)):
        raise ValueError('complete unchanged audited34formation47name scope required')
    wanted={}
    for name,item in inventory['cache_manifests'].items():
        wanted[name+'/manifest.json']=item['manifest_sha256']
        wanted[name+'/calendar.json']=r['local_source_sha256'][name+'/calendar.json']
    for code,candidates in inventory['all47_dependency_candidates'].items():
        for c in candidates:
            if not c['packet_present_and_byte_matched']: raise ValueError('original inventory missing packet')
            wanted[c['cache']+'/codes/'+code+'.json']=c['actual_opaque_packet_sha256']
    if wanted!=r['local_source_sha256']: raise ValueError('all original alternatives and only bound originals required')
    return r,inventory,inputs


def execute(request,expected,repo,base,out):
    if out.exists(): raise ValueError('preserve original output; no overwrite or automatic resume')
    r,inventory,inputs=authenticate(request,expected,repo,base)
    if out.resolve()!=(base/r['output_directory']).resolve(): raise ValueError('fixed fresh output required')
    (out/'items').mkdir(parents=True); (out/'request.json').write_bytes(Path(request).read_bytes())
    save(out/'inputs-before.json',inputs); completed=[]; result=None; error=None; original=None
    def completed_item(code,item):
        save(out/'items'/(code+'.json'),item); completed.append(code)
        print('raw overlap',len(completed),'/',len(r['codes']),code,'unresolved',item['route'] is None,flush=True)
    try:
        result=audit_inventory(inventory,base,on_complete=completed_item)
    except BaseException as exc:
        original=exc; error={'error_type':type(exc).__name__,'error':str(exc)}
    changes=[]
    for name,h in inputs.items():
        try:
            if sha(name)!=h: changes.append(name)
        except Exception: changes.append(name)
    post={'all_inputs_unchanged':not changes,'changed_or_missing':changes,'consumed_file_count':len(inputs)}
    persistence=[]
    try: save(out/'inputs-after.json',post)
    except BaseException as exc: persistence.append({'file':'inputs-after.json','error_type':type(exc).__name__,'error':str(exc)})
    summary={**(result or {}),'status':('RAW_OVERLAP_CHECK_COMPLETE_NOT_SOURCE_ADMISSION' if
        result is not None and not error and not changes and not persistence else 'INCOMPLETE_RAW_OVERLAP_RETAINED'),
        'request_sha256':expected,'completed_codes':completed,'pending_codes':sorted(set(r['codes'])-set(completed)),
        'original_error':error,'input_postcheck':post,'persistence_errors':persistence}
    summary_persisted=False
    try:
        save(out/'summary.json',summary)
        summary_persisted=True
    except BaseException as exc: persistence.append({'file':'summary.json','error_type':type(exc).__name__,'error':str(exc)})
    terminal={'request_sha256':expected,'completed_codes':completed,'pending_codes':summary['pending_codes'],
        'original_error':error,'input_postcheck':post,'persistence_errors':persistence,
        'summary_persisted':summary_persisted,'source_admitted_for_replay':False}
    save(out/'terminal.json',terminal)
    if original is not None: raise original
    if changes or persistence: raise ValueError('source mutation or finalization error retained')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ('request','expected-request-sha256','source-root','output-dir'): p.add_argument('--'+name,required=True)
    a=p.parse_args(argv); repo=Path(__file__).resolve().parents[1]
    result=execute(Path(a.request),a.expected_request_sha256,repo,Path(a.source_root),Path(a.output_dir))
    print('raw overlap complete',len(result['completed_codes']),'unresolved',len(result['unresolved_codes']),
          'calendar errors',len(result['calendar_errors']),'no network/account returns',flush=True)
    return 0 if not result['unresolved_codes'] else 2


if __name__=='__main__': raise SystemExit(main())
