"""Frozen local f32 source probe; controls precede any missing-code decoding."""
import argparse
from datetime import date
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import struct
from scripts.immutable_http_capture import need,write_once,file_sha as sha
from stock_rsi.float32_quote_bounds import cent_price,volume_interval,floor
from scripts.audit_low_operating_raw_pre2026 import resolve

START,END='2023-12-29','2025-12-31'
CANDIDATE='low_operating_profitability_followup_v1'
OUTPUT='low-operating-f32-source-recovery-v1-20261023'
PROVIDER='qlib-price-delay-pre2026-clock-v2-20261021'
RAW='low-operating-lifecycle-raw-pre2026-v1-20261023'
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
DESIGN='docs/research/low-operating-float32-source-design-2026-10-23.md'
PLAN='docs/superpowers/plans/2026-10-23-low-operating-float32-sources.md'
REVIEW=PREFIX+'low-operating-f32-source-review.json'
METHODS=('src/stock_rsi/float32_quote_bounds.py','scripts/recover_low_operating_quotes_pre2026.py',
    'scripts/audit_low_operating_quote_recovery_pre2026.py','tests/test_low_operating_quote_recovery.py','scripts/immutable_http_capture.py')

def read(p):return json.loads(Path(p).read_text())
def tree(p):return {str(f.relative_to(p)):sha(f) for f in sorted(p.rglob('*')) if f.is_file()}
def changed(paths):
    result=[]
    for p,h in paths.items():
        try:
            if sha(p)!=h:result.append(p)
        except OSError:result.append(p)
    return result


class Feature:
    def __init__(self,path,calendar_length,expected_sha256=None):
        self.raw=Path(path).read_bytes()
        if expected_sha256 is not None:need(hashlib.sha256(self.raw).hexdigest()==expected_sha256,'authenticated exact feature buffer')
        need(len(self.raw)>=8 and len(self.raw)%4==0,'valid f32 file size')
        start=struct.unpack_from('<f',self.raw)[0]
        need(start==int(start) and 0<=start<calendar_length,'integer bounded f32 header');self.start=int(start)
        self.count=len(self.raw)//4-1;need(self.start+self.count<=calendar_length,'feature extends beyond capped calendar')
    def value(self,index):
        offset=index-self.start
        return None if offset<0 or offset>=self.count else struct.unpack_from('<f',self.raw,(offset+1)*4)[0]


def read32(path,index,calendar_length):
    need(type(index) is int and 0<=index<calendar_length,'explicit bounded calendar index')
    return Feature(path,calendar_length).value(index)


def controls(packets,sessions,get,on_control=None):
    reports={};total=trade=excluded=checked=matched=unique=0;volume_bad={1:0,100:0};volume_rows=0
    for code,packet in sorted(packets.items()):
        need(packet['instrument']==code and packet['window']==[START,END],'original control identity/window')
        days=[v['date'] for v in packet['bars']];need(days==sorted(set(days)) and set(days)<=set(sessions),'explicit original control sessions')
        failures=[];ct=cm=0
        for row in packet['bars']:
            total+=1
            if row['tradestatus']!='1':excluded+=1;continue
            trade+=1;ct+=1;day=row['date'];factor=get(code,'factor',day)
            for field in ('open','high','low','close'):
                checked+=1
                try:
                    recovered=cent_price(get(code,field,day),factor)
                    if recovered['status']=='UNIQUE_POSITIVE_CENT':unique+=1
                    if recovered['value'] is not None and Fraction(recovered['value'])==Fraction(row[field]):matched+=1;cm+=1
                    else:failures.append({'date':day,'field':field,'original':row[field],'reconstruction':recovered})
                except (ValueError,TypeError) as exc:failures.append({'date':day,'field':field,'error':str(exc)})
            volume_rows+=1;volume=get(code,'volume',day)
            for scale in (1,100):
                try:
                    lo,hi=volume_interval(volume,factor,scale)
                    if not lo<=Fraction(row['volume'])<=hi:volume_bad[scale]+=1
                except (ValueError,TypeError):volume_bad[scale]+=1
        reports[code]={'raw_rows':len(days),'trading_rows':ct,'matched_price_cells':cm,'failures':failures}
        if on_control:on_control(code,reports[code])
    candidates=[s for s in (1,100) if volume_rows and volume_bad[s]==0]
    return {'control_codes':len(reports),'raw_rows_counted':total,'trading_rows_checked':trade,'nontrading_rows_excluded':excluded,
        'price_cells_checked':checked,'unique_cent_price_cells':unique,'matched_price_cells':matched,
        'price_gate_passed':bool(reports) and all(r['trading_rows']>0 and r['matched_price_cells']==4*r['trading_rows'] for r in reports.values()),
        'volume_rows_checked':volume_rows,'volume_scale_mismatch_rows':{str(s):n for s,n in volume_bad.items()},
        'volume_scale_candidates':candidates,'identified_volume_scale':candidates[0] if len(candidates)==1 else None,'by_code':reports}


