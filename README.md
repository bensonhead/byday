# byday
Summarize log content in condensed form.

## Display method

### Rows

Time span contained in a log is represented on a screen as rows of cells.

Each row represents a fixed-length subinterval of the time period.
For example, a row may represent an hour, or a day.
The cells in a row (internally called "buckets") represent proportionally smaller subintervals of that larger subinterval. Their actual duration depends on a screen width. For example, if the row represents 1 hour and there are 72 cells in a row, then each cell represent 1/72 of the hour, or 50 seconds.

As the data from the log is coming, it is collected in aggregators, 1 per each cell.

### Aggregator

Each cell represents a value of an "aggregator".
Aggregator is a structure that can accumulate some value of interest.
Sometimes the cell will represent information from multiple log entries, so this information must be aggregated is some way. Example can be a simple count of events. Another example is sum of values.

```
@startuml
Class Aggregator {
  contextType
  update()
  format()
}
@enduml

Each time this summarizer receives a timestamped log entry, it determines which aggregator of a row needs to be updated and calls its `.update(entry)` method.

### Cells

Once the row is complete and ready to be printed it is calls `.format` method on each of its aggregators. This method must return one character, representing the value accumulated in that aggregator. Summarizer collects all the characters, supplies them with row header (on the left), optional row legend (on the right), prints it out and moves on to the next row.

So, the job of accumulator is two-fold. First, must know how to accumulate some value from several log entries that fall into its time range. Second, it must be able to represent this value as a character. Generally speaking istead of a single character it is possible to use a rectangular block of characters. This allows for greater ability to display data at the expense of less efficient use of screen. Anyway, this possibility is not implemented and 1 character to represent a value is all we will have to work with.

### Renderers

Renderer maintains current row of aggregators.
When it receives next timestamped entry from the log (its `.process()` method is called), it decides which aggregator needs to be updated. If the new row 

```
@startuml
abstract class Renderer {
  aggregatorType
  dataRow : DataRow
  process(timestamp,entry)
  begin()
  printRow()
  end()
}

abstract class IntervalPrinter {
  begin()
  printRow()
  end()
}

Renderer <|-- IntervalPrinter
IntervalPrinter <|-- MinutePrinter
IntervalPrinter <|-- HourPrinter
IntervalPrinter <|-- DayPrinter
IntervalPrinter <|-- MonthPrinter

@enduml
```

`IntervalPrinter` is a kind of output that where each row represents a standard time interval (e.g. 1 hour), each row has a header (e.g. hour number), rows are grouped into larger blocks (e.g. at daybreaks) and each block has its own header (e.g. year, month and day of hours that follow).

There are several premade derived classes, each to display data row per minute/hour/day/month.
 
### Parsers

Parsers are needed to address a problem that different logs have widely differing format.

So, each type of log must have its own parser associated with it.

```
parser(string,renderer)
```

parser detects if a string (which presumably comes from the log) contains a timestamp and relevant data. If so, it calls parser's `.process(` method, thus passing the parsed timestamp as datetime object and retrieved data in a form of the object `entry`. The type and format of this object must be compatible with renderer's aggregatorType, as renderer passes the `entry` object directly to aggregator's `.update(` method

example workflow:

choose parser and renderer
choose type of aggregator to use (it must be compatible with the parser)
initialize renderer to use with this aggregatorType
for each line in logfile:
   call parser.process(line,renderer)
call renderer.end()

Parser knows how to extract the data.
Aggregator knows how to accumulate this kind of data and how to condense the final accumulated result into a single compact visual block (currently, one single-width unicode symbol).
These 2 must be compatible with each other and most likely need to be implemented by the user for each kind of log format/information kind they are interested in.
Renderer sits in between. It knows what time scale user is interested in. Based on the timestamp of received entry it chooses whether it needs to update an aggregator from the current row or create a new row. It outputs rows (together withl all necessary adornments) as they fill up and separates them into blocks with possible headers, legends, etc.

## Problems




