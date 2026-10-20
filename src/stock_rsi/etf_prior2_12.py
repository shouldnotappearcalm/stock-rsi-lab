"""Fixed prior2-12 index-style signal; an 11-month return ending one month ago."""
from decimal import Decimal as D
from stock_rsi.etf_relative_replay import CODES,Relative12Month

class Prior2To12(Relative12Month):
    """Uses the same exact incremental total-return book and visible month ends."""
    def observe_close(self,day,closes,cashflows):
        result=super().observe_close(day,closes,cashflows)
        if result is None:return None
        window=self.monthends[-13:]
        start,end=window[0],window[-2]
        scores={c:end[1][c]/start[1][c]-1 for c in CODES}
        result.update(leader=sorted(CODES,key=lambda c:(-scores[c],c))[0],
            scores={c:str(D(v.numerator)/D(v.denominator)) for c,v in scores.items()},
            scores_exact_ratio={c:[str(v.numerator),str(v.denominator)] for c,v in scores.items()},
            signal='PRIOR2_TO12_EXCLUDING_LATEST_COMPLETE_MONTH',
            signal_start_monthend=start[0].isoformat(),signal_end_monthend=end[0].isoformat(),
            excluded_monthend=window[-1][0].isoformat(),return_month_count=11)
        return result
