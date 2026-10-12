
import calendar,re
DATE_FORMATS={"year","numeric","short","long"}
def validate_dates(start_year=None,start_month=None,end_year=None,end_month=None,is_current=False):
 if start_month and not start_year: raise ValueError("Start month requires a start year.")
 if end_month and not end_year: raise ValueError("End month requires an end year.")
 if is_current and (end_year or end_month): raise ValueError("Current entries cannot have an end date.")
 if start_year and end_year and (end_year,end_month or 12)<(start_year,start_month or 1): raise ValueError("End date cannot precede start date.")
def format_point(year,month,style):
 if not year:return ""
 if style=="year" or not month:return str(year)
 if style=="numeric":return f"{month:02d}/{year}"
 return f"{calendar.month_abbr[month] if style=='short' else calendar.month_name[month]} {year}"
def display_date(row,style="long"):
 override=(row.get("date_label") or row.get("display_date") or "").strip()
 if override:return override
 start=format_point(row.get("start_year"),row.get("start_month"),style)
 end="Present" if row.get("is_current") else format_point(row.get("end_year"),row.get("end_month"),style)
 return " - ".join(x for x in (start,end) if x)
def chronological_key(row):
 structured=bool(row.get("start_year") or row.get("end_year") or row.get("is_current"))
 if not structured:return (1,0,0,row.get("manual_order",0),str(row.get("id","")))
 end=999912 if row.get("is_current") else (row.get("end_year") or 0)*100+(row.get("end_month") or 12)
 start=(row.get("start_year") or 0)*100+(row.get("start_month") or 1)
 return (0,-int(bool(row.get("is_current"))),-end,-start,row.get("manual_order",0),str(row.get("id","")))
def normalize_company(value):return re.sub(r"\s+"," ",(value or "").strip()).casefold()
def month_value(year,month,boundary):return year*12+(month or boundary)-1 if year else None
def continuous(previous,current):
 if normalize_company(previous.get("organization"))!=normalize_company(current.get("organization")):return False
 prior_end=month_value(previous.get("end_year"),previous.get("end_month"),12)
 if previous.get("is_current"):prior_end=999999
 current_start=month_value(current.get("start_year"),current.get("start_month"),1)
 current_end=month_value(current.get("end_year"),current.get("end_month"),12) or (999999 if current.get("is_current") else None)
 prior_start=month_value(previous.get("start_year"),previous.get("start_month"),1)
 if None in (prior_end,current_start,current_end,prior_start):return False
 return current_start<=prior_end+1 and prior_start<=current_end+1
def preprocess_resume(resume,sort_modes=None,date_format="long"):
 data={**resume};modes=sort_modes or {}
 for key in ("projects","work_experience","leadership"):
  rows=[dict(x) for x in data.get(key,[])]
  for row in rows:
   rendered=display_date(row,date_format)
   if rendered or not row.get("date"):
    row["date"]=rendered
  if modes.get(key,"automatic")=="automatic":rows=sorted(rows,key=chronological_key)
  if key=="work_experience":
   for i,row in enumerate(rows):
    previous=rows[i-1] if i else None
    same=bool(previous) and normalize_company(previous.get("organization"))==normalize_company(row.get("organization")) and bool(normalize_company(row.get("organization")))
    row["suppress_organization"]=same
  data[key]=rows
 education=[]
 for item in data.get("education",[]):
  row=dict(item)
  override=(row.get("display_date") or "").strip()
  if override:
   row["graduation_date"]=override
  elif row.get("graduation_year"):
   row["graduation_date"]=format_point(row.get("graduation_year"),row.get("graduation_month"),date_format)
  education.append(row)
 data["education"]=education
 custom=[]
 for section in data.get("custom_sections",[]):
  sec=dict(section); entries=[]
  for item in sec.get("entries",[]):
   row=dict(item); rendered=display_date(row,date_format)
   if rendered or not row.get("date"): row["date"]=rendered
   entries.append(row)
  sec["entries"]=entries; custom.append(sec)
 data["custom_sections"]=custom
 return data
