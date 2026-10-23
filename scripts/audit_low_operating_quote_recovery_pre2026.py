"""Reconstruct the frozen source probe from integer bits, without producer imports."""
import argparse
from datetime import date
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
from scripts.immutable_http_capture import need,file_sha as sha
from scripts.audit_low_operating_raw_pre2026 import resolve

START,END='2023-12-29','2025-12-31'
RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
HTTP='low-operating-http-tax-sources-pre2026-v1-20261023'
PREFIX='experiments/qlib/'
PROOF=PREFIX+'low-operating-http-tax-source-independent-check.json'
PROOF_SHA='90f1c955777627b4284822a37bbc126b4385dd3f6f7d481155397e4df73383e2'
HTTP_REQUEST=PREFIX+'low-operating-http-tax-source-request.json'
OPERATING=PREFIX+'operating-profitability-pre2026-request.json'
OPERATING_SHA='7fedda231ca66593d9b1bfcf1c05f11f670fcc9ca18605c132f630885c65818c'
TARGET=PREFIX+'operating-profitability-pre2026-targets.json'
TARGET_SHA='d56de5a1fcce5e404b7a795f75fa92cfd5197a95e1d5a2a017b41caed3cc4dfa'
FAMILY='operating_profit_prior_assets_bottom_decile_control'
FIELDS=('open','high','low','close','factor','volume')
METHODS=('src/stock_rsi/float32_quote_bounds.py','scripts/recover_low_operating_quotes_pre2026.py',
    'scripts/audit_low_operating_quote_recovery_pre2026.py','tests/test_low_operating_quote_recovery.py','scripts/immutable_http_capture.py')
PUBLIC=('docs/research/low-operating-float32-source-design-2026-10-23.md',
    'docs/superpowers/plans/2026-10-23-low-operating-float32-sources.md',PREFIX+'low-operating-f32-source-review.json')
GUARD=Fraction(1,2**40)

