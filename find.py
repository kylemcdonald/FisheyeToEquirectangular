import argparse
import os
from datetime import datetime
from dateutil import parser as dateparser
from utils.list_all_files import list_all_files

parser = argparse.ArgumentParser(
    epilog='Usage: python find.py -i files/ -t "6/26/2019 15:14:45" -c 1 2'
)

parser.add_argument('-i', '--input_directory', type=str,
    help='Where to search for files', required=True)
parser.add_argument('-t', '--timestamp', type=str,
    help='Timestamp', required=True)
parser.add_argument('-c', '--channels', nargs='+',
    help='List of channels', required=True)
parser.add_argument('--fps', type=int,
    help='Frame rate for computing skip amount', default=24)
parser.add_argument('-e', '--extension', type=str,
    help='File extension (e.g. ".mp4")', default='.mp4')
parser.add_argument('-v', '--verbose', action='store_true')

args = parser.parse_args()
target = dateparser.parse(args.timestamp)
prefixed = [f'{int(channel):02d}' for channel in args.channels]

if args.verbose:
    print('Parsed date:', target)
    print(f'Listing files in {args.input_directory}')

files = list(list_all_files(args.input_directory, [args.extension]))

if args.verbose:
    print(f'{len(files)} files with extension {args.extension}')

matches = {}
for fn in files:
    basename = os.path.basename(fn)
    channel = basename[2:4]
    if basename[2:4] not in prefixed:
        continue
    current = datetime.strptime(basename[5:-4], '%Y%m%d%H%M%S')
    distance = int((target - current).total_seconds())
    if distance < 0:
        continue
    if channel not in matches or distance < matches[channel][0]:
        matches[channel] = (distance, fn)

skips = []
filenames = []
for prefix in prefixed:
    duration, fn = matches[prefix]
    print(f'{fn} +{duration} seconds')
    skips.append(duration * args.fps)
    filenames.append(fn)

if len(prefixed) == 2:

    print('Extract near beginning of files:')
    smaller = min(*skips)
    out = []
    for side, skip, fn in zip(['left', 'right'], skips, filenames):
        out.append(f'-{side[0]} {fn}')
        out.append(f'--skip_{side} {skip - smaller}')
    print('  ' + ' '.join(out))

    print(f'Extract from {args.timestamp}:')
    smaller = min(*skips)
    out = []
    for side, skip, fn in zip(['left', 'right'], skips, filenames):
        out.append(f'-{side[0]} {fn}')
        out.append(f'--skip_{side} {skip}')
    print('  ' + ' '.join(out))