"""Calendar-only extension of frozen beta60, retaining the original module unchanged.

The loop below is the frozen formation loop. Only its date-cap validation differs.
Use extend_targets to enforce the exact original 24-month byte prefix first.
"""
import json,math
from datetime import date
from stock_rsi.low_beta60 import START,END,FAMILIES,CONTROL,MARKET,beta60,lowest_beta_decile
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices


def json_bytes(value):
 return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def build_targets(snapshot,memberships,start=START,end=END,*,permitted_end):
 for value in (start,end,permitted_end):
  if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('canonical ISO date required')
 if start<START or start>end or end>permitted_end:raise ValueError('beta extension exceeds explicit cap')
 targets={k:{} for k in (*FAMILIES,'eligible_equal_weight',CONTROL)};receipts=[]
 for index,day in enumerate(snapshot.calendar):
  if not start<=day.isoformat()<=end:continue
  if index==0:raise ValueError('prior session required')
  previous=snapshot.calendar[index-1]
  if previous.strftime('%Y-%m')==day.strftime('%Y-%m'):continue
  endpoints=complete_month_ends(snapshot.calendar,previous,count=61)
  expected=(day.year,day.month-1) if day.month>1 else (day.year-1,12)
  if (previous.year,previous.month)!=expected:raise ValueError('preceding exchange month missing')
  view=AsOfPrices(snapshot,previous);market=[view.value(MARKET,'close',d.isoformat()) for d in endpoints]
  if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in market):raise ValueError('complete market month ends required')
  names=sorted(c for c,spans in memberships.items() if any(a<=previous.isoformat()<=b for a,b in spans))
  if len(names)<200:raise ValueError('historical mainboard membership unexpectedly small')
  scores={};vols={};coefficients={};excluded={}
  for c in names:
   current=[view.value(c,f,previous.isoformat()) for f in ('factor','volume','close')]
   if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in current):excluded[c]='MISSING_OR_INACTIVE_FORMATION';continue
   value=beta60([view.value(c,'close',d.isoformat()) for d in endpoints],market)
   if value is None:excluded[c]='INCOMPLETE_OR_DEGENERATE_60_MONTH_HISTORY';continue
   scores[c]=value['beta'];vols[c]=value['volatility_annualized'];coefficients[c]={'beta':value['beta'],'alpha':value['alpha']}
  if len(scores)<100 or len(scores)<.5*len(names):raise ValueError('complete60month coverage below100 and50percent')
  selected=lowest_beta_decile(scores);control_selected=lowest_beta_decile(vols)
  for name,chosen in ((FAMILIES[0],selected),('eligible_equal_weight',sorted(scores)),(CONTROL,control_selected)):
   targets[name][day.isoformat()]={'as_of':previous.isoformat(),'weights':{c:.95/len(chosen) for c in chosen}}
  receipts.append({'execution_session':day.isoformat(),'formation_asof':previous.isoformat(),'market_instrument':MARKET,
   'regression_begin_close':endpoints[0].isoformat(),'return_months':[d.strftime('%Y-%m') for d in endpoints[1:]],
   'historical_members':len(names),'eligible':len(scores),'excluded':excluded,'selected':list(selected),'scores':scores,
   'regression_coefficients':coefficients,'control_volatility_scores':vols,'control_selected':list(control_selected),
   'latest_factor_price_read':view.latest_read.isoformat()})
 return targets,receipts


def extend_targets(snapshot,memberships,reference_targets,reference_receipts,*,end,permitted_end):
 """Fail on changed historical bytes before any additional formation is queried."""
 # Validate the expanded cap even when a historical prefix would otherwise fail.
 for value in (end,permitted_end):
  if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('canonical ISO date required')
 if end<=END or end>permitted_end:raise ValueError('explicit post2025 extension within cap required')
 before,old_receipts=build_targets(snapshot,memberships,permitted_end=END)
 if len(old_receipts)!=24 or json_bytes(before)!=reference_targets or json_bytes(old_receipts)!=reference_receipts:
  raise ValueError('pre2026 target or receipt bytes differ from frozen evidence')
 targets,receipts=build_targets(snapshot,memberships,end=end,permitted_end=permitted_end)
 prefix={family:{day:t for day,t in days.items() if day<=END} for family,days in targets.items()}
 if json_bytes(prefix)!=reference_targets or json_bytes([r for r in receipts if r['execution_session']<=END])!=reference_receipts:
  raise ValueError('expanded pre2026 prefix bytes differ from frozen evidence')
 return targets,receipts
