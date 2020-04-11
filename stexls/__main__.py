from argparse import ArgumentParser
import pickle
import sys
import re
from tqdm import tqdm
from pathlib import Path

parser = ArgumentParser()

parser.add_argument('--cache', required=True, type=Path, help='Datei die als cache verwendet wird und beim neustart des Programms geladen wird. Die Datei kann einfach gelöscht werden ohne dass was schlimmes passiert.')
parser.add_argument('--root', required=True, type=Path, help='Pfad zum obersten MathHub Ordner, der smglom und MiKoMH usw. enthält.')
parser.add_argument('--filter', default='**/*.tex', help='Ein glob der relativ zu <root> sein muss. Default ist "**/*.tex". Erlaubt, dass man selektiv Dateien analysiert. Z.b. "--filter smglom/**/*.tex" würde alle Dateien in smglom analysieren. "--filter **/primes/*.tex" würde alle Dateien auschließlich im Repository "primes" sich anschauen.')
parser.add_argument('--tagfile', default=None, const='tags', action='store', nargs='?', type=Path, help='Optionaler Pfad, der raltive zu <root> ist, für ein Tagfile. "tags" wird verwendet, wenn kein Wert übergeben wurde. Kein Tagfile wird generiert, wenn diese Option nicht angegeben wird.')
parser.add_argument('--file', default=None, type=Path, help='Gibt informationen nur für eine Datei aus. Wenn diese Option nicht angegeben ist, werden alle Fehler für alle Dateien ausgegeben.')
parser.add_argument('--progress-indicator', const=tqdm, default=(lambda x: x), action='store_const', help='Gib eine Fortschrittsanzeige aus, während geupdated wird.')
parser.add_argument('--no-use-multiprocessing', action='store_true', help='Schalte multiprocessing ab. Macht alles aber langsam.')
parser.add_argument('--format', default='{file}:{line}:{column} - {severity} - {message}', help='Format für die Fehlermeldungen. Mögliche variablen sind: {file}, {line}, {column}, {severity} und {message}. Das Standartformat verwende alle diese Variablen und muss nicht angepasst werden, wenn du alle informationen haben willst.')
parser.add_argument('--view-graph', action='store_true', help='Zeigt den Importgraphen der Datei, die mit --file spezifiziert wurde.')

args = parser.parse_args()

from stexls import *

if args.cache.is_file():
    with open(args.cache.as_posix(), 'rb') as fd:
        linker = pickle.load(fd)
else:
    linker = Linker(root=args.root, file_pattern=args.filter)
    linker.update(progress=args.progress_indicator, use_multiprocessing=not args.no_use_multiprocessing)
    with open(args.cache.as_posix(), 'wb') as fd:
        pickle.dump(linker, fd)

def read_location(loc: Location):
    with open(loc.uri, 'r') as fd:
        lines = fd.readlines()
        if loc.range.is_single_line():
            return lines[loc.range.start.line][loc.range.start.character:loc.range.end.character]
        else:
            lines = lines[loc.range.start.line:loc.range.end.line+1]
            return '\n'.join(lines)[loc.range.start.character:-loc.range.end.character]

if args.tagfile:
    trans = str.maketrans({'-': r'\-', ']': r'\]', '\\': r'\\', '^': r'\^', '$': r'\$', '*': r'\*', '.': r'\,'})
    lines = []
    for path, objects in linker.objects.items():
        for object in objects:
            for id, symbols in object.symbol_table.items():
                for symbol in symbols:
                    keyword = symbol.identifier.identifier
                    file = symbol.location.uri.as_posix()
                    pattern = read_location(symbol.location).translate(trans)
                    lines.append(f'{keyword}\t{file}\t/{pattern}\n')
                    qkeyword = symbol.qualified_identifier.identifier.replace('.', '?')
                    if qkeyword != keyword:
                        lines.append(f'{qkeyword}\t{file}\t/{pattern}\n')
    with open((args.root/args.tagfile).as_posix(), 'w') as fd:
        fd.writelines(sorted(lines))
    del lines


if args.file:
    args.file = args.root / args.file.absolute().relative_to(args.root.absolute())
    linker.info(args.file)
    if args.view_graph:
        linker.view_import_graph(args.file)
    sys.exit()

for path, objects in linker.objects.items():
    for object in objects:
        link = linker.links.get(object, object)
        if link.errors:
            for loc, errs in link.errors.items():
                for err in errs:
                    print(
                        args.format.format(
                            file=loc.uri,
                            line=loc.range.start.line,
                            column=loc.range.start.character,
                            severity=type(err).__name__,
                            message=str(err)))
