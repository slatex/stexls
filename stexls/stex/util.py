from pathlib import Path

def find_source_dir(root: Path, file: Path) -> Path:
    """ Extracts the source directory from a file inside a subdirectory of root.

    Arguments:
        root: Root directory.
        file: File inside root directory.

    Returns:
        The first 'source' directory that appears in the relative path between <root> and <file>.
    """
    rel = file.relative_to(root)
    i = rel.parts.index('source')
    rel_source = rel.parents[i]
    return root / rel_source


def get_repository_identifier_from_filepath(root: Path, file: Path) -> str:
    """ Extracts the repository identifier from a filepath relative a certain root.

    Arguments:
        root: Path to the root directory.
        file: Path to the file inside a repository. Must be in a sub-directory of root.

    Returns:
        Repository identifier used in gimports.
        E.g.: smglom/balancedprime
    """
    pass

