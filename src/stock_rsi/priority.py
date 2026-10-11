"""Frozen-rule exploratory runs on captured raw prices, with explicit caveats."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from .data import canonical
from .runner import run
from .skill import RuleAgent,Skill
from .time import parse_time


def build_dataset(capture_dir,codes):
    root=Path(capture_dir)
    calendar=json.loads((root/'calendar.stdout').read_text())
    days=[row['date'] for row in calendar]
    if not days or len(set(days))!=len(days):
        raise ValueError('explicit unique calendar required')
    records,sources,jumps=[],[],[]
    for code in codes:
        path=root/(code+'.stdout')
        body=json.loads(path.read_text())
        if body['meta']['adjust_actual']!='raw':
            raise ValueError('execution requires explicitly raw source prices')
        rows=sorted(body['data'],key=lambda row:row['time'])
        seen=set();previous=None
        for row in rows:
            day=row['time']
            if day in seen or day not in days:
                raise ValueError('duplicate or off-calendar bar')
            seen.add(day)
            prices=[row[key] for key in ('open','close','high','low')]
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in prices):
                raise ValueError('invalid finite OHLC')
            if not row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']:
                raise ValueError('invalid OHLC order')
            prior=previous if previous is not None else row['open']
            flags=[]
            if previous is not None and abs(row['close']/previous-1)>.15:
                flags.append('UNRESOLVED_RAW_DISCONTINUITY')
                jumps.append({'security_id':code,'date':day,'previous_close':previous,'close':row['close'],
                              'raw_return':row['close']/previous-1})
            payload={key:row[key] for key in ('open','close','high','low')}
            payload.update(trade_date=day,volume_provider_raw=row.get('volume'),
                           limit_up=round(prior*1.1,2),limit_down=round(prior*.9,2),suspended=False,
                           limits_status='ASSUMED_MAINBOARD_10PCT_UNVERIFIED',
                           suspension_status='ASSUMED_NOT_SUSPENDED_UNVERIFIED',quality_flags=flags)
            records.append({'record_id':f'{code}:{day}:raw','fact_key':f'{code}:{day}:bar',
                            'security_id':code,'kind':'bar','event_at':day+'T15:00:00+08:00',
                            'public_at':day+'T15:01:00+08:00','available_at':day+'T17:00:00+08:00','payload':payload})
            previous=row['close']
        sources.append({'security_id':code,'source':body['meta']['source'],'meta':body['meta'],
                        'normalized_capture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'rows':len(rows),'missing_dates':sorted(set(days)-seen)})
    assumptions=['daily availability reconstructed at 17:00; not measured historical arrival',
                 '10% price boundaries reconstructed from prior raw close; not legal limits',
                 'suspension assumed false; historical trading status unverified',
                 'cash dividends/share actions not modeled; observed raw discontinuities audited separately',
                 'six surviving securities form a diagnostic sample, not a historical market universe',
                 '20bps default one-way cost proxy; no verified queue/capacity/slippage model']
    return {'dataset_id':'captured_raw_mainboard_2024_2026_six','evidence_level':'REAL_PRICE_ENGINEERING_ONLY',
            'provenance':{'source':'captured a-share-data raw price adapter','sources':sources,
                          'assumptions':assumptions,'raw_discontinuities':jumps,'volume_unit':'unverified provider raw'},
            'sessions':sorted(days),'records':records}


def summarize(data,report):
    config=report['manifest']['config']
    start,end=parse_time(config['start']),parse_time(config['end'])
    initial=Decimal(config.get('initial_cash','100000'))
    cash=initial;positions={};curve=[];exposure=[];index=0
    fills=report['fills']
    bars={(row['security_id'],row['payload']['trade_date']):row['payload'] for row in data['records']}
    flags={(item['security_id'],item['date']):item for item in data['provenance']['raw_discontinuities']}
    for day in data['sessions']:
        close_at=parse_time(day+'T17:00:00+08:00')
        if not start<=close_at<=end:
            continue
        open_at=parse_time(day+'T09:30:00+08:00')
        for (security,event_day),item in flags.items():
            if event_day==day:
                exposure.append(item|{'held_before_open':positions.get(security,0),
                                     'same_day_fill_count':sum(f['security_id']==security and parse_time(f['execution_at'])==open_at for f in fills)})
        while index<len(fills) and parse_time(fills[index]['execution_at'])<=close_at:
            fill=fills[index];index+=1;cash=Decimal(fill['cash_after'])
            key=fill['security_id']
            positions[key]=positions.get(key,0)+(fill['quantity'] if fill['action']=='BUY' else -fill['quantity'])
        equity=cash+sum((quantity*Decimal(str(bars[(security,day)]['close'])) for security,quantity in positions.items() if quantity),Decimal(0))
        curve.append({'date':day,'cash':str(cash),'equity':str(equity),'positions':{key:value for key,value in positions.items() if value}})
    if not curve or Decimal(curve[-1]['equity'])!=Decimal(report['account']['equity']):
        raise ValueError('daily equity does not match engine final account')
    peak=initial;dd=Decimal(0)
    for row in curve:
        equity=Decimal(row['equity']);peak=max(peak,equity);dd=max(dd,(peak-equity)/peak)
    monthly=[];prior=initial
    for month in sorted({row['date'][:7] for row in curve}):
        final=Decimal(next(row for row in reversed(curve) if row['date'].startswith(month))['equity'])
        monthly.append({'month':month,'return_pct':float((final/prior-1)*100),'end_equity':str(final)})
        prior=final
    fees=sum((Decimal(fill['cost']) for fill in fills),Decimal(0))
    exposures=[(Decimal(row['equity'])-Decimal(row['cash']))/Decimal(row['equity']) for row in curve]
    annual_segments=[];segment_initial=initial
    for year in sorted({row['date'][:4] for row in curve}):
        part=[row for row in curve if row['date'].startswith(year)]
        final=Decimal(part[-1]['equity'])
        annual_segments.append({'year':year,'start_equity':str(segment_initial),'end_equity':str(final),
                                'carryover_return_pct':float((final/segment_initial-1)*100)})
        segment_initial=final
    affected=any(row['held_before_open'] or row['same_day_fill_count'] for row in exposure)
    return {'result_quality':'KNOWN_DISCONTINUITY_EXPOSURE' if affected else 'EXPLORATORY_UNVERIFIED_ACTIONS',
            'metrics':{'initial_cash':str(initial),'final_equity':curve[-1]['equity'],
                       'price_pnl_return_pct':float((Decimal(curve[-1]['equity'])/initial-1)*100),
                       'max_daily_close_drawdown_pct':float(dd*100),'fees':str(fees),
                       'average_daily_close_exposure_pct':float(sum(exposures)/len(exposures)*100),
                       'max_daily_close_exposure_pct':float(max(exposures)*100),
                       'fill_count':len(fills),'buy_fills':sum(f['action']=='BUY' for f in fills),
                       'sell_fills':sum(f['action']=='SELL' for f in fills),'sessions':len(curve)},
            'order_status_counts':dict(Counter(row['status'] for row in report['orders'])),
            'fills_by_security':dict(Counter(row['security_id'] for row in fills)),
            'discontinuity_exposure':exposure,'annual_segments':annual_segments,'monthly':monthly,'equity_curve':curve}


def save_summary(root,summary):
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    with (root/'equity.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['date','cash','equity','positions']);writer.writeheader()
        for row in summary['equity_curve']:writer.writerow(row|{'positions':canonical(row['positions'])})


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run frozen-rule exploratory 2025-2026 backtests')
    parser.add_argument('--capture-dir',required=True)
    parser.add_argument('--plan',default='experiments/a-share-2025-2026.json')
    parser.add_argument('--output',required=True)
    parser.add_argument('--cost-bps',default='20')
    parser.add_argument('--engineering',action='store_true',required=True)
    args=parser.parse_args(argv)
    plan=json.loads(Path(args.plan).read_text())
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    data=build_dataset(args.capture_dir,plan['price_probe_securities'])
    dataset=out/'dataset.json';dataset.write_text(canonical(data))
    results={}
    for window in plan['runs']:
        print('Running '+window['id'],flush=True)
        config={key:window[key] for key in ('start','end','initial_cash')}
        config.update(cost_bps=args.cost_bps,snapshot_bar_limit=120)
        report=run(dataset,config,RuleAgent(Skill()),out/window['id'])
        if report['status']!='COMPLETED_ENGINEERING' or not report['verify_gate']['exploratory_backtest_allowed']:
            raise ValueError('hard verification failure; inspect '+window['id']+'/report.json')
        summary=summarize(data,report);save_summary(out/window['id'],summary)
        results[window['id']]={key:value for key,value in summary.items() if key!='equity_curve'}
        print(json.dumps({'window':window['id'],'metrics':summary['metrics'],'result_quality':summary['result_quality'],'discontinuity_exposure':summary['discontinuity_exposure']},ensure_ascii=False),flush=True)
    combined={'status':'EXPLORATORY_COMPLETED','strategy':'frozen trend-pullback seed; no optimization or RSI comparison',
              'skill':Skill().to_dict(),'evidence_level':data['evidence_level'],
              'assumptions':data['provenance']['assumptions'],'runs':results}
    (out/'summary.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
