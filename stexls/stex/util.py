from pathlib import Path

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

