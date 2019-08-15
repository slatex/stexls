from os import path
from . import download

__all__ = ['maybe_download']

all_repositories = (
    "smglom/physics",
    "smglom/cs",
    "smglom/lmfdb",
    "smglom/probability",
    "smglom/measure-theory",
    "smglom/tannakian",
    "smglom/categories",
    "smglom/theresas-playground",
    "smglom/complexity",
    "smglom/arithmetics",
    "smglom/elliptic-curves",
    "smglom/manifolds",
    "smglom/numthy",
    "smglom/identities",
    "smglom/numthyfun",
    "smglom/constants",
    "smglom/analysis",
    "smglom/trigonometry",
    "smglom/numbers",
    "smglom/primes",
    "smglom/linear-algebra",
    "smglom/magic",
    "smglom/functional-analysis",
    "smglom/geometry",
    "smglom/topology",
    "smglom/calculus",
    "smglom/algebra",
    "smglom/graphs",
    "smglom/sets",
    "smglom/mv",
    "smglom/chevahir",
    "smglom/SMGloM"
)

def maybe_download(
    save_dir='./data',
    show_progress=True,
    base_url="https://gl.mathhub.info/",
    repositories=all_repositories):
    """Downloads the repositories to the specified folder and returns the paths to all downloaded repositories.
    
    Keyword Arguments:
        :param save_dir: Directory to save downloaded repos to.
        :param show_progress: Wether debug output should be made or not.
        :param base_url: Base url where all repositories are located at.
        :param repositories: List of git repositories to download from base_url.
    Returns:
        Paths to all downloaded repository folders.
    """
    return [
        download.maybe_download_git(
            repo_url=path.join(base_url, repo),
            silent=not show_progress,
            save_dir=path.join(save_dir, '/'.join(repo.split('/')[:-1])))
        for repo in repositories
    ]
