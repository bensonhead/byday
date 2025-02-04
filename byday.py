from datetime import datetime, timedelta

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

class Renderer:
    def __init__(self, interval):
        self.interval=interval
    # called when the very first row is ready to accept data
    # interval is reset, but buckets are empty
    # here is the place to print main header and initialize continuity tracking
    def begin(self):
        pass
    def printRow(self):
        pass
    def end(self):
        if self.interval.start!=None:
            self.printRow()

class Stats:
    def __init__(self):
        self.min=float('inf')
        self.max=float('-inf')
        self.sum=0.0
        self.count=0
        self.sum2=0.0
        self.first=None
        self.last=None

    def process(self, entry):
        entry=float(entry)
        if entry>self.max: self.max=entry 
        if entry<self.min: self.min=entry 
        if self.first==None: self.first=entry
        self.last=entry
        self.count+=1
        self.sum+=entry
        self.sum2+=entry*entry

class StatsContext(Accumulator.Context):
    def __init__(self):
        self.stats=Stats()
    def process(self,entry):
        super().process(entry)
        self.stats.process(entry)

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
        self.stat.process(number)

    def format(self):
        if self.stat.count==0: return super().format()
        return ("%02d"%int(self.stat.max))[0]

# "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,"^`'. "
# " .:-=+*#%@"

class TimelineInterval:
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
        self.renderType=Renderer
        self.__dict__.update(kwargs)
        self.render=self.renderType(self)

    def reset(self, start=None):
        self.start=start
        self.finish=start+self.duration
        self.context=self.accumType.contextType()
        self.context.duration_s=self.duration_s/self.length
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

    def finalize(self):
        self.render.end()

class DayInterval(TimelineInterval):

    def daystart(timestamp):
        return timestamp.replace(hour=0,minute=0,second=0,microsecond=0)

    def __init__(self,length,**kwargs):
        super().__init__(timedelta(days=1),length,**kwargs)

    def reset(self,ts):
        super().reset(DayInterval.daystart(ts))

class HourInterval(TimelineInterval):

    def intervalstart(timestamp):
        "truncate to nearest hour"
        return timestamp.replace(minute=0,second=0,microsecond=0)

    def __init__(self,length,**kwargs):
        super().__init__(timedelta(seconds=3600),length,**kwargs)

    def reset(self,ts):
        super().reset(HourInterval.intervalstart(ts))

class HourPrinter(Renderer):
    def __init__(self,interval):
        super().__init__(interval)
        l=interval.length
        s=0 # no hour marks
        for nt in [60, 12, 6, 4, 2, 1]:
            if l//nt>=4:
                s=nt
                break
        hdr=""
        step=60/s
        for i in range(s):
            pos=int(l*(i*step/60.0))
            hdr=hdr+("_" * (pos-len(hdr)))+("%d"%(int(i*step)))
        hdr=hdr+("_" * (l-len(hdr)))
        self.scale=(" "*len(self._formatRowHeader(datetime.now())))+hdr
        self.lastStart=None

    def begin(self):
        self._printBlockHeader(self.interval.start)

    # what a separator between larger blocks looks like
    def _printBlockHeader(self,start):
        self.lastStart=start
        print(start.strftime("%Y-%m-%d"))
        if self.scale!="":
            print (self.scale)

    # what the typical row header looks like
    def _formatRowHeader(self, ts):
        return ts.strftime("%H:")

    def printRow(self):
        if self.lastStart.year!=self.interval.start.year or self.lastStart.month!=self.interval.start.month or self.lastStart.day != self.interval.start.day:
            self._printBlockHeader(self.interval.start)

        rh=self._formatRowHeader(self.interval.start)

        body=''.join([bucket.format() for bucket in self.interval.buckets])
        legend=''
        if self.interval.context!=None: legend=self.interval.context.format()

        print(rh+body+legend)




class DayPrinter(Renderer):
    def __init__(self,interval):
        super().__init__(interval)
        l=interval.length
        s=0 # no hour marks
        for nt in [24,12,8,4,2,1]:
            if l//nt>=4:
                s=nt
                break
        hdr=""
        step=24/s
        for i in range(s):
            pos=int(l*(i*step/24.0))
            hdr=hdr+("_" * (pos-len(hdr)))+("%d"%(int(i*step)))
        hdr=hdr+("_" * (l-len(hdr)))
        self.scale="   "+hdr
        self.lastStart=None

    def begin(self):
        self._printBlockHeader(self.interval.start)

    # what a separator between larger blocks looks like
    def _printBlockHeader(self,start):
        self.lastStart=start
        print(start.strftime("%Y-%b"))
        if self.scale!="":
            print (self.scale)

    # what the typical row header looks like
    def _formatRowHeader(self, ts):
        return ts.strftime("%d:")

    def printRow(self):
        if self.lastStart.year!=self.interval.start.year or self.lastStart.month!=self.interval.start.month:
            self._printBlockHeader(self.interval.start)

        rh=self._formatRowHeader(self.interval.start)

        body=''.join([bucket.format() for bucket in self.interval.buckets])
        legend=''
        if self.interval.context!=None: legend=self.interval.context.format()

        print(rh+body+legend)



def SummarizeLogFile(logname:str, parser, row:TimelineInterval):
    with open(logname,"r") as file:
        while True:
            line=file.readline()
            if not line: break
            # log-specific parsing
            l=line.rstrip("\r\n")
            parser(l,row)
        row.finalize()

def matchIso(s:str):
    import re
    m=re.search('\d{4}([-/]?\d{2}){2}[T ]\d{2}(:\d{2}(:\d{2}(\.\d*)?)?)?([-+]\d{2}:\d{2})?',s)
    return m

# finds anything that looks like iso timestamp in the string and if found
# passes entire string as an entry
def parseIso(s : str, interval : TimelineInterval):
    m=matchIso(s)
    if m!=None:
        try:
            ts=datetime.fromisoformat(m.group(0))
            interval.process(ts,s)
        except ValueError:
            pass
    
# 127.0.0.1 - - [15/Jan/2025 15:01:59] "GET / HTTP/1.1" 200 -
#MONTHS=['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
MONTHS=[ datetime(year=1,month=i+1,day=1).strftime("%b").lower() for i in range(12)]
def parsePythonWeb(s:str, interval:TimelineInterval):
    m=re.search('^(\S+)\s+(\S+)\s+(\S+)\s+\[(\d+)/(.*)/(\d+) (\d+):(\d+):(\d+)\] *(.*)',s)
    if m!=None:
        try:
            (ip,_,_,d,mname,y,h,m,s,rq)=m.groups()
            mnum=MONTHS.index(mname.lower())
            ts=datetime(year=int(y),month=int(mnum)+1, day=int(d), hour=int(h), minute=int(m), second=int(s))
            interval.process(ts,[ip,rq])
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


if __name__=='__main__':
    import sys
    import shutil
    cols=shutil.get_terminal_size((80,24)).columns
    NBUCKETS=cols-10
    for filename in sys.argv:
        SummarizeLogFile(filename, parseIso,  DayInterval(NBUCKETS,accumType=Accumulator, renderType=DayPrinter))
