"""One signed market-beta adaptation, with no execution-day price inputs."""
import math,statistics
from stock_rsi.low_risk_monthly import complete_month_ends
from stock_rsi.prior_close_orders import AsOfPrices
from stock_rsi.return_families import choose_development_lead
FAMILIES=('low_beta60',)
CONTROL='low_vol60_control'
MARKET='SH000905'
START,END='2024-01-02','2025-12-31'


def beta60(stock_closes,market_closes):
 if len(stock_closes)!=61 or len(market_closes)!=61:raise ValueError('61 consecutive monthly closes required')
 if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (*stock_closes,*market_closes)):return None
 ys=[b/a-1 for a,b in zip(stock_closes,stock_closes[1:])];xs=[b/a-1 for a,b in zip(market_closes,market_closes[1:])]
 if any(not math.isfinite(x) for x in (*ys,*xs)):return None
 xb=statistics.mean(xs);yb=statistics.mean(ys);xx=math.fsum((x-xb)**2 for x in xs);yy=math.fsum((y-yb)**2 for y in ys)
 if not math.isfinite(xx+yy) or min(xx,yy)<=1e-24:return None
 beta=math.fsum((x-xb)*(y-yb) for x,y in zip(xs,ys))/xx;alpha=yb-beta*xb;vol=math.sqrt(12*yy/59)
 if any(not math.isfinite(v) for v in (beta,alpha,vol)):return None
 return {'beta':beta,'alpha':alpha,'volatility_annualized':vol}


def lowest_beta_decile(scores):
 if not scores or any(not math.isfinite(x) for x in scores.values()):raise ValueError('finite signed scores required')
 return tuple(sorted(scores,key=lambda c:(scores[c],c))[:max(1,len(scores)//10)])


def build_targets(snapshot,memberships,start=START,end=END):
 if start<START or start>end or end>END:raise ValueError('beta development capped at2025')
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
