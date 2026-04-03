'''
Specialized version of Surf built specifically for Dumb OS
'''
from reader import rhtml
from reader.rescape import *
import os
import subprocess

def terminal_img(target):
    if target.startswith("http://") or target.startswith("https://"):
        try:
            import urllib.request
            tmp = "/tmp/dos_img_tmp"
            urllib.request.urlretrieve(target, tmp)
            result = subprocess.run(["chafa", tmp], capture_output=True, text=True)
        except Exception as e:
            print(f"{LRED}DOS: img: {e}{R}")
            return 0
    else:
        result = subprocess.run(["chafa", target], capture_output=True, text=True)
    print(result.stdout, end="")
    return result.stdout.count("\n")

def surf(args):
    max_lines = os.get_terminal_size().lines
    if not args:
        print(f"{LRED}Usage: surf <url>{R}")
        return
    no_graphics = "nographics" in args
    url = args[0]
    data = rhtml.parse(url)
    line_count = 0
    for line in data:
        if line["type"] in ["h1", "h2", "h3", "h4", "h5"]:
            print(f"{style(B, IT)}{line['text']}{R}")
        elif line["type"] in ["p", "code"]:
            print(line["text"])
        elif line["type"] == "a" and "href" in line:
            href = line["href"]
            if href.endswith((".png", ".jpg", ".jpeg", ".gif")):
                if not no_graphics:
                    line_count += terminal_img(href)
            else:
                print(f"{UL}{line['text']}{R}  [{LCYAN}{href}{R}]")
        elif line["type"] in ["img", "image"] and "src" in line:
            if not no_graphics:
                line_count += terminal_img(line["src"])
        line_count += 1
        if line_count >= max_lines - 2:
            print(f"{DM}-- press enter for more --{R}", end="", flush=True)
            input()
            line_count = 0
