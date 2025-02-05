from datetime import datetime, timedelta
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
        duration_s=0
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

    def update(self,entry):
        self.initialized=True

    def format(self):
        if self.initialized: return '-'
        else: return ' '

class Stats:
    def __init__(self):
        self.min=float('inf')
        self.max=float('-inf')
        self.sum=0.0
        self.count=0
        self.sum2=0.0
        self.first=None
        self.last=None

    def update(self, value):
        value=float(value)
        if value>self.max: self.max=value
        if value<self.min: self.min=value
        if self.first==None: self.first=value
        self.last=value
        self.count+=1
        self.sum+=value
        self.sum2+=value*value
        return self

    def mergeWith(self,other):
        if other.count==0 : return
        if other.min<self.min: self.min=other.min
        if other.max>self.max: self.max=other.max
        self.last=other.last
        self.count+=other.count
        self.sum+=other.sum
        self.sum2+=other.sum2
        return self

class StatsContext(Accumulator.Context):
    def __init__(self):
        self.stats=Stats()
    def process(self,entry):
        super().process(entry)
        self.stats.update(entry)

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
            # TODO: remove common prefix and suffix
            # TODO: if remaining is 1 character long, then ''.join
            return ':'+(','.join(self.seentoday))

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
        if self.mask>0:
            return "%1x"%self.mask
        return super().format()

class StatsAccum(Accumulator):
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

# "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,"^`'. "
# " .:-=+*#%@"

class DataRow:
    """
    Serves as a base class, but may be used by itself
    intended to be initialized once and then reused for each subsequent rows of
    a summary
    """
    def __init__(self,duration,length,**kwargs):
        self.start=None
        self.finish=None
        self.accumType=Accumulator
        self.duration=duration
        self.duration_s=duration.total_seconds()
        self.length=length
        self.context=None
        self.render=None
        self.__dict__.update(kwargs)

    def reset(self, ts):
        start=self.render.startFor(ts)
        self.start=start
        # this may be overridden to be less than full duration
        # e.g. month view would have reserved space for 31 days, but only days
        # of current month will be actually filled
        self.finish=start+self.duration
        self.context=self.accumType.contextType()
        self.context.duration_s=self.duration_s/self.length
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
    # called when the very first row is ready to accept data
    # interval is reset, but buckets are empty
    # here is the place to print main header and initialize continuity tracking
    def begin(self):
        pass
    def printRow(self):
        pass
    def end(self):
        if self.dataRow.start!=None:
            self.printRow()
    def process(self,ts,entry):
        self.dataRow.process(ts,entry)
    # calculate beginning of a row interval for a givent ts.
    # override when necessary to round to nearest day, hour, etc.
    def startFor(self,ts):
        return ts

# use console to visualize data
# each cell in a row is 1xN symbols, usually N=1
class IntervalPrinter(Renderer):
    SCALEFILLER='·'
    def __init__(self,duration,length,accumType=Accumulator):
        # super().__init__(duration,length,accumType)
        self.dataRow=DataRow(duration,length)
        self.dataRow.render=self
        self.dataRow.accumType=accumType
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
                print(bh+(' '*w)+self.scale)
            else:
                print(bh)
                print( (' '*self.ROWHEADERWIDTH)+self.scale)

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

        print(rh+body+legend)

class HourPrinter(IntervalPrinter):
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
        return ts.strftime("%d:")

    def _isBlockHeaderNeeded(self):
        return (self.lastStart.year!=self.dataRow.start.year
            or self.lastStart.month!=self.dataRow.start.month)

# TODO? WeekPrinter? Monthprinter? YearPrinter? MinutePrinter

def SummarizeLogFile(logname:str, parser, r:Renderer):
    with open(logname,"r") as file:
        while True:
            line=file.readline()
            if not line: break
            # log-specific parsing
            l=line.rstrip("\r\n")
            parser(l,r)
        r.end()

def matchIso(s:str):
    m=re.search('\d{4}([-/]?\d{2}){2}[T ]\d{2}(:\d{2}(:\d{2}(\.\d*)?)?)?([-+]\d{2}:\d{2})?',s)
    return m

# finds anything that looks like iso timestamp in the string and if found
# passes entire string as an entry
def parseIso(s : str, r : Renderer):
    m=matchIso(s)
    if m!=None:
        try:
            ts=datetime.fromisoformat(m.group(0))
            r.process(ts,s)
        except ValueError:
            pass

# 127.0.0.1 - - [15/Jan/2025 15:01:59] "GET / HTTP/1.1" 200 -
#MONTHS=['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
MONTHS=[ datetime(year=1,month=i+1,day=1).strftime("%b").lower() for i in range(12)]
def parsePythonWeb(s:str, r:Renderer):
    m=re.search('^(\S+)\s+(\S+)\s+(\S+)\s+\[(\d+)/(.*)/(\d+) (\d+):(\d+):(\d+)\] *(.*)',s)
    if m!=None:
        try:
            (ip,_,_,d,mname,y,h,m,s,rq)=m.groups()
            mnum=MONTHS.index(mname.lower())
            ts=datetime(year=int(y),month=int(mnum)+1, day=int(d), hour=int(h), minute=int(m), second=int(s))
            r.process(ts,[ip,rq])
        except:
            pass

class WebAccum(StatsAccum):
    def update(self,data):
        (ip,rq)=data
        if ip=='127.0.0.1': return
        m=re.search('"(\S+)\s+(\S+)\s*(\S*)"\s*(\d+)',rq)
        if m!=None:
            (verb,urn,ver,code)=m.groups()
            super().update(int(code))

    def format(self):
        if not self.initialized: return ' '
        if self.stat.count==0: return '-'
        n=self.stat.max
        if n==0: return '?'
        return "%d"%(n//100)

# TODO: -n <buckets> -d (dayly) -H (hourly), -m -w -y -M

if __name__=='__main__':
    import sys
    import shutil
    cols=shutil.get_terminal_size((80,24)).columns
    NBUCKETS=cols-10
    for filename in sys.argv:
        SummarizeLogFile(filename, parseIso,  DayPrinter(NBUCKETS,Accumulator))
