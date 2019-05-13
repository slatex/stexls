import knowledge
import argparse
import tempfile
import sys
from os.path import isfile, exists, abspath

parser = argparse.ArgumentParser()

parser.add_argument('root', type=str, help='Path to root directory.')
parser.add_argument('--threads', type=int, default=2, help='Number of threads to use for parsing tex files.')
parser.add_argument('--pos_embedding_size', type=int, help='Dimensionality of the pos embedding.')
parser.add_argument('--pos_embedding_window', type=int, help='Window used to create the pos embedding.')
parser.add_argument('--to_file', type=str, help='If path is set, writes the database to the provided file.')
parser.add_argument('--encoding', type=str, default='utf-8', help='Encoding of result files.')
parser.add_argument('--as_tmp_file', action='store_const', const=True, default=False, help='If enabled, writes the database to a temporary file instead of dumping it to std::out, then prints the file\'s name to std::out.')
parser.add_argument('--debug', action='store_const', const=True, default=False, help='Prints stuff.')

args = parser.parse_args()

if args.to_file:
    if exists(args.to_file) and not isfile(args.to_file):
        parser.error('Path "%s" is not a valid output location.' % abspath(args.to_file))

kwargs = {
    "save_dir": args.root,
    "silent": not args.debug,
}

if args.pos_embedding_size:
    kwargs['pos_embedding_size'] = args.pos_embedding_size

if args.pos_embedding_window:
    kwargs['pos_embedding_window'] = args.pos_embedding_window

kb = knowledge.KnowledgeBase(n_jobs=args.threads, **kwargs)

if args.to_file:
    with open(args.to_file, mode='w+', encoding=args.encoding) as ref:
        kb.export_json(ref)
        print(ref.name)
elif args.as_tmp_file:
    with tempfile.NamedTemporaryFile(delete=False, mode='w+', encoding=args.encoding) as ref:
        kb.export_json(ref)
        print(ref.name)
else:
    kb.export_json(sys.stdout)
