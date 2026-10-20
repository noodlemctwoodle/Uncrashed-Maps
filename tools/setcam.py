#!/usr/bin/env python3
"""Point a map's editor camera (CamLoc) somewhere, in the repo copy and the installed copy, so relaunching the game
gives a known screenshot. Used by the in-game verification loop: set a camera, launch the game, grab the editor
view, repeat for the next viewpoint.

usage: setcam.py <MapName> <x> <y> <z> <yaw_deg> <pitch_deg>      (metres and degrees in the map's local frame;
       pitch negative looks down; yaw is the stored CamLoc yaw, see README for the convention test)"""

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEAM_ID = os.environ.get('UNCRASHED_STEAM_ID', '76561197969360950')
GAME_USER_MAPS = os.path.expanduser(f'~/Library/Application Support/Uncrashed/{STEAM_ID}/MapEditor/User')


def quat_pitch_yaw(pitch_deg, yaw_deg):
    """Quaternion for pitch then yaw in degrees (roll 0)."""
    P, Y = math.radians(pitch_deg) / 2, math.radians(yaw_deg) / 2
    SP, CP, SY, CY = math.sin(P), math.cos(P), math.sin(Y), math.cos(Y)
    return dict(X=SP * SY, Y=-SP * CY, Z=CP * SY, W=CP * CY)


if __name__ == '__main__':
    name = sys.argv[1]
    x, y, z, yaw, pitch = (float(v) for v in sys.argv[2:7])
    cam = dict(
        Rotation=quat_pitch_yaw(pitch, yaw),
        Translation=dict(X=round(x * 100, 2), Y=round(y * 100, 2), Z=round(z * 100, 2)),
        Scale3D=dict(X=1, Y=1, Z=1),
    )
    for folder in (os.path.join(ROOT, 'maps', name), os.path.join(GAME_USER_MAPS, name)):
        p = os.path.join(folder, name + '.json')
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        d['CamLoc'] = cam
        json.dump(d, open(p, 'w'))
        print('camera set in', p)
