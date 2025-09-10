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