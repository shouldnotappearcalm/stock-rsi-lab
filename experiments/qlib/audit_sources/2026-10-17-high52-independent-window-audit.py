"""Stdlib reconstruction of source-window counts; imports no project code."""
import argparse,hashlib,json
from decimal import Decimal,ROUND_DOWN
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source-dir',required=True);p.add_argument('--output',required=True);a=p.parse_args()
root=Path(a.source_dir);out=Path(a.output);assert not out.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result=json.loads((root/'analysis.json').read_text());manifest=json.loads((root/'manifest.json').read_text())
assert result['capture_manifest_sha256']==sha(root/'manifest.json')
for name,h in manifest['artifact_sha256'].items():assert sha(root/name)==h
verified=[];failed=[]
for r in result['results']:
 code,day=r['instrument'],r['day'];name=code+'-'+day+'.json';assert day<='2025-12-31'
 raw=json.loads((root/'daily'/name).read_text())['bar'];packet=json.loads((root/'sessions'/name).read_text());record=packet.get('methods',{}).get('minutes.history',packet)
 if r['status']=='SOURCE_REJECTED':
  assert record['status']=='REQUEST_FAILED';failed.append([code,day]);continue
 assert r['status']=='SOURCE_WINDOW_EVIDENCE_COMPLETE' and record['status']=='RESPONSE_CAPTURED'
 points=record['response']['points'];assert len(points)==240 and raw['tradestatus']=='1' and raw['isST']=='0'
 assert Decimal(points[-1]['price_milli'])/1000==Decimal(raw['close'])
 windows=[]
 for i in range(0,240,5):
  block=points[i:i+5];prices=[Decimal(x['price_milli'])/1000 for x in block if x['volume']>0]
  assert all(type(x['volume']) is int and x['volume']>=0 for x in block)
  windows.append((sum(max(0,x['volume']*100-100) for x in block),max(prices) if prices else None,block[-1]['time']))
 upper=(Decimal(raw['preclose'])*Decimal('1.095')).quantize(Decimal('.01'),rounding=ROUND_DOWN)
 for participation in (100,500,1000):
  actual=r['evidence_by_participation_bps'][str(participation)];expected=[]
  for i in range(1,47):
   before,now=windows[i-1],windows[i]
   shares=min(before[0]*participation//10000,now[0]*participation//10000,1000000)//100*100
   if shares>=100 and now[1] is not None and now[1]<upper:expected.append((datetime.fromisoformat(now[2]).astimezone(timezone.utc).isoformat(),shares,str(now[1])))
  assert actual['protective_buy_limit_CNY']==str(upper) and actual['candidate_windows']==len(expected)
  assert [(w['end'],w['two_bucket_volume_cap_shares'],w['sampled_adverse_buy_CNY']) for w in actual['windows']]==expected
  assert actual['actual_fill_verified'] is False and actual['cash_and_parent_quantity_simulated'] is False
 verified.append(r)
counts={str(p):sum(r['evidence_by_participation_bps'][str(p)]['candidate_windows']>0 for r in verified) for p in (100,500,1000)}
assert counts==result['pairs_with_candidate_windows_by_participation_bps']
assert len(verified)==34 and failed==[['SH603056','2025-06-03']]
out.write_text(json.dumps({'status':'INDEPENDENT_SOURCE_WINDOW_COUNTS_RECONSTRUCTED','analysis_sha256':sha(root/'analysis.json'),
 'audit_code_sha256':sha(Path(__file__)),'valid_pairs':34,'failed_pairs_preserved':failed,'candidate_window_pair_counts':counts,
 'imports_project_code':False,'scope':'Raw minute blocks, prior/current stressed capacities, protective threshold and eligible interval counts only.',
 'actual_fills_verified':False,'new_portfolio_account_run':False,'2026_market_values_queried':False,'objective_achieved':False},indent=2)+'\n')
print('independent source-window audit',len(verified),'valid; counts',counts)
