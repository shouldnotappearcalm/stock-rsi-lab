"""Conditional exact price lattice from binary32 cells, never trading state."""
from fractions import Fraction
import math
import struct

GUARD=Fraction(1,2**40)
def ratio_text(q):return str(q.numerator)+'/'+str(q.denominator)
def floor(q):return q.numerator//q.denominator
def ceil(q):return -((-q.numerator)//q.denominator)


def cell(value,allow_zero=False):
    if type(value) is not float or not math.isfinite(value) or value<0 or value==0 and not allow_zero:
        raise ValueError('finite positive binary32 required, volume may be zero')
    try:encoded=struct.pack('<f',value)
    except (OverflowError,struct.error) as exc:raise ValueError('binary32 range required') from exc
    if struct.unpack('<f',encoded)[0]!=value:raise ValueError('exact stored binary32 required')
    bits=struct.unpack('<I',encoded)[0]
    if value==0:return Fraction(0),Fraction(1,2**150)
    if bits>=0x7f7fffff:raise ValueError('finite neighboring binary32 cells required')
    current=Fraction.from_float(value)
    previous=Fraction.from_float(struct.unpack('<f',struct.pack('<I',bits-1))[0])
    following=Fraction.from_float(struct.unpack('<f',struct.pack('<I',bits+1))[0])
    return (previous+current)/2,(current+following)/2


def cent_price(value,factor):
    p0,p1=cell(value);f0,f1=cell(factor)
    lo=p0/f1*(1-GUARD);hi=p1/f0*(1+GUARD);low=ceil(lo*100);high=floor(hi*100)
    result={'status':'NO_CENT_PRICE' if high<low else 'AMBIGUOUS_CENT_PRICE','lower':ratio_text(lo),'upper':ratio_text(hi),
        'first_cent':low,'last_cent':high,'value':None}
    if low==high and low>0:result.update(status='UNIQUE_POSITIVE_CENT',value=f'{low//100}.{low%100:02d}')
    return result


def volume_interval(value,factor,scale):
    if type(scale) is not int or scale not in (1,100):raise ValueError('only frozen volume unit scales1/100')
    v0,v1=cell(value,allow_zero=True);f0,f1=cell(factor)
    return v0*f0*scale*(1-GUARD),v1*f1*scale*(1+GUARD)
