from datetime import datetime, timedelta, timezone
import re

"""
represent each time interval (e.g. 1 day)
as a row of characters.
Each character represents subinterval of the entire interval and depents on
total array of entries whose timestamp falls into that subinterval.
These entries are fed into some sort of accumulator and once complete the value of the accumulator represented by a symbol.

At the very least, there should be a way to represent subintervals that do not have any entries from subintervals with entries.

Examples of accumulators:
a) count relevant entries
b) sum values of relevant entries
c) form bitmask of events seen in that entries

Each accumulator, in addition to holding a value, must also have "uninitialized" state, which represents situation when no entries at all were detected in its respective time range. "Initialized/Empty" state means that there were entries, but no relevant entries to update the state.

"""

class Accumulator:
    """
    Base class, but can be used in itself for simple seen/unseen functionality
    Represents a cell (subinterval) in a row (interval) of a timeline.
    """

    class Context:
        # called for each entry of the subinterval
        def process(self, entry):
            pass
        # called once in the end of the row to print row "legend"
        # best if not needed
        def format(self):
            return ''

    """
    Context is accumulator for entire parent row.
    All accumulators of same row share context and can update it.
    For example, track min/max for entire row to scale the resulst when
    the row is dumped.
    """
    contextType=Context

    def __init__(self, context):
        assert type(context)==self.contextType
        self.context=context
        self.initialized=False

    def __add__(self,entry):
        return self.update(entry)
        
    def update(self,entry):
        self.initialized=True
        return self

    def __str__(self):
        return self.format()

    def format(self):
        if self.initialized: return '-'
        else: return ' '

class Counted:
    """
    Most generic aggregator.
    Calculates total number of updates together with first and last updates.
    """
    def __init__(self):
        self.count=0
        self.first=None
        self.last=None

    def update(self, value):
        if isinstance(value,Counted):
            if self.first==None: self.first=value.first
            self.last=value.last
            self.count+=value.count
        else:
            if self.first==None: self.first=value
            self.last=value
            self.count+=1
        return self

class Ordered(Counted):
    """
    Aggregator for values that can be compared with < and >.
    In addition to data collected by Counted, collects min and max value.
    """
    def __init__(self):
        super().__init__()
        self.min=None
        self.max=None

    def update(self,value):
        super().update(value)
        if isinstance(value,Ordered):
            if self.min==None or ( value.min!=None and value.min<self.min): self.min=value.min
            if self.max==None or (value.max !=None and value.max>self.max): self.max=value.max
        else:
            if self.min==None or value<self.min: self.min=value
            if self.max==None or value>self.max: self.max=value
        return self



class Additive(Ordered):
    """
    For values that can be added together with a +.
    Additionally accumulates total sum of entries.
    """
    def __init__(self):
        super().__init__()
        self.sum=None

    def update(self, value):
        super().update(value)
        if self.sum==None: self.sum=value
        else: self.sum+=value
        return self


    def __repr__(self):
        return f"{__name__}({self.min}..{self.max}/{self.count})"

class Stats(Additive):
    def __init__(self):
        super().__init__()
        self.sum2=0.0

    def update(self, value):
        v=float(value)
        super().update(v)
        self.sum2+=v*v
        return self

    def average(self):
        return self.sum/self.count

    # √(1/n · Σ(xi-Σxi/n)²) = √[(Σxi²)/n-μ²]
    def stdev(self):
        return (self.sum2/self.count-self.average()**2)**0.5
        pass

# Accumulators

class BitmaskAccum(Accumulator):
    """
    accumulate small set of strings in a form of bitmask
    BitmaskContext contains seentoday array which shows which string corresponds to which bit
    entry must be a simple string
    """
    class BitmaskContext(Accumulator.Context):
        """
        contains seentoday array which shows which string corresponds to which
        bit To be used in conjunction with BitmaskAccum
        """
        def __init__(self):
            self.seentoday=[]
        def process(self, entry):
            "return index in seentoday array"
            try:
                i=self.seentoday.index(entry)
                return i
            except ValueError:
                i=len(self.seentoday)
                self.seentoday.append(entry)
                return i
        def format(self):
            j=','
            if len(self.seentoday)>0 and max([len(e) for e in self.seentoday])<=1: j=''
            return ':'+(j.join(self.seentoday))

    contextType=BitmaskContext

    def __init__(self, context):
        super().__init__(context)
        self.mask=0

    def update(self, entries):
        super().update(entries)
        for e in entries:
            if e=='': continue
            self.mask |= 1<<self.context.process(e)

    def format(self):
        if self.mask>15: return '≡'
        if self.mask>3: return "%1x"%self.mask
        if self.mask>0: return "?▀▄█"[self.mask]
        return super().format()


