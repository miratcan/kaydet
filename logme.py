#!/usr/bin/env python

"""logme: Simplest diary program"""

__author__ = "Mirat Can Bayrak"
__copyright__ = "Copyright 2016, Planet Earth"


from datetime import datetime

from os import mkdir
from os.path import expanduser, join, exists
import argparse
import subprocess
from tempfile import NamedTemporaryFile


def parse_args():
    parser = argparse.ArgumentParser(
        description='Diary program for your terminal.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--story', '-s', type=str, action='store',
        help='Your one line story to be saved.')
    group.add_argument(
        '--editor', '-e', dest='use_editor', action='store_true',
        help='Use editor to make multiline stories.')
    return parser.parse_args()


def get_story_from_editor():
    with NamedTemporaryFile('r') as tfile:
        subprocess.call(["vim", tfile.name])
        with open(tfile.name, 'r') as sfile:  # TODO: Fix this hack.
            story = sfile.read()
    return story


args = parse_args()
if args.use_editor:
    story = get_story_from_editor()
else:
    story = args.story

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
    timestamp = now.strftime("%H:%M")
    if args.use_editor:
        fp.write('%s: %s' % (timestamp, story.strip()))
    else:
        fp.write('%s: %s\n' % (timestamp, story.strip()))
fp.close()
