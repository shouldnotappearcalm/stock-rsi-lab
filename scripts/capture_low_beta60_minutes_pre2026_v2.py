"""Strict byte-anchored resume; legacy frozen capture implementation is unchanged."""
import argparse,fcntl,json
from pathlib import Path
from scripts.capture_low_beta60_minutes_pre2026 import capture_prefix as legacy_capture,authenticate
from scripts.admit_low_beta60_minutes_pre2026 import METHOD_FILES as SOURCE_METHODS,verify_query_receipt
from scripts.fundamental_query_journal import digest,file_sha

METHOD_FILES=tuple((*SOURCE_METHODS,'scripts/capture_low_beta60_minutes_pre2026_v2.py'))


def exact_json_file(path,value):
    expected=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    if Path(path).read_bytes()!=expected:raise ValueError('immutable journal/snapshot bytes changed')


def capture_prefix_v2(base,out,reused,fresh,plan,fetch,*,expected_manifest_sha256=None):
    base,out=Path(base),Path(out)
    budget=plan.get('max_fresh_query_reservations')
    if type(budget) is not int or not 1<=budget<=493 or len(fresh)!=budget:
        raise ValueError('absolute493 fresh logical reservation cap required')
    mf=out/'manifest.json'
    if expected_manifest_sha256 is None or not mf.exists() or file_sha(mf)!=expected_manifest_sha256:
        raise ValueError('externally anchored existing capture manifest required')
    m=json.loads(mf.read_text())
    for field,name in (('plan_sha256','plan.json'),('capture_request_sha256','capture_request.json')):
        if file_sha(out/name)!=m[field]:raise ValueError('existing configuration bytes changed')
    if json.loads((out/'plan.json').read_text())!=plan or json.loads((out/'capture_request.json').read_text())!={'reused':reused,'fresh':fresh}:
        raise ValueError('original capture configuration changed')
    if 'request_sha256' in plan and file_sha(out/'request.json')!=plan['request_sha256']:
        raise ValueError('original frozen request bytes changed')
    selected=out/('capture-snapshot-'+digest(m)+'.json')
    if not selected.exists() or json.loads(selected.read_text())!=m:raise ValueError('bound immutable snapshot missing or changed')
    for snapshot in out.glob('capture-snapshot-*.json'):
        value=json.loads(snapshot.read_text())
        if snapshot.name!='capture-snapshot-'+digest(value)+'.json':raise ValueError('historical capture snapshot identity changed')
        exact_json_file(snapshot,value)
    names={c+'-'+d+'.json' for c,d in fresh}|set(reused)
    if (m['requested']!=len(names) or m['captured']!=len(m['per_session_sha256'])
            or not set(m['per_session_sha256'])<=names or m['reused_session_provenance']!=reused
            or m['complete_capture']!=(len(m['per_session_sha256'])==len(names))):raise ValueError('existing capture coverage changed')
    if {p.name for p in (out/'sessions').iterdir()}!=set(m['per_session_sha256']):
        raise ValueError('unbound session or interrupted partial session needs separate evidence recovery')
    for name,h in m['per_session_sha256'].items():
        if file_sha(out/'sessions'/name)!=h:raise ValueError('captured source packet bytes changed')
        if name in reused:
            origin=reused[name]
            if h!=origin['sha256'] or file_sha(base/origin['root']/'sessions'/name)!=h:raise ValueError('reused source bytes changed')
    identities={}
    for code,day in fresh:
        identity={'method':'minutes.history','instrument':code,'requested_day':day,'host':plan['host'],'include_raw':True}
        key=digest(identity)
        if key in identities:raise ValueError('duplicate source identity')
        identities[key]=(code,day,identity)
    folders=[f for f in (out/'queries').iterdir()] if (out/'queries').exists() else []
    if any(not f.is_dir() or f.name not in identities for f in folders):raise ValueError('unknown existing journal identity')
    for folder in folders:
        code,day,identity=identities[folder.name];name=code+'-'+day+'.json'
        if not (folder/'response-1.json').exists():raise ValueError('reserved unanswered attempt remains consumed; no free retry')
        if {p.name for p in folder.iterdir()}!={'request.json','reserved-1.json','response-1.json'}:
            raise ValueError('unexpected or interrupted journal attempt files')
        exact_json_file(folder/'request.json',identity)
        for n in ('reserved-1.json','response-1.json'):
            exact_json_file(folder/n,json.loads((folder/n).read_text()))
        if name not in m['per_session_sha256']:raise ValueError('journal outcome outside immutable snapshot needs separate evidence recovery')
        packet=json.loads((out/'sessions'/name).read_text())
        verify_query_receipt(out,code,day,packet,plan['host'])
    fired={identities[f.name][0]+'-'+identities[f.name][1]+'.json' for f in folders}
    if fired!=set(m['per_session_sha256'])-set(reused):raise ValueError('fresh session missing original journal')
    if m['fresh_query_reservations']!=len(folders) or m['fresh_query_responses_preserved']!=len(folders):
        raise ValueError('journal attempt totals changed')
    if m['complete_capture']:
        if m['abnormal_exit'] is not None or m['stopped_after_consecutive_source_failures']:raise ValueError('complete capture carries invalid terminal state')
        return m
    if m['abnormal_exit'] is not None:raise ValueError('interrupted capture requires separately reviewed recovery')
    return legacy_capture(base,out,reused,fresh,plan,fetch)


def main(argv=None):
    p=argparse.ArgumentParser()
    for n in ('source-root','capture-dir','guard-plan','expected-guard-plan-sha256'):p.add_argument('--'+n,required=True)
    a=p.parse_args(argv);repo=Path(__file__).resolve().parents[1];base=Path(a.source_root);out=Path(a.capture_dir)
    if file_sha(a.guard_plan)!=a.expected_guard_plan_sha256:raise ValueError('strict resume guard plan changed')
    guard=json.loads(Path(a.guard_plan).read_text())
    if guard['status']!='FROZEN_LOW_BETA60_COMPLETE_CAPTURE_STRICT_LOCAL_RECHECK' or set(guard['method_code_sha256'])!=set(METHOD_FILES):
        raise ValueError('strict local-only recheck method changed')
    for n,h in guard['method_code_sha256'].items():
        if file_sha(repo/n)!=h:raise ValueError('strict resume guard code changed')
    for n,h in guard['public_evidence_sha256'].items():
        if Path(n).is_absolute() or '..' in Path(n).parts or file_sha(repo/n)!=h:raise ValueError('strict guard evidence changed')
    cp=repo/'experiments/qlib/low-beta60-minute-capture-plan.json';rq=repo/'experiments/qlib/low-beta60-minute-gap-identities.json'
    if file_sha(cp)!=guard['capture_plan_sha256'] or file_sha(rq)!=guard['request_sha256']:raise ValueError('original frozen identities changed')
    plan=json.loads(cp.read_text());request=json.loads(rq.read_text());reused,fresh=authenticate(base,repo,request,plan)
    if not json.loads((out/'manifest.json').read_text())['complete_capture']:raise ValueError('this frozen guard only permits complete local recheck')
    def no_fetch(*args):raise AssertionError('no SDK call authorized by local-only guard')
    with (out/'capture.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=capture_prefix_v2(base,out,reused,fresh,plan,no_fetch,expected_manifest_sha256=guard['capture_manifest_sha256'])
    print('Strict v2 recheck:1332original source bytes and493journals authenticated;zero SDK calls or source rewrites',flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