class StatsAccum(Accumulator):
    class StatsContext(Accumulator.Context):
        def __init__(self):
            self.stats=Stats()
            self.cell_duration_s=None
        def process(self,entry):
            super().process(entry)
            self.stats.update(entry)

    contextType=StatsContext
    def __init__(self,context):
        super().__init__(context)
        self.stat=Stats()

    def update(self, number):
        super().update(number)
        self.context.process(number)
        self.stat.update(number)

    def format(self):
        if self.stat.count==0: return super().format()
        return ("%02d"%int(self.stat.max))[0]

# "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
# SHORT_GRAYSCALE=" .:-=+*#%@"
# LONG_GRAYSCALE=' .\'`^",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$'

class DataRow:
    """
    Serves as a base class, but may be used by itself
    intended to be initialized once and then reused for each subsequent rows of
    a summary
    """
    def __init__(self,length,**kwargs):
        self.start=None
        self.finish=None
        self.accumType=Accumulator
        self.duration=None
        self.duration_s=None
        self.length=length
        self.context=None
        self.render=None
        self.__dict__.update(kwargs)

    def setDuration(self,d:timedelta):
        self.duration=d;
        self.duration_s=d.total_seconds();

    def reset(self, ts):
        self.render.setRangeFor(ts,self)
        # initialize common context
        self.context=self.accumType.contextType()
        self.context.parentRow=self
        self.context.bucket_duration_s=self.duration_s/self.length
        # all buckets share row context
        self.buckets=[self.accumType(self.context) for i in range(self.length)]

    # can also be used to check if timestamp belongs to the interval
    def _getAccumFor(self, timestamp):
        if timestamp<self.start or timestamp>=self.finish: return None
        d=int((timestamp-self.start).total_seconds()*self.length/self.duration_s)
        self.buckets[d].initialized=True
        return self.buckets[d]

    def process(self,ts,entry=None):
        if self.start==None:
            # first time called; initialize and print block header
            self.reset(ts)
            self.render.begin()
        a=self._getAccumFor(ts)
        if a==None:
            # need new row
            # first output current row
            self.render.printRow()
            # then start a new one
            self.reset(ts)
            a=self._getAccumFor(ts)
        a.update(entry)

class Renderer:

    # renderer does 2 kinds of timezone processing:
    # 1) it can assign timezone to the timestamps that do not have it explicitly
    ITZ=None # if input time stamp's timezone is not explicit, use this one
    # 2) convert timezone for output
    OTZ=None # output time zone, None=local

    # called when the very first row is ready to accept data
    # interval is reset, but buckets are empty
    # here is the place to print main header and initialize continuity tracking
    def begin(self):
        pass
    # called when row is ready to be printed. This must be overridden in
    # subclasses and implement different row headers, decision to insert
    # intermediate block headers, etc.
    def printRow(self):
        pass
    # called by parser at the end of the file
    def end(self):
        if self.dataRow.start!=None:
            self.printRow()
    # called by parser for each found entry
    def process(self,ts,entry):
        if ts.tzinfo==None:
            ts=ts.replace(tzinfo=self.ITZ)
        ts=ts.astimezone(self.OTZ)
        self.dataRow.process(ts,entry)
    # calculate beginning of a row interval for a givent ts.
    # override when necessary to round to nearest day, hour, etc.
    def startFor(self,ts):
        return ts
    def setRangeFor(self,ts,dr:DataRow):
        start=self.startFor(ts)
        dr.start=start
        # this may be overridden to be less than full duration
        # e.g. month view would have reserved space for 31 days, but only days
        # of current month will be actually filled
        dr.finish=start+self.rowDuration
        dr.setDuration(self.rowDuration)


