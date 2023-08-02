__author__ = "Mirat Can Bayrak"
__copyright__ = "Copyright 2016, Planet Earth"
__version__ = "0.8.5"
__description__ = "Simple and terminal-based personal diary app designed " \
                  "to help you preserve your daily thoughts, experiences, " \
                  "and memories."


from datetime import datetime

from os import mkdir, environ as env
from os.path import expanduser, join, exists
from configparser import ConfigParser
from os import fdopen, remove
import argparse
import subprocess
from tempfile import mkstemp


def parse_args(config_path):
    parser = argparse.ArgumentParser(
        prog='kaydet',
        description=__description__,
        epilog="You can configure this by editing: %s" % config_path +
               "You can try these:\n\n"
               "  $ kaydet 'I felt grateful now.'\n"
               "  $ kaydet \"When I'm typing this I felt that I need an "
               "editor\" --editor",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'entry', type=str, nargs='?', metavar='Entry', action='store',
        help='Your one entry to be saved. If not given, editor will be '
             'dispayed.')
    parser.add_argument(
        '--editor', '-e', dest='use_editor', action='store_true',
        help='Force to open editor')
    return parser.parse_args()


def get_entry(args, config):
    entry: str
    if args.use_editor or args.entry is None:
        fd, path = mkstemp()
        with fdopen(fd, 'w+') as file:
            file.write(args.entry or '')
        subprocess.call([config['EDITOR'], path])
        with open(path, 'r') as file:
            entry = file.read()
        remove(path)
        return entry + '\n'
    return args.entry + '\n'


def get_config():
    config_dir = env.get("XDG_CONFIG_HOME", "")
    if not config_dir.strip():
        config_dir = expanduser("~/.config")
    config_dir = join(config_dir, 'kaydet')

    if not exists(config_dir):
        mkdir(config_dir)

    config = ConfigParser(interpolation=None)

    config_path = join(config_dir, 'config.ini')

    if not exists(config_path):
        config['SETTINGS'] = {
            'DAY_FILE_PATTERN': '%Y-%m-%d.txt',
            'DAY_TITLE_PATTERN': '%Y/%m/%d/ - %A',
            'LOG_DIR': join(expanduser('~'), '.kaydet'),
            'EDITOR': 'vim'
        }
        with open(config_path, 'w') as config_file:
            config.write(config_file)
            return config['SETTINGS'], config_path
    config.read(config_path)
    return config['SETTINGS'], config_path


def main():
    config, config_path = get_config()

    if not exists(config['LOG_DIR']):
        mkdir(config['LOG_DIR'])

    args = parse_args(config_path)
    now = datetime.now()

    file_name = datetime.strftime(now, config['DAY_FILE_PATTERN'])
    file_path = join(config['LOG_DIR'], file_name)

    if not exists(file_path):
        with open(file_path, 'w') as file:
            title = datetime.strftime(now, config['DAY_TITLE_PATTERN'])
            file.write(title + '\n')
            file.write('-' * (len(title) - 1) + '\n')

    entry = get_entry(args, config)
    with open(file_path, 'a') as file:
        timestamp = now.strftime("%H:%M")
        file.write('%s: %s\n' % (timestamp, entry.strip()))

    print("Entry added to:", file_path)


if __name__ == '__main__':
    main()


