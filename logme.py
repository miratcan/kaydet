#!/usr/bin/env python

"""logme: Simplest diary program"""

__author__ = "Mirat Can Bayrak"
__copyright__ = "Copyright 2016, Planet Earth"


from datetime import datetime

from os import mkdir
from os.path import expanduser, join, exists
from sys import argv

DAY_FILE_PATTERN = '%Y-%m-%d.txt'
DAY_TITLE_PATTERN = '%Y/%m/%d/ - %A\n'

LOG_DIR = join(expanduser('~'), '.logme')

if not exists(LOG_DIR):
    mkdir(LOG_DIR)

now = datetime.now()
file_name = datetime.strftime(now, DAY_FILE_PATTERN)
file_path = join(LOG_DIR, file_name)

if not exists(file_path):
    fp = open(file_path, 'w')
    title = datetime.strftime(now, DAY_TITLE_PATTERN)
    fp.write(title)
    fp.write('-' * (len(title) - 1) + '\n')
else:
    fp = open(file_path, 'a')

if len(argv) > 1:
    note = ' '.join(argv[1:])
    timestamp = now.strftime("%H:%M")
    fp.write('%s: %s\n' % (timestamp, note))

fp.close()