# use console to visualize data
# each cell in a row is 1xN symbols, usually N=1
class IntervalPrinter(Renderer):
    SCALEFILLER='·'
    # terminal-specific
    def nocolor(self):
        self.ATTR_BLOCKHEADER=''
        self.ATTR_ROWHEADER=''
        self.ATTR_SCALE=''
        self.ATTR_NORMAL=''

    ATTR_BLOCKHEADER='\x1b[92m'
    ATTR_ROWHEADER='\x1b[36m'
    ATTR_SCALE='\x1b[90m'
    ATTR_NORMAL='\x1b(B\x1b[m'

    def __init__(self,duration,length,accumType=Accumulator):
        # super().__init__(duration,length,accumType)
        self.rowDuration=duration
        self.dataRow=DataRow(length,render=self,accumType=accumType)
        self.dataRow.setDuration(self.rowDuration)
        self.scale=None
        self.lastStart=None
        self.ROWHEADERWIDTH=len(self._formatRowHeader(datetime.now()))

    def makeScale(self, tryTickCount):
        l=self.dataRow.length
        s=0 # no hour marks

        maxticks=tryTickCount[0]
        for nt in tryTickCount:
            if l//nt>=4:
                s=nt
                break
        hdr=""
        step=maxticks/s
        for i in range(s):
            pos=int(l*(i*step/float(maxticks)))
            hdr=hdr+(self.SCALEFILLER * (pos-len(hdr)))+("%d"%(int(i*step)))
        hdr=hdr+(self.SCALEFILLER * (l-len(hdr)))
        self.scale=hdr

    def begin(self):
        self._printBlockHeader(self.dataRow.start)

    # what a separator between larger blocks looks like
    def _printBlockHeader(self,start):
        self.lastStart=start
        bh=self._formatBlockHeader(start)
        if self.scale==None:
            print(bh)
        else:
            pad=self.ROWHEADERWIDTH-len(bh)
            if pad>=0:
                print(self.ATTR_BLOCKHEADER+bh+(' '*pad)+self.ATTR_SCALE+self.scale+self.ATTR_NORMAL)
            else:
                print(self.ATTR_BLOCKHEADER+bh)
                print( self.ATTR_BLOCKHEADER+(' '*self.ROWHEADERWIDTH)+self.ATTR_SCALE+self.scale+self.ATTR_NORMAL)

    def _formatBlockHeader(self,start):
        return "%s"%start;

    # first blockheader always printed regardless
    def _isBlockHeaderNeeded(self):
        return False

    def printRow(self):
        if self._isBlockHeaderNeeded():
            self._printBlockHeader(self.dataRow.start)

        rh=self._formatRowHeader(self.dataRow.start)

        body=''.join([bucket.format() for bucket in self.dataRow.buckets])
        legend=''
        if self.dataRow.context!=None: legend=self.dataRow.context.format()

        print(self.ATTR_ROWHEADER+rh+self.ATTR_NORMAL+body+self.ATTR_SCALE+legend+self.ATTR_NORMAL)

class MinutePrinter(IntervalPrinter):
    SCALEFILLER='"'
    def __init__(self,length, accumType):
        super().__init__(timedelta(seconds=60),length, accumType)
        self.makeScale([60, 12, 6, 4, 2, 1])
        self.lastBlockHeader=None

    def startFor(self,ts):
        return ts.replace(second=0,microsecond=0)

    def _formatBlockHeader(self,start):
        h=""
        if (self.lastBlockHeader==None
        or self.lastBlockHeader.day!=start.day
        or self.lastBlockHeader.month!=start.month
        or self.lastBlockHeader.year!=start.year):
            h=start.strftime("%Y-%m-%d %H:%M")
        else:
            h=start.strftime("%H:")
        self.lastBlockHeader=start
        return h

    def _formatRowHeader(self, ts):
        return ts.strftime(" :%M'")

    def _isBlockHeaderNeeded(self):
        return (self.lastStart.year!=self.dataRow.start.year
            or self.lastStart.month!=self.dataRow.start.month
            or self.lastStart.day!=self.dataRow.start.day
            or self.lastStart.hour!=self.dataRow.start.hour)

class HourPrinter(IntervalPrinter):
    SCALEFILLER="'"
    def __init__(self,length, accumType):
        super().__init__(timedelta(seconds=3600),length, accumType)
        self.makeScale([60, 12, 6, 4, 2, 1])

    def startFor(self,ts):
        return ts.replace(minute=0,second=0,microsecond=0)

    def _formatBlockHeader(self,start):
        return start.strftime("%Y-%m-%d")

    def _formatRowHeader(self, ts):
        return ts.strftime("%H:")

    def _isBlockHeaderNeeded(self):
        return (self.lastStart.year!=self.dataRow.start.year
            or self.lastStart.month!=self.dataRow.start.month
            or self.lastStart.day!=self.dataRow.start.day)

