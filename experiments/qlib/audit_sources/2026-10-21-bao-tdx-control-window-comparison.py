"""Source-only96window comparison; never changes source admission or alpha."""
import argparse,hashlib,json
from decimal import Decimal as D
from pathlib import Path


def main():
 p=argparse.ArgumentParser();p.add_argument('--base-dir',required=True);p.add_argument('--output-dir',required=True);args=p.parse_args()
 b=Path(args.base_dir);out=Path(args.output_dir)
 if out.exists():raise ValueError('source window comparison output exists')
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 probe=b/'illiquidity-missing-minute-probes-20261021';pm=json.loads((probe/'manifest.json').read_text())
 request=Path('experiments/qlib/illiquidity-missing-minute-source-probe-request.json')
 assert sha(request)==pm['request_sha256']
 public=Path('experiments/qlib/illiquidity-development-minute-admission.json');admission=json.loads(public.read_text())
 assert admission['admitted_for_reconstructed_execution'] is False
 roots=[b/'tdx-fixed-order-history-20261017',b/'illiquidity-minutes-dev-20261021'];index={};source_manifests={}
 for root,key in zip(roots,('old_tape_manifest_sha256','extra_tape_manifest_sha256')):
  assert sha(root/'manifest.json')==admission[key];source_manifests[root.name]=sha(root/'manifest.json')
  for name,h in json.loads((root/'manifest.json').read_text())['per_session_sha256'].items():
   assert name not in index;index[name]=(root/'sessions'/name,h)
 rows=[];controls=[]
 for result in pm['results']:
  if result['method']!='query_history_k_data_plus' or result['role']!='FIXED_HASH_CHOSEN_CONTROL':continue
  code,day=result['instrument'],result['day'];path=probe/result['file'];assert sha(path)==result['sha256']
  record=json.loads(path.read_text())['payload']['rows'][0]
  assert len(record['rows'])==48
  five=[dict(zip(record['fields'],r)) for r in record['rows']]
  path,h=index[code+'-'+day+'.json'];assert sha(path)==h
  packet=json.loads(path.read_text());assert packet['instrument']==code and packet['requested_day']==day
  value=packet.get('methods',{}).get('minutes.history',packet)
  assert value['status']=='RESPONSE_CAPTURED';points=value['response']['points'];assert len(points)==240
  local=[]
  for i,f in enumerate(five):
   block=points[i*5:i*5+5];assert f['time']==day.replace('-','')+block[-1]['time_label'].replace(':','')+'00000'
   prices=[D(x['price_milli'])/1000 for x in block if x['volume']>0]
   nominal=sum(x['volume']*100 for x in block);lower=sum(max(0,x['volume']*100-100) for x in block)
   r={'instrument':code,'day':day,'bucket_index':i,'end_label':block[-1]['time_label'],
    'inside_existing_execution_bucket_range':1<=i<=46,
    'Bao_OHLC_contains_TDX_sampled_prices':all(D(f['low'])<=x<=D(f['high']) for x in prices),
    'end_close_equal':D(f['close'])==D(block[-1]['price_milli'])/1000,
    'Bao_reported_share_volume':int(f['volume']),'TDX_nominal_hand_volume_as_shares':nominal,
    'TDX_lower_shares':lower,'Bao_volume_minus_TDX_nominal':int(f['volume'])-nominal}
   local.append(r);rows.append(r)
  active=[r for r in local if r['inside_existing_execution_bucket_range']]
  controls.append({'instrument':code,'day':day,'windows':48,'end_close_mismatches':sum(not r['end_close_equal'] for r in local),
   'execution_range_end_close_mismatches':sum(not r['end_close_equal'] for r in active),
   'execution_range_all_sampled_prices_contained':all(r['Bao_OHLC_contains_TDX_sampled_prices'] for r in active),
   'maximum_abs_execution_range_volume_difference_shares':max(abs(r['Bao_volume_minus_TDX_nominal']) for r in active),
   'distinct_execution_range_volume_differences':sorted(set(r['Bao_volume_minus_TDX_nominal'] for r in active)),
   'TDX_packet_sha256':h,'Bao_packet_sha256':result['sha256']})
 out.mkdir(parents=True);(out/'windows.json').write_text(json.dumps(rows,indent=2)+'\n')
 summary={'status':'TWO_CONTROL_SOURCE_WINDOW_COMPARISON_COMPLETE','audit_code_sha256':sha(Path(__file__)),
  'source_probe_manifest_sha256':sha(probe/'manifest.json'),'source_admission_summary_sha256':sha(public),
  'source_minute_manifest_sha256':source_manifests,'controls':controls,'windows_compared':len(rows),
  'execution_range_windows':sum(r['inside_existing_execution_bucket_range'] for r in rows),
  'execution_range_end_close_mismatches':sum(r['inside_existing_execution_bucket_range'] and not r['end_close_equal'] for r in rows),
  'detail_sha256':sha(out/'windows.json'),'source_timing_or_true_volume_certified':False,
  'uniform_volume_conversion_is_a_verified_fix':False,'source_admission_changed':False,
  'source_prices_or_volumes_modified':False,'portfolio_returns_computed':False,'2026_market_values_queried':False,'objective_achieved':False}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
