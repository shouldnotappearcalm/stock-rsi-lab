"""Selected historical tokens only; current quote branches remain opaque bytes."""
from datetime import date
from decimal import Decimal,localcontext
import json
import re

START,END='2023-12-29','2025-12-31'
NUMBER=re.compile(rb'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')

def need(ok,message):
    if not ok:raise ValueError(message)


class JsonSlices:
    def __init__(self,body):
        need(type(body) is bytes and 0<len(body)<=1048576,'bounded byte response')
        self.b=body;self.start=self.ws(0);assignment=re.match(rb'kline_day2023\s*=\s*',body[self.start:])
        if assignment:self.start+=assignment.end()
        self.stop=self.end(self.start,0)
        tail=body[self.stop:].strip();need(tail==b'' or assignment is not None and tail==b';','exact JSON/assignment framing')
    def ws(self,i):
        while i<len(self.b) and self.b[i] in b' \r\n\t':i+=1
        return i
    def string_end(self,i):
        need(i<len(self.b) and self.b[i]==34,'JSON string required');i+=1
        while i<len(self.b):
            c=self.b[i];i+=1
            if c==34:return i
            need(c>=32,'unescaped control byte')
            if c==92:
                need(i<len(self.b),'complete string escape');e=self.b[i];i+=1
                if e==117:
                    need(len(self.b[i:i+4])==4 and all(v in b'0123456789abcdefABCDEF' for v in self.b[i:i+4]),'four hex escape digits');i+=4
                else:need(e in b'"\\/bfnrt','valid string escape')
        raise ValueError('unterminated JSON string')
    def end(self,i,depth):
        need(depth<=64,'maximum64nested JSON containers');i=self.ws(i);need(i<len(self.b),'complete JSON value');c=self.b[i]
        if c==34:return self.string_end(i)
        if c in (123,91):
            object_=c==123;closing=125 if object_ else 93;i=self.ws(i+1)
            if i<len(self.b) and self.b[i]==closing:return i+1
            while True:
                if object_:
                    i=self.ws(self.string_end(i));need(i<len(self.b) and self.b[i]==58,'object colon');i+=1
                i=self.ws(self.end(i,depth+1));need(i<len(self.b),'closed container')
                if self.b[i]==closing:return i+1
                need(self.b[i]==44,'container comma');i=self.ws(i+1)
        for literal in (b'true',b'false',b'null'):
            if self.b.startswith(literal,i):return i+len(literal)
        match=NUMBER.match(self.b,i);need(match is not None,'JSON primitive grammar');return match.end()
    def path(self,keys):
        i=self.start
        for selected in keys:
            need(self.b[i]==123,'object on selected path');p=self.ws(i+1);found=None;seen=set()
            while self.b[p]!=125:
                endkey=self.string_end(p);key=json.loads(self.b[p:endkey]);need(key not in seen,'duplicate traversed object key');seen.add(key)
                p=self.ws(endkey);need(self.b[p]==58,'selected object colon');p=self.ws(p+1);stop=self.end(p,0)
                if key==selected:found=p
                p=self.ws(stop)
                if self.b[p]==125:break
                need(self.b[p]==44,'selected object comma');p=self.ws(p+1)
            need(found is not None,'missing selected historical path');i=found
        return self.b[i:self.end(i,0)]
    @staticmethod
    def items(array):
        s=JsonSlices(array);need(s.b[s.start]==91,'historical array required');i=s.ws(s.start+1);result=[]
        while s.b[i]!=93:
            stop=s.end(i,0);result.append(s.b[i:stop]);i=s.ws(stop)
            if s.b[i]==93:break
            need(s.b[i]==44,'array comma');i=s.ws(i+1)
        return result


def numeric(token,optional=False):
    if optional and token in (b'null',b'""'):return None
    need(token.startswith(b'"') or NUMBER.fullmatch(token) is not None,'numeric scalar token only')
    value=json.loads(token) if token.startswith(b'"') else token.decode('ascii')
    need(type(value) is str,'source numeric text');number=Decimal(value);need(number.is_finite(),'finite source number')
    return number


def scale(number,multiplier):
    with localcontext() as context:
        context.prec=len(number.as_tuple().digits)+8
        return number*multiplier