# each row is a day
class DayPrinter(IntervalPrinter):
    def __init__(self,length, accumType):
        super().__init__(timedelta(days=1),length,accumType)
        self.makeScale([24,12,8,4,2,1])

    def startFor(self,ts):
        return ts.replace(hour=0,minute=0,second=0,microsecond=0)

    def _formatBlockHeader(self,start):
        return start.strftime("%Y-%b")

    def _formatRowHeader(self, ts):
        return ts.strftime("%d|")

    def _isBlockHeaderNeeded(self):
        return (self.lastStart.year!=self.dataRow.start.year
            or self.lastStart.month!=self.dataRow.start.month)

# each row is a month
class MonthPrinter(IntervalPrinter):
    def __init__(self,length, accumType):
        super().__init__(timedelta(days=31),length,accumType)
        self.makeMonthScale([1,2,[4,5],[9,10]])

    def makeMonthScale(self, trySteps):
        l=self.dataRow.length

        sm=datetime(year=2000,month=1,day=1)
        dur_s=self.rowDuration.total_seconds()
        for stp in trySteps:
            if type(stp)==int: stp=[stp,stp]
            pd=1
            hdr="%d"%pd
            s=stp[0]
            while (nd:=pd+s)<=31:
                ni=int(l*(sm.replace(day=nd)-sm).total_seconds()/dur_s)
                if ni-len(hdr)<1:
                    break
                hdr+=self.SCALEFILLER *(ni-len(hdr)) + "%d"%nd
                pd=nd
                s=stp[-1]
            else:
                self.scale=hdr+(self.SCALEFILLER * (l-len(hdr)))
                break

    def startFor(self,ts):
        assert False

    def setRangeFor(self,ts,dr:DataRow):
        start=ts.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        dr.start=start
        dr.setDuration(self.rowDuration)
        for ml in [28,29,30,31]:
            dr.finish=start+timedelta(ml)
            if dr.finish.day==1: break
        else:
            assert False

    def _formatBlockHeader(self,start):
        return start.strftime("%Y")

    def _formatRowHeader(self, ts):
        return ts.strftime(" %b|")

    def _isBlockHeaderNeeded(self):
        return (self.lastStart.year!=self.dataRow.start.year)

# TODO? WeekPrinter? Monthprinter? YearPrinter? MinutePrinter

def openLogFile(logname):
    if logname[-3:]=='.gz':
        import gzip
        return gzip.open(logname,"rb")
    else:
        return open(logname,"rb")

def SummarizeLogFile(logname:str, parser, r:Renderer):
    with openLogFile(logname) as file:
        while True:
            line=file.readline()
            line=line.decode('utf-8')
            if not line: break
            # log-specific parsing
            l=line.rstrip("\r\n")
            parser(l,r)
        r.end()

# finds anything that looks like iso timestamp in the string and if found
# passes entire string as an entry
RE_ISOTS=re.compile(r"""
  (?P<date>  \d{4} (?: [-/] \d{2} ){2} ) # date
  (?: \S | \s+ ) # separator (seen spaces, Z, T)
    (?: (?P<hours> \d{1,2} )  # hours (fromisoformat allows just hours)
    (?: : (?P<minutes>  \d{1,2} )    # minutes
    (?: : (?P<seconds>  \d{1,2} )    # seconds
    (?P<fraction> \.\d* )?)?)?)? # fraction seconds, must have exactly 3 digits when present (weird, because format displays 6 places)
  # if there are fractions, space between time and tz is prohibited,
  # otherwise (no fractions or seconds), permitted
  (?: \s*
    (?P<tzh> [-+] \d{2})
    :?  # must have ':' for fromisoformat to work
    (?P<tzm> (?: \d{2} )? ) )? # TZ
""", re.VERBOSE)