def read(p):return json.loads(Path(p).read_text())
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def text(q):return str(q.numerator)+'/'+str(q.denominator)
def floor(q):return q.numerator//q.denominator
def ceil(q):return -((-q.numerator)//q.denominator)


def rational(bits):
    sign=bits>>31;exponent=(bits>>23)&255;mantissa=bits&0x7fffff
    need(exponent!=255,'finite binary32 bits')
    n=mantissa if exponent==0 else mantissa+(1<<23);power=-149 if exponent==0 else exponent-150
    q=Fraction(n*(2**power)) if power>=0 else Fraction(n,2**(-power))
    return -q if sign else q


def bit_cell(bits,allow_zero=False):
    if bits is None or type(bits) is not int or not 0<=bits<=0xffffffff:
        raise ValueError('finite positive binary32 required, volume may be zero')
    magnitude=bits&0x7fffffff
    if magnitude>=0x7f800000 or bits>>31 and magnitude or magnitude==0 and not allow_zero:
        raise ValueError('finite positive binary32 required, volume may be zero')
    if magnitude==0:return Fraction(0),Fraction(1,2**150)
    if bits>=0x7f7fffff:raise ValueError('finite neighboring binary32 cells required')
    q=rational(bits)
    return (rational(bits-1)+q)/2,(q+rational(bits+1))/2


def cent_from_bits(price,factor):
    a,b=bit_cell(price);c,d=bit_cell(factor);lo=a/d*(1-GUARD);hi=b/c*(1+GUARD)
    low,high=ceil(lo*100),floor(hi*100)
    result={'status':'NO_CENT_PRICE' if high<low else 'AMBIGUOUS_CENT_PRICE','lower':text(lo),'upper':text(hi),
        'first_cent':low,'last_cent':high,'value':None}
    if low==high and low>0:result.update(status='UNIQUE_POSITIVE_CENT',value=f'{low//100}.{low%100:02d}')
    return result


def volume_from_bits(volume,factor,scale):
    a,b=bit_cell(volume,allow_zero=True);c,d=bit_cell(factor)
    return a*c*scale*(1-GUARD),b*d*scale*(1+GUARD)


class BitFeature:
    def __init__(self,path,length,expected_sha256=None):
        self.raw=Path(path).read_bytes()
        if expected_sha256 is not None:need(hashlib.sha256(self.raw).hexdigest()==expected_sha256,'separate authenticated exact bit buffer')
        need(len(self.raw)>=8 and len(self.raw)%4==0,'separate valid binary extent')
        header=rational(struct.unpack_from('<I',self.raw)[0])
        need(header.denominator==1 and 0<=header<length,'separate bounded integer header');self.start=int(header)
        self.count=len(self.raw)//4-1;need(self.start+self.count<=length,'separate capped feature extent')
    def at(self,index):
        offset=index-self.start
        return None if offset<0 or offset>=self.count else struct.unpack_from('<I',self.raw,(offset+1)*4)[0]


def rebuild_controls(packets,sessions,get):
    reports={};total=trade=excluded=checked=matched=unique=0;bad={1:0,100:0};volume_rows=0
    for code,packet in sorted(packets.items()):
        need(packet['instrument']==code and packet['window']==[START,END],'separate control identity')
        days=[v['date'] for v in packet['bars']];need(days==sorted(set(days)) and set(days)<=set(sessions),'separate control sessions')
        failures=[];ct=cm=0
        for row in packet['bars']:
            total+=1
            if row['tradestatus']!='1':excluded+=1;continue
            trade+=1;ct+=1;at=row['date'];factor=get(code,'factor',at)
            for field in ('open','high','low','close'):
                checked+=1
                try:
                    result=cent_from_bits(get(code,field,at),factor)
                    if result['status']=='UNIQUE_POSITIVE_CENT':unique+=1
                    if result['value'] is not None and Fraction(result['value'])==Fraction(row[field]):matched+=1;cm+=1
                    else:failures.append({'date':at,'field':field,'original':row[field],'reconstruction':result})
                except (ValueError,TypeError) as exc:failures.append({'date':at,'field':field,'error':str(exc)})
            volume_rows+=1;volume=get(code,'volume',at)
            for scale in (1,100):
                try:
                    lo,hi=volume_from_bits(volume,factor,scale)
                    if not lo<=Fraction(row['volume'])<=hi:bad[scale]+=1
                except (ValueError,TypeError):bad[scale]+=1
        reports[code]={'raw_rows':len(days),'trading_rows':ct,'matched_price_cells':cm,'failures':failures}
    candidates=[s for s in (1,100) if volume_rows and bad[s]==0]
    return {'control_codes':len(reports),'raw_rows_counted':total,'trading_rows_checked':trade,'nontrading_rows_excluded':excluded,
        'price_cells_checked':checked,'unique_cent_price_cells':unique,'matched_price_cells':matched,
        'price_gate_passed':bool(reports) and all(v['trading_rows']>0 and v['matched_price_cells']==4*v['trading_rows'] for v in reports.values()),
        'volume_rows_checked':volume_rows,'volume_scale_mismatch_rows':{str(s):n for s,n in bad.items()},
        'volume_scale_candidates':candidates,'identified_volume_scale':candidates[0] if len(candidates)==1 else None,'by_code':reports}


def rebuild_projection(sessions,get,scale):
    rows=[]
    for at in sessions:
        factor=get('SZ002326','factor',at);prices={}
        for field in ('open','high','low','close'):
            try:prices[field]=cent_from_bits(get('SZ002326',field,at),factor)
            except (ValueError,TypeError) as exc:prices[field]={'status':'UNAVAILABLE_F32','value':None,'error':str(exc)}
        row={'date':at,'prices':prices,'volume_lower_shares':None,'source_kind':'CONDITIONAL_F32_LATTICE_PRICES_NOT_RAW_VENDOR_OR_TRADABILITY'}
        if scale is not None:
            try:
                lo,hi=volume_from_bits(get('SZ002326','volume',at),factor,scale)
                row.update(volume_lower_shares=floor(lo),volume_upper_shares=ceil(hi))
            except (ValueError,TypeError) as exc:row['volume_error']=str(exc)
        rows.append(row)
    return rows


def projection_evidence(out,sessions,get,report,terminal):
    """Validate completed rows only; never continue a failed target read."""
    gate=report['price_gate_passed'];projection=[];names=set()
    if gate:
        need(read(out/'target-projection-started.json')=={'only_after_complete_price_gate':True},'separate target gate marker')
        names.add('target-projection-started.json')
        rows=sorted((out/'projection-rows').glob('*.json'));started=sorted((out/'projection-progress').glob('*.json'))
        days=[p.stem for p in rows];attempts=[p.stem for p in started]
        need(days==sessions[:len(days)] and attempts==sessions[:len(attempts)] and len(days)<=len(attempts)<=len(days)+1,'separate exact completed/started prefixes')
        need(terminal['target_read_started']==bool(attempts) and terminal['target_quote_values_decoded']==bool(attempts)
            and terminal['completed_projection_rows']==len(rows) and terminal['last_target_session']==(attempts[-1] if attempts else None),'separate target read progress')
        for path in started:
            need(read(path)=={'date':path.stem,'stage':'TARGET_READ_STARTED'},'separate one reserved session read')
            names.add('projection-progress/'+path.name)
        projection=rebuild_projection(days,get,report['identified_volume_scale'])
        for path,want in zip(rows,projection):
            need(read(path)==want,'separate persisted projection prefix');names.add('projection-rows/'+path.name)
        if (out/'projection.json').exists():
            need(len(days)==len(sessions) and read(out/'projection.json')==projection,'separate full aggregate projection')
            names.add('projection.json')
        if 'error_type' in terminal:
            need(terminal['status']=='LOCAL_SOURCE_RECOVERY_FAILURE_RETAINED' and type(terminal['error_type']) is str
                and type(terminal['error']) is str,'separate retained native target failure')
        else:need(len(days)==len(sessions) and 'projection.json' in names,'separate all target sessions finished')
    else:
        need(terminal['target_read_started'] is False and terminal['target_quote_values_decoded'] is False
            and terminal['completed_projection_rows']==0 and terminal['last_target_session'] is None,'separate forbidden target read state')
    complete=gate and len(projection)==len(sessions) and 'error_type' not in terminal and all(v['volume_lower_shares'] is not None
        and all(p['status']=='UNIQUE_POSITIVE_CENT' for p in v['prices'].values()) for v in projection)
    return {'projection':projection,'complete':complete,'names':names}


def audit(base,root,out,request,expected):
    need(sha(request)==expected,'separate frozen exact request');r=read(request)
    need(r['status']=='FROZEN_LOW_OPERATING_EXACT_F32_SOURCE_HYPOTHESIS' and r['candidate']=='low_operating_profitability_followup_v1'
        and r['window']==[START,END] and r['price_tick']=='1/100' and r['relative_normalizer_guard']=='1/1099511627776'
        and r['volume_unit_hypotheses']==[1,100] and r['network_or_account_or_returns_permitted'] is False
        and r['2026_values_permitted'] is False,'separate fixed reconstruction hypothesis')
    for name,h in ((PROOF,PROOF_SHA),(OPERATING,OPERATING_SHA),(TARGET,TARGET_SHA)):need(sha(root/name)==h,'separate immutable authority')
    old=read(root/PROOF);need(old['tax_risk_codes']==42 and not old['tax_errors'] and old['source_diagnostic_complete'] is False,'separate prior outcomes')
    required={('repo/'+HTTP_REQUEST if k=='frozen_request' else k):h for k,h in old['all_input_sha256'].items()}
    required.update({'source/'+HTTP+'/'+n:h for n,h in old['all_capture_sha256'].items()})
    required.update({'repo/'+n:h for n,h in ((PROOF,PROOF_SHA),(OPERATING,OPERATING_SHA),(TARGET,TARGET_SHA))})
    targets=read(root/TARGET)[FAMILY];codes=sorted({c for v in targets.values() for c in v['weights']})
    manifest=read(base/RAW/'manifest.json');need(len(targets)==24 and len(codes)==43 and set(manifest['per_code_sha256'])==set(codes)-{'SZ002326'},'separate fixed43names42controls')
    authority=read(root/OPERATING)['input_sha256']
    for name in ['calendars/day.txt','instruments/all.txt','manifest.json']+[f'features/{c.lower()}/{f}.day.bin' for c in codes for f in FIELDS]:
        key='source/'+PROVIDER+'/'+name;need(key in authority,'separate original provider binding');required[key]=authority[key]
    need(set(r['input_sha256'])==set(required)|{'repo/'+p for p in (*METHODS,*PUBLIC)}
        and all(r['input_sha256'][k]==v for k,v in required.items()),'separate full transitive closure')
    need(set(r['method_sha256'])==set(METHODS) and all(r['input_sha256']['repo/'+p]==v for p,v in r['method_sha256'].items()),'separate method identities')
    paths={k:resolve(k,root,base) for k in r['input_sha256']};paths['frozen_request']=request;want={**r['input_sha256'],'frozen_request':expected}
    for k,p in paths.items():need(not p.is_symlink() and sha(p)==want[k],'separate input before '+k)
    before=tree(out);terminal=read(out/'terminal.json');need(not any(n.startswith('.') for n in before),'no incomplete staging')
    need(terminal['request_sha256']==expected and terminal['candidate']==r['candidate'] and terminal['all_inputs_unchanged'] is True
        and terminal['all_outputs_unchanged'] is True and terminal['capture_sha256']=={k:h for k,h in before.items() if k!='terminal.json'},'separate terminal snapshot')
    cp=base/PROVIDER/'calendars/day.txt';calendar_bytes=cp.read_bytes()
    need(hashlib.sha256(calendar_bytes).hexdigest()==want['source/'+PROVIDER+'/calendars/day.txt'],'separate exact calendar buffer')
    calendar=calendar_bytes.decode().splitlines()
    need(calendar==sorted(set(calendar)) and calendar[-1]==END and all(date.fromisoformat(d).isoformat()==d for d in calendar),'separate physically capped calendar')
    sessions=[d for d in calendar if START<=d<=END];need(len(sessions)==486 and sessions==read(base/RAW/'calendar.json')['sessions'],'separate486sessions')
    packets={c:read(base/RAW/'codes'/(c+'.json')) for c in sorted(manifest['per_code_sha256'])}
    for c in packets:need(sha(base/RAW/'codes'/(c+'.json'))==manifest['per_code_sha256'][c],'separate raw control identity')
    cache={};indices={d:i for i,d in enumerate(calendar)}
    def get(code,field,at):
        need(at in sessions and field in FIELDS and code in set(packets)|{'SZ002326'},'separate only registered cells')
        key=(code,field)
        if key not in cache:
            name='features/'+code.lower()+'/'+field+'.day.bin'
            cache[key]=BitFeature(base/PROVIDER/name,len(calendar),want['source/'+PROVIDER+'/'+name])
        return cache[key].at(indices[at])
    report=rebuild_controls(packets,sessions,get);need(report==read(out/'control-summary.json'),'separate all controls/counters/units')
    for code,v in report['by_code'].items():need(read(out/'controls'/(code+'.json'))==v,'separate per-issuer result')
    need(report['raw_rows_counted']==20089 and report['control_codes']==42,'all original controls counted')
    gate=report['price_gate_passed'];names={'terminal.json','control-summary.json'}|{'controls/'+c+'.json' for c in packets}
    # Recheck the entire frozen context immediately before any target getter.
    if gate:
        for k,p in paths.items():need(sha(p)==want[k],'separate full context at target boundary '+k)
        need(tree(out)==before,'separate control evidence at target boundary')
    facts=projection_evidence(out,sessions,get,report,terminal);projection=facts['projection'];complete=facts['complete'];names|=facts['names']
    need(set(before)==names,'separate exact output closure and no forbidden target artifact')
    status='LOCAL_SOURCE_RECOVERY_FAILURE_RETAINED' if 'error_type' in terminal else 'CONDITIONAL_F32_SOURCE_PROJECTION_COMPLETE_NOT_ACCOUNT_ADMITTED' if complete else 'F32_SOURCE_HYPOTHESIS_NOT_FULLY_VERIFIED'
    need(terminal['complete']==complete and terminal['source_projection_complete']==complete and terminal['status']==status
        and terminal['control_price_gate_passed']==gate,'separate source outcomes')
    for key in ('historical_arrival_verified','physical_account_admitted','tax_treatment_admitted','corporate_action_completeness_verified','portfolio_return_computed','2026_values_read','objective_achieved'):
        need(terminal[key] is False,'conditional sources cannot admit accounts or goal')
    for k,p in paths.items():need(sha(p)==want[k],'separate input after '+k)
    need(tree(out)==before,'separate unchanged source outputs')
    return {'status':'PASS_RETAINED_F32_SOURCE_FAILURE_PREFIX_NOT_ACCOUNT_ADMISSION' if 'error_type' in terminal else 'PASS_INDEPENDENT_BIT_SOURCE_RECONSTRUCTION_NOT_ACCOUNT_ADMISSION','request_sha256':expected,
        'all_input_sha256':want,'all_capture_sha256':before,'all_inputs_outputs_unchanged':True,'no_new_producer_or_bounds_imports':True,
        'control_codes':report['control_codes'],'raw_rows_counted':report['raw_rows_counted'],'trading_rows_checked':report['trading_rows_checked'],
        'price_cells_checked':report['price_cells_checked'],'matched_price_cells':report['matched_price_cells'],'control_price_gate_passed':gate,
        'identified_volume_scale':report['identified_volume_scale'],'volume_scale_mismatch_rows':report['volume_scale_mismatch_rows'],
        'target_quote_values_decoded':terminal['target_quote_values_decoded'],'target_projection_rows':len(projection),'source_projection_complete':complete,
        'physical_account_admitted':False,'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False}


def main():
    p=argparse.ArgumentParser()
    for name in ('source-root','raw-dir','request','expected-request-sha256','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();out=Path(a.output);raw=Path(a.raw_dir).resolve();need(not out.exists() and not out.resolve().is_relative_to(raw),'fresh external proof')
    try:result=audit(Path(a.source_root).resolve(),Path(__file__).resolve().parents[1],raw,Path(a.request).resolve(),a.expected_request_sha256)
    except BaseException as exc:
        with out.open('x') as f:json.dump({'status':'FAILED_SEPARATE_F32_SOURCE_CHECK','error_type':type(exc).__name__,'error':str(exc),'objective_achieved':False},f,indent=2)
        raise
    with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(result['status'],'controls',result['control_codes'],'price_gate',result['control_price_gate_passed'],'complete',result['source_projection_complete'],flush=True)


if __name__=='__main__':main()
