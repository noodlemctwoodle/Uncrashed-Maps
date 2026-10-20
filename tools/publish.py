#!/usr/bin/env python3
"""Keep each map's Workshop title, description, tags and change note in the repo (maps/<Name>/workshop.json) so
publishing never means retyping them, and render the steamcmd upload script for a map.

The game itself stores only Name/BaseMapRow/CreatorSteamID/CreationTimeUnix/Track in <Name>.info; the Workshop
title and description live on Steam alone. steamcmd's workshop_build_item uploads or updates a Workshop item for
any app from a VDF, which is the same item type the game's own publish dialog creates. First publish: leave
"publishedfileid" at 0, run the command, then paste the id steamcmd prints back into workshop.json so later runs
update the same item.

usage: publish.py <MapName> [--write]     prints (or writes maps/<Name>/workshop.vdf) and the steamcmd command"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPID = 1682970  # Uncrashed: FPV Drone Simulator


def vdf(name, meta):
    folder = os.path.join(ROOT, 'maps', name)
    lines = [
        '"workshopitem"',
        '{',
        f'    "appid" "{APPID}"',
        f'    "publishedfileid" "{meta.get("publishedfileid", 0)}"',
        f'    "contentfolder" "{folder}"',
        f'    "previewfile" "{os.path.join(folder, meta.get("preview", "Thumbnail.jpg"))}"',
        f'    "visibility" "{meta.get("visibility", 0)}"',
        f'    "title" "{meta["title"]}"',
        f'    "description" "{meta["description"]}"',
        f'    "changenote" "{meta.get("changenote", "")}"',
    ]
    if meta.get('tags'):
        lines += ['    "tags"', '    {'] + [f'        "{i}" "{t}"' for i, t in enumerate(meta['tags'])] + ['    }']
    lines.append('}')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    name = sys.argv[1]
    meta = json.load(open(os.path.join(ROOT, 'maps', name, 'workshop.json')))
    text = vdf(name, meta)
    out = os.path.join(ROOT, 'maps', name, 'workshop.vdf')
    if '--write' in sys.argv:
        open(out, 'w').write(text)
        print('wrote', out)
    else:
        print(text)
    print(f'steamcmd +login <steam_user> +workshop_build_item "{out}" +quit')
