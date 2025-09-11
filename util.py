import json

def remove_source(s: str):
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
    if isinstance(s, dict):
        return s
    
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in string")
    
    json_str = s[start:end+1]
    return json.loads(json_str)