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

    """
    Context is accumulator for entire parent row.
    All accumulators of same row share context and can update it.
    For example, track min/max for entire row to scale the resulst when
    the row is dumped.
    """
    contextType=type(None)

    def __init__(self, context):
        assert context==None or type(context)==self.contextType
        self.context=context
        self.initialized=False

    def update(self,entry):
        self.initialized=True

    def format(self):
        if self.initialized: return '-'
        else: return ' '

class AccumContext:
    # called for each entry of the subinterval
    def process(self, entry):
        pass
    # called once in the end of the row to print row "legend"
    # best if not needed
    def format(self):
        return ''
        
class Renderer:
    def __init__(self, interval):
        self.interval=interval
    # called when the very first row is ready to accept data
    # interval is reset, but buckets are empty
    # here is the place to print main header and initialize continuity tracking
    def begin(self):
        pass
    def main(self):
        pass
    def end(self):
        if self.interval.start!=None:
            self.main()

class BitmaskContext(AccumContext):
    """
    contains seentoday array which shows which string corresponds to which bit
    To be used in conjunction with BitmaskAccum
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
        return ':'+(','.join(self.seentoday))

class StatsContext(AccumContext):
    def __init__(self):
        super().__init__();
        self.min=float('inf')
        self.max=float('-inf')
        self.sum=0.0
        self.count=0
        self.sum2=0.0

    def process(self, entry):
        entry=float(entry)
        if entry>self.max: self.max=entry 
        if entry<self.min: self.min=entry 
        self.count+=1
        self.sum+=entry
        self.sum2+=entry*entry

class BitmaskAccum(Accumulator):
    """
    accumulate small set of strings in a form of bitmask
    BitmaskContext contains seentoday array which shows which string corresponds to which bit
    entry must be a simple string
    """
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

class StatAccum(Accumulator):
    contextType=StatsContext
    def __init__(self,context):
        super().__init__(context)
        self.stat=StatsContext()

    def update(self, number):
        super().update(number)
        self.context.process(number)
        self.stat.process(number)

    def format(self):
        if self.stat.count==0: return super().format()
        return ("%02d"%int(self.stat.max))[0]

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
            self.render.main()
            # then start a new one
            self.reset(ts)
            a=self._getAccumFor(ts)
        a.update(entry)

    def format(self):
        h=self.start.strftime("%Y%m%d %H%M%S")
        return h+':'+''.join([bucket.format() for bucket in self.buckets])

    def finalize(self):
        self.render.end()

class DayInterval(TimelineInterval):

    def daystart(timestamp):
        return timestamp.replace(hour=0,minute=0,second=0,microsecond=0)

    def __init__(self,length,**kwargs):
        super().__init__(timedelta(days=1),length,**kwargs)

    def reset(self,ts):
        super().reset(DayInterval.daystart(ts))

    def format(self):
        rowheader=self.start.strftime("%d:")
        body=''.join([bucket.format() for bucket in self.buckets])
        legend=''
        if self.context!=None: legend=self.context.format()
        return rowheader+body+legend

class DayPrinter(Renderer):
    def __init__(self,interval):
        super().__init__(interval)
        self.lastStart=None

    def header(self,start):
        print(start.strftime("%Y-%b"))
    def begin(self):
        self.header(self.interval.start)

    def main(self):
        print(self.interval.format())



def SummarizeLogFile(logname:str, parser, row:TimelineInterval):
    with open(logname,"r") as file:
        while True:
            line=file.readline()
            if not line: break
            # log-specific parsing
            l=line.rstrip("\r\n")
            parser(l,row)
        row.finalize()

if __name__=='__main__':
    import sys
    print("hello")