def canonical(number):
    text=format(number,'f');return text.rstrip('0').rstrip('.') if '.' in text else text


def decode(body,code,sessions,on_row=None):
    s=JsonSlices(body);need(s.path(('code',))==b'0','provider success code0');result=[];previous=None
    need(sessions==sorted(set(sessions)) and all(START<=d<=END for d in sessions),'explicit frozen sessions')
    for index,tokens in enumerate(s.items(s.path(('data',code.lower(),'day')))):
        parts=s.items(tokens);need(len(parts)==6 or len(parts)>=9,'six basic or nine extended historical fields')
        need(parts[0].startswith(b'"'),'date string before any quote');day=json.loads(parts[0])
        need(type(day) is str and date.fromisoformat(day).isoformat()==day and START<=day<=END and day in sessions,'date outside frozen explicit sessions')
        need(previous is None or day>previous,'strictly increasing unique historical dates');previous=day
        n=[numeric(p) for p in parts[1:6]];o,c,h,l,v=n
        need(all(x>0 and scale(x,100)==scale(x,100).to_integral_value() for x in (o,c,h,l)),'positive integer-cent prices')
        need(l<=min(o,c)<=max(o,c)<=h,'historical OHLC range');need(v>=0 and scale(v,100)==scale(v,100).to_integral_value(),'nonnegative integer-share volume')
        turnover=numeric(parts[7],True) if len(parts)>=9 else None;amount=numeric(parts[8],True) if len(parts)>=9 else None
        need((turnover is None or turnover>=0) and (amount is None or amount>=0),'nonnegative optional activity')
        r={'date':day,'open':str(o),'close':str(c),'high':str(h),'low':str(l),'volume_lots':str(v),'volume_shares':canonical(scale(v,100)),
            'turnover_percent':None if turnover is None else str(turnover),'amount_10k':None if amount is None else str(amount),
            'amount_cny':None if amount is None else canonical(scale(amount,10000)),'source_kind':'HISTORICAL_UNADJUSTED_COMPONENTS_NOT_STATE_OR_ACCOUNT'}
        if on_row:on_row(r)
        result.append(r)
    return result


def compare(rows,original):
    dates=[r['date'] for r in rows];need(dates==sorted(set(dates)),'unique ordered control source rows');lookup={r['date']:r for r in rows}
    raw_dates=[r['date'] for r in original];need(raw_dates==sorted(set(raw_dates)),'unique ordered original rows')
    checked=matched=volume=trade=amount_checked=amount_match=amount_missing=excluded=0;bad=[];amount_bad=[];missing=[]
    for raw in original:
        need(raw['tradestatus'] in ('0','1'),'explicit original trading state')
        if raw['tradestatus']!='1':excluded+=1;continue
        trade+=1;at=raw['date']
        if at not in lookup:missing.append(at);continue
        row=lookup[at];fields=[]
        for k in ('open','close','high','low'):
            checked+=1
            if Decimal(row[k])==Decimal(raw[k]):matched+=1
            else:fields.append(k)
        if Decimal(row['volume_shares'])==Decimal(raw['volume']):volume+=1
        else:fields.append('volume_shares')
        if fields:bad.append({'date':at,'fields':fields})
        if row['amount_cny'] is None:amount_missing+=1
        else:
            amount_checked+=1
            if Decimal(row['amount_cny'])==Decimal(raw['amount']):amount_match+=1
            else:amount_bad.append({'date':at,'source_cny':row['amount_cny'],'original_cny':raw['amount']})
    gate=trade>0 and not missing and not bad and checked==matched==4*trade and volume==trade
    return {'raw_rows_counted':len(original),'trading_rows_checked':trade,'nontrading_rows_excluded':excluded,'returned_rows':len(rows),
        'missing_trading_dates':missing,'price_cells_checked':checked,'matched_price_cells':matched,'volume_rows_matched':volume,'mismatches':bad,
        'amount_rows_compared':amount_checked,'amount_exact_matches':amount_match,'amount_missing_rows':amount_missing,'amount_mismatches':amount_bad,
        'price_volume_gate_passed':gate,'all_components_exactly_corroborated':gate and amount_checked==amount_match==trade,'account_admitted':False}
