from os import path as _path
from . import download as _download

def maybe_download(
    save_dir='./data',
    silent=True,
    base_url="https://gl.mathhub.info/",
    repositories=["smglom/SMGloM","smglom/chevahir","smglom/mv","smglom/sets","smglom/graphs", "smglom/algebra","smglom/calculus",
    "smglom/topology","smglom/geometry","smglom/functional-analysis","smglom/magic","smglom/linear-algebra",
    "smglom/primes","smglom/numbers","smglom/trigonometry","smglom/analysis","smglom/constants","smglom/numthyfun",
    "smglom/identities","smglom/numthy","smglom/manifolds","smglom/elliptic-curves",
    "smglom/arithmetics","smglom/complexity","smglom/theresas-playground","smglom/categories",
    "smglom/tannakian","smglom/measure-theory","smglom/stats"]):
    """Downloads the repositories to the specified folder and returns the paths to all downloaded repositories.
    
    Keyword Arguments:
        :param save_dir: Directory to save downloaded repos to.
        :param silent: Wether debug output should be made or not.
        :param base_url: Base url where all repositories are located at.
        :param repositories: List of git repositories to download from base_url.
    Returns:
        Paths to all downloaded repository folders.
    """
    return [
        _download.maybe_download_git(
            repo_url=_path.join(base_url, repo),
            silent=silent,
            save_dir=_path.join(save_dir, '/'.join(repo.split('/')[:-1])))
        for repo in repositories
    ]
