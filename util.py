import json
import datetime
from dateutil import parser
from zoneinfo import ZoneInfo


def get_month_name(number, language):
    month_name = None

    if number == 1:
        if language == "en":
            month_name = "january"
        else:
            month_name =  "januari"
    elif number == 2:
        if language == "en":
            month_name = "february"
        else:
            month_name = "februari"
    elif number == 3:
        if language == "en":
            month_name = "march"
        else:
            month_name = "maart"
    elif number == 4:
        month_name = "april"
    elif number == 5:
        if language == "en":
            month_name = "may"
        else: 
            month_name = "mei"
    elif number == 6:
        if language == "en":
            month_name = "june"
        else:
            month_name = "juni"
    elif number == 7:
        if language == "en":
            month_name = "july"
        else:
            month_name = "juli"
    elif number == 8:
        if language == "en":
            month_name = "august"
        else:
            month_name = "augustus"
    elif number == 9:
        month_name = "september"
    elif number == 10:
        if language == "en":
            month_name = "october"
        else:
            month_name = "oktober"
    elif number == 11:
        month_name = "november"
    else:
        month_name = "december"


    # Using this because months are capitalized in English but not in Dutch
    if language == "en":
        return month_name.capitalize()
    return month_name

def add_timezone_to_date(input_date, time_zone):
    dt = parser.isoparse(input_date)
    dt = dt.replace(tzinfo=ZoneInfo(time_zone))

    return dt

def get_today_date():
    return (datetime.datetime.now().strftime("%A"), datetime.datetime.now(ZoneInfo("Europe/Brussels")).strftime("%H:%M:%S"), datetime.date.today().isoformat())

def remove_source(s: str):
    """Function that removes sources that AI on Azure mentions when
    searching for information in attached files."""
    start = s.find("【")
    end = s.rfind("】")

    if start != -1 and end != -1:
        s = s[0:start] + s[end+1:]
    
    while True:
        if s[-1] == " " or s[-1] == "\n":
            s = s[:-1]
        else:
            break

    return s


def extract_json(s: str):
    """Function that makes sure JSON is extracted even if 
    AI adds redundant text outside of JSON.
    
    Throws a ValueError if no JSON is found."""
    if isinstance(s, dict):
        return s
    
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in string")
    
    json_str = s[start:end+1]
    return json.loads(json_str)


print(get_today_date())