def matchIso(s:str)->datetime :
    m=re.search(RE_ISOTS,s);
    if m==None: return None
    d,hr,mn,sc,f,zh,zm=m.groups('')
    d=d.replace('/','-')
    if len(hr)<2:  hr='0'*(2-len(hr))+hr
    if len(mn)<2:  mn='0'*(2-len(mn))+mn
    if len(sc)<2:  sc='0'*(2-len(sc))+sc
    us=0
    if len(f)>0:
        us=int(float(f+'0')*1e6)
        f=(f+'0'*(4-len(f)))[0:4]
    if zh!='':
        if zm=='': zm='00'
        zm=":"+zm
    normalizedTs=f"{d} {hr}:{mn}:{sc}{f}{zh}{zm}"
    iso=datetime.fromisoformat(normalizedTs)
    if iso!=None and us>0:
        iso=iso.replace(microsecond=us)
    return iso


def parseIso(s : str, r : Renderer):
    ts=matchIso(s)
    if ts!=None: r.process(ts,s)

# 127.0.0.1 - - [15/Jan/2025 15:01:59] "GET / HTTP/1.1" 200 -
#MONTHS=['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
MONTHS=[ datetime(year=1,month=i+1,day=1).strftime("%b").lower() for i in range(12)]
def parsePythonWeb(s:str, r:Renderer):
    m=re.search('^(\\S+)\\s+(\\S+)\\s+(\\S+)\\s+\\[(\\d+)/(.*)/(\\d+) (\\d+):(\\d+):(\\d+)\\] *(.*)',s)
    if m!=None:
        try:
            (ip,_,_,d,mname,y,h,m,s,rq)=m.groups()
            mnum=MONTHS.index(mname.lower())
            ts=datetime(year=int(y),month=int(mnum)+1, day=int(d), hour=int(h), minute=int(m), second=int(s))
            r.process(ts,[ip,rq])
        except:
            pass

class WebAccum(StatsAccum):
    IGNOREIP=['127.0.0.1']
    def update(self,data):
        (ip,rq)=data
        if ip in self.IGNOREIP : return
        m=re.search('"(\\S+)\\s+(\\S+)\\s*(\\S*)"\\s*(\\d+)',rq)
        if m!=None:
            (verb,urn,ver,code)=m.groups()
            super().update(int(code))

    def format(self):
        if not self.initialized: return ' '
        if self.stat.count==0: return '-'
        n=self.stat.max
        if n==0: return '?'
        return "%d"%(n//100)

# must receive entry as a pair of (prio:int, symbol:string)
# symbol represents event, prio its importance. Events with higher importance
# override events with lower importance
# using an Ordered aggregator with an element of pair (prio,symbol) and using
# min or max's second element as a format would work too, except that prio
# would have to be different for all entries and the count applies to all the
# entries, not just those with the highest priority
class PriorityEventsAccum(Accumulator):
    prio=-999999
    symb='?'
    count=0
    def __repr__(self):
        return f"{__name__}(p={self.prio},s={self.symb},#={self.count})"
    def update(self,entry):
        super().update(entry)
        try:
            prio,symb=entry
            if prio>self.prio:
                self.symb=symb
                self.prio=prio
                self.count=0
            elif prio==self.prio:
                self.symb=symb # of equal priorities use last symbol
                self.count+=1
            # print("%s %d %s"%(entry,self.prio,self.symb))
        except ValueError:
            pass
    def format(self):
        if self.initialized: return self.symb
        else: return ' '

if __name__=='__main__':
    import sys
    import shutil
    cols=shutil.get_terminal_size((80,24)).columns
    NBUCKETS=cols-10
    IntervalPrinter.nocolor(IntervalPrinter)
    renderer=DayPrinter
    option=None
    for arg in sys.argv[1:]:
        if option==None and arg[0]=='-':
            o=arg[1:]
            if o in ['w','b']:
                option=o
            elif o=='m' :render=MonthPrinter
            elif o=='d' :render=DayPrinter
            elif o=='H' :render=HourPrinter
            elif o=='M' :render=MinutePrinter
            elif o=='u' :Renderer.ITZ=timezone.utc
            elif o=='ou' :Renderer.OTZ=timezone.utc
            else: print("unknown option %s"%arg)
        elif option!=None:
            if   option=='w': NBUCKETS+=int(arg)
            elif option=='b': NBUCKETS=int(arg)
            option=None
        else:
            SummarizeLogFile(arg, parseIso,  renderer(NBUCKETS,Accumulator))