def project(sessions,get,scale,on_row=None,on_read=None):
    result=[]
    for day in sessions:
        if on_read:on_read(day)
        factor=get('SZ002326','factor',day);prices={}
        for field in ('open','high','low','close'):
            try:prices[field]=cent_price(get('SZ002326',field,day),factor)
            except (ValueError,TypeError) as exc:prices[field]={'status':'UNAVAILABLE_F32','value':None,'error':str(exc)}
        row={'date':day,'prices':prices,'volume_lower_shares':None,
            'source_kind':'CONDITIONAL_F32_LATTICE_PRICES_NOT_RAW_VENDOR_OR_TRADABILITY'}
        if scale is not None:
            try:
                lo,hi=volume_interval(get('SZ002326','volume',day),factor,scale)
                row.update(volume_lower_shares=floor(lo),volume_upper_shares=-((-hi.numerator)//hi.denominator))
            except (ValueError,TypeError) as exc:row['volume_error']=str(exc)
        if on_row:on_row(row)
        result.append(row)
    return result


def recover(packets,sessions,get,on_control=None,before_target=None,on_summary=None,on_row=None,on_read=None):
    report=controls(packets,sessions,get,on_control);projection=[];decoded=report['price_gate_passed']
    if on_summary:on_summary(report)
    if decoded:
        if before_target:before_target()
        projection=project(sessions,get,report['identified_volume_scale'],on_row,on_read)
    complete=decoded and len(projection)==len(sessions) and all(r['volume_lower_shares'] is not None
        and all(p['status']=='UNIQUE_POSITIVE_CENT' for p in r['prices'].values()) for r in projection)
    return {'controls':report,'projection':projection,'target_quote_values_decoded':decoded,'source_projection_complete':complete}


def context(base,root):
    need(sha(root/PROOF)==PROOF_SHA and sha(root/OPERATING)==OPERATING_SHA and sha(root/TARGET)==TARGET_SHA,'fixed source/strategy/provider authorities')
    prior=read(root/PROOF);need(prior['tax_risk_codes']==42 and not prior['tax_errors'] and prior['source_diagnostic_complete'] is False,'preserved prior actual source outcome')
    paths={};expected={}
    for key,h in prior['all_input_sha256'].items():
        k='repo/'+HTTP_REQUEST if key=='frozen_request' else key;p=root/HTTP_REQUEST if key=='frozen_request' else resolve(key,root,base)
        paths[k]=p;expected[k]=h
    for name,h in prior['all_capture_sha256'].items():paths['source/'+HTTP+'/'+name]=base/HTTP/name;expected['source/'+HTTP+'/'+name]=h
    for name,h in ((PROOF,PROOF_SHA),(OPERATING,OPERATING_SHA),(TARGET,TARGET_SHA)):paths['repo/'+name]=root/name;expected['repo/'+name]=h
    targets=read(root/TARGET)[FAMILY];codes=sorted({c for v in targets.values() for c in v['weights']});m=read(base/RAW/'manifest.json')
    need(len(targets)==24 and len(codes)==43 and set(m['per_code_sha256'])==set(codes)-{'SZ002326'},'all fixed targets and42controls')
    authority=read(root/OPERATING)['input_sha256']
    names=['calendars/day.txt','instruments/all.txt','manifest.json']+[f'features/{c.lower()}/{f}.day.bin' for c in codes for f in FIELDS]
    for name in names:
        key='source/'+PROVIDER+'/'+name;need(key in authority,'original provider binding '+name);paths[key]=base/PROVIDER/name;expected[key]=authority[key]
    for k,p in paths.items():need(not p.is_symlink() and sha(p)==expected[k],'authenticated full original/provider context '+k)
    calendar=(base/PROVIDER/'calendars/day.txt').read_text().splitlines()
    need(calendar==sorted(set(calendar)) and calendar[-1]==END and all(date.fromisoformat(d).isoformat()==d for d in calendar),'physically capped explicit canonical calendar')
    sessions=[d for d in calendar if START<=d<=END];need(len(sessions)==486 and sessions==read(base/RAW/'calendar.json')['sessions'],'same486source sessions')
    packets={c:read(base/RAW/'codes'/(c+'.json')) for c in sorted(m['per_code_sha256'])}
    for c,p in packets.items():need(sha(base/RAW/'codes'/(c+'.json'))==m['per_code_sha256'][c],'unchanged raw control packet')
    return packets,sessions,paths


def authenticate(base,root,request,expected):
    need(sha(request)==expected,'frozen local recovery request');r=read(request)
    need(r['status']=='FROZEN_LOW_OPERATING_EXACT_F32_SOURCE_HYPOTHESIS' and r['candidate']==CANDIDATE and r['window']==[START,END]
        and r['price_tick']=='1/100' and r['relative_normalizer_guard']=='1/1099511627776' and r['volume_unit_hypotheses']==[1,100]
        and r['network_or_account_or_returns_permitted'] is False and r['2026_values_permitted'] is False,'fixed single local reconstruction hypothesis')
    packets,sessions,paths=context(base,root)
    for p in (*METHODS,DESIGN,PLAN,REVIEW):paths['repo/'+p]=root/p
    need(set(paths)==set(r['input_sha256']) and set(r['method_sha256'])==set(METHODS),'complete recovery closure')
    for k,p in paths.items():need(sha(p)==r['input_sha256'][k],'bound recovery input '+k)
    for p,h in r['method_sha256'].items():need(h==r['input_sha256']['repo/'+p],'explicit recovery method')
    return r,packets,sessions,{**{str(p.resolve()):r['input_sha256'][k] for k,p in paths.items()},str(request.resolve()):expected}


def persist(out,name,value,outputs):
    # Bind the intended bytes before the write, rather than adopting later bytes.
    encoded=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    need(name not in outputs,'one immutable artifact write');outputs[name]=hashlib.sha256(encoded).hexdigest()
    path=out/name;path.parent.mkdir(parents=True,exist_ok=True);write_once(path,value)
    need(sha(path)==outputs[name],'original bytes persisted '+name)


def finish(out,result,known,outputs):
    base=dict(outputs);primary=None
    result={**result,'capture_sha256':base,'all_inputs_unchanged':not changed(known),'all_outputs_unchanged':True}
    try:
        need(tree(out)==base,'source outputs changed before terminal persistence')
        write_once(out/'.terminal-pending.json',result)
        after={k:h for k,h in tree(out).items() if k!='.terminal-pending.json'}
        need(not changed(known) and after==base,'source recovery inputs/outputs changed during persistence')
        os.replace(out/'.terminal-pending.json',out/'terminal.json')
    except BaseException as exc:
        primary=exc;after={k:h for k,h in tree(out).items() if k not in ('.terminal-pending.json','terminal.json')}
        result.update(complete=False,status='LOCAL_SOURCE_RECOVERY_FAILURE_RETAINED',all_inputs_unchanged=not changed(known),
            all_outputs_unchanged=after==base,error_type=type(exc).__name__,error=str(exc))
        result['observed_capture_sha256']=after
        try:write_once(out/'.terminal-failure.json',result);os.replace(out/'.terminal-failure.json',out/'terminal.json')
        except BaseException as secondary:primary.add_note('failure terminal persistence error: '+type(secondary).__name__)
    if primary is not None:raise primary
    return result


def run(base,root,request,expected):
    r,packets,sessions,known=authenticate(base,root,request,expected);out=base/OUTPUT;need(not out.exists() and not out.is_symlink(),'fresh local recovery output')
    cp=base/PROVIDER/'calendars/day.txt';calendar_bytes=cp.read_bytes()
    need(hashlib.sha256(calendar_bytes).hexdigest()==known[str(cp.resolve())],'authenticated actual calendar buffer')
    calendar=calendar_bytes.decode().splitlines();indices={d:i for i,d in enumerate(calendar)};cache={}
    def get(code,field,day):
        need(day in sessions and field in FIELDS and code in set(packets)|{'SZ002326'},'only frozen quote cells')
        key=(code,field)
        if key not in cache:
            path=base/PROVIDER/'features'/code.lower()/(field+'.day.bin')
            cache[key]=Feature(path,len(calendar),known[str(path.resolve())])
        return cache[key].value(indices[day])
    out.mkdir();(out/'controls').mkdir();primary=None;outputs={}
    result={'candidate':CANDIDATE,'request_sha256':expected,'complete':False,'status':'LOCAL_SOURCE_RECOVERY_INCOMPLETE',
        'historical_arrival_verified':False,'physical_account_admitted':False,'tax_treatment_admitted':False,
        'corporate_action_completeness_verified':False,'portfolio_return_computed':False,'2026_values_read':False,'objective_achieved':False,
        'source_projection_complete':False,'control_price_gate_passed':False,'target_quote_values_decoded':False,
        'target_read_started':False,'completed_projection_rows':0,'last_target_session':None}
    def save(name,value):persist(out,name,value,outputs)
    def summary(report):
        save('control-summary.json',report);result['control_price_gate_passed']=report['price_gate_passed']
    def boundary():
        need(not changed(known),'complete frozen context unchanged before target access')
        need(tree(out)==outputs,'all control evidence unchanged before target access')
        save('target-projection-started.json',{'only_after_complete_price_gate':True})
    def reading(day):
        save('projection-progress/'+day+'.json',{'date':day,'stage':'TARGET_READ_STARTED'})
        result.update(target_read_started=True,target_quote_values_decoded=True,last_target_session=day)
    def row_done(row):
        save('projection-rows/'+row['date']+'.json',row);result['completed_projection_rows']+=1
    try:
        data=recover(packets,sessions,get,lambda c,v:save('controls/'+c+'.json',v),boundary,summary,row_done,reading)
        if data['target_quote_values_decoded']:save('projection.json',data['projection'])
        result.update(complete=data['source_projection_complete'],source_projection_complete=data['source_projection_complete'],
            target_quote_values_decoded=data['target_quote_values_decoded'],control_price_gate_passed=data['controls']['price_gate_passed'],
            status='CONDITIONAL_F32_SOURCE_PROJECTION_COMPLETE_NOT_ACCOUNT_ADMITTED' if data['source_projection_complete'] else 'F32_SOURCE_HYPOTHESIS_NOT_FULLY_VERIFIED')
    except BaseException as exc:primary=exc;result.update(status='LOCAL_SOURCE_RECOVERY_FAILURE_RETAINED',error_type=type(exc).__name__,error=str(exc))
    try:final=finish(out,result,known,outputs)
    except BaseException as exc:
        if primary is None:primary=exc
        else:primary.add_note('terminal persistence error: '+type(exc).__name__)
    if primary is not None:raise primary
    return final


def main():
    p=argparse.ArgumentParser()
    for n in ('source-root','request','expected-request-sha256'):p.add_argument('--'+n,required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();root=Path(__file__).resolve().parents[1];base=Path(a.source_root).resolve();req=Path(a.request).resolve()
    if a.preflight_only:authenticate(base,root,req,a.expected_request_sha256);print('full local/provider preflight PASS;no feature comparison',flush=True);return 0
    result=run(base,root,req,a.expected_request_sha256);print(result['status'],flush=True);return 0 if result['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
