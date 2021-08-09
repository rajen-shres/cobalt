#!/usr/bin/env python

import sys, math, time, random
from time import sleep
from random import uniform

def distance(x, y):
    return math.ceil(math.sqrt(((x - 40) ** 2) + (((y - 12) * 2) ** 2)))

def star(radiuses):
    for r in radiuses:
        print((chr(27) + "[2J"))
        for y in range(24):
            # height
            for x in range(80):
                d = distance(x, y)
                if (d == r):
                    sys.stdout.write('*')
                elif (d < r):
                    if (r > 35):
                        sys.stdout.write(' ')
                    elif (r > 25) and ((d % 2) != 0):
                        sys.stdout.write('-')
                    elif (r > 15) and ((d % 2) == 0):
                        sys.stdout.write(' ')
                    else :
                        sys.stdout.write(random.choice('****#@'))
                else:
                    sys.stdout.write(' ')
            print()
        time.sleep(0.1)

star(list(range(0, 12)) + list(range(10, 0, -1)) + list(range(0, 50)))
