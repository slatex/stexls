from pathlib import Path

def find_source_dir(root: Path, file: Path) -> Path:
    """ Extracts the source directory from a file inside a subdirectory of root.

    Arguments:
        root: Root directory.
        file: File inside root directory.

    Returns:
        The first 'source' directory that appears in the relative path between <root> and <file>.

    Examples:
        >>> from pathlib import Path
        >>> root = Path('path/to/mathhub')
        >>> file = root / 'mh/primes/source/lang/en/balancedprime.en.tex'
        >>> find_source_dir(root, file)
        PosixPath('path/to/mathhub/mh/primes/source')
    """
    rel = file.relative_to(root)
    i = rel.parts.index('source')
    rel_source = rel.parents[i]
    return root / rel_source


def get_repository_name(root: Path, file: Path) -> str:
    """ Extracts the repository identifier from a filepath relative a certain root.

    Arguments:
        root: Path to the root directory of MathHub.
        file: Path to the file inside a repositories source directory. Must be in a sub-directory of root.

    Returns:
        Repository identifier name.

    Examples:
        >>> from pathlib import Path
        >>> root = Path('path/to/mathhub')
        >>> file = root / 'smglom/primes/source/balancedprime.en.tex'
        >>> get_repository_name(root, file)
        'smglom/primes'
    """
    source = find_source_dir(root, file)
    i = source.parents.index(root)
    return '/'.join(file.parent.parts[-i:])

def get_path(root: Path, file: Path) -> str:
    """ Extracts the relative path between the source directory of a file and the file itself, INCLUDING the file
    but without the extension.
    Used in path= arguments of \\importmodule environments.

    Arguments:
        root: MathHub root directory.
        file: File to extract path= from.

    Returns:
        Path identifier.

    Examples:
        >>> from pathlib import Path
        >>> root = Path('path/to/mathhub')
        >>> file = root / 'MikoMH/TDM/source/digidocs/en/markdown.tex'
        >>> get_path(root, file)
        'digidocs/en/markdown'
    """
    source = find_source_dir(root, file)
    rel = file.relative_to(source)
    return str(rel.parent / rel.stem)

def get_dir(root: Path, file: Path) -> Path:
    """ Extracts the directory relative to the source directory of the file.

    Arguments:
        root: MathHub root directory.
        file: File to extract dir= from.

    Returns:
        Path to file relative to the file's source directory.

    Examples:
        >>> from pathlib import Path
        >>> root = Path('path/to/mathhub')
        >>> file = root / 'MikoMH/TDM/source/digidocs/en/markdown.tex'
        >>> get_dir(root, file)
        PosixPath('digidocs/en')
    """
    return file.relative_to(find_source_dir(root, file)).parent

def is_file_newer(file: Path, old_file: Path) -> bool:
    ' Checks if file is newer than old_file. '
    return file.lstat().st_mtime > old_file.lstat().st_mtime
