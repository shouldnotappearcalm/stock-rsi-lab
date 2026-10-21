"""Source questions only; no corporate economics inferred and no portfolio replay."""
from pathlib import Path
from decimal import Decimal
import hashlib,json
BASE=Path('/Users/calm/dev/git_repo/stock-rsi-lab/data/local/qlib-pre2026-research-20261015')
REPO=Path('/Users/calm/dev/git_repo/stock-rsi-lab-worktrees/pead')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=BASE/'price-delay-raw-dev-20261021';m=json.loads((p/'manifest.json').read_text())
questions={'noncash':[],'unknown_economics':[],'adjustments_without_distribution':[]};bars=0
for code,h in m['per_code_sha256'].items():
 f=p/'codes'/(code+'.json');assert sha(f)==h;d=json.loads(f.read_text());assert d['window']==['2023-12-29','2025-12-31'];bars+=len(d['bars']);ex={r['dividOperateDate'] for r in d['distributions']}
 for r in d['distributions']:
  # dividCashStock is a descriptive text column, never a numeric ratio.
  if any(r[k] and Decimal(r[k])>0 for k in ('dividStocksPs','dividReserveToStockPs')):questions['noncash'].append({'instrument':code,'record':r})
  display=r.get('dividCashStock','');cash=Decimal(r['dividCashPsBeforeTax']) if r['dividCashPsBeforeTax'] else None;stock=Decimal(r['dividStocksPs']) if r['dividStocksPs'] else None
  compiler_cash_only=(cash is not None and cash>0 and stock==0 and display.startswith('10派') and '送' not in display and '转' not in display and not r['dividStockMarketDate'])
  if cash is None or stock is None or (not r['dividReserveToStockPs'] and not compiler_cash_only):questions['unknown_economics'].append({'instrument':code,'record':r})
 for r in d['adjustments']:
  if r['dividOperateDate'] not in ex:questions['adjustments_without_distribution'].append({'instrument':code,'record':r})
report={'status':'RAW_CAPTURE_COMPLETE_CORPORATE_QUESTIONS_NOT_EVENT_ADMISSION','manifest_sha256':sha(p/'manifest.json'),'method_sha256':sha(Path(__file__)),'names':m['names'],'bars':bars,'distributions':m['totals']['distributions'],'questions':questions,'account_returns_computed':False,'new_2026_market_queries':False,'objective_achieved':False}
(REPO/'experiments/qlib/price-delay-raw-source-corporate-questions.json').write_text(json.dumps(report,indent=2)+'\n')
(REPO/'experiments/qlib/price-delay-pre2026-raw-source-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print({k:len(v) for k,v in questions.items()})
