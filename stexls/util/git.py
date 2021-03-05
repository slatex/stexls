' Interface to git. '

import subprocess

GIT_EXECUTABLE = 'git'

__all__ = ['clone']


def clone(repo: str, dest: str = None, depth: int = None) -> int:
    ' Clones a repository into the current pwd or dest if given. Returns git process exit code. '
    args = [GIT_EXECUTABLE, 'clone']
    if depth is not None:
        args.extend(('--depth', str(depth)))
    args.append(repo)
    if dest is not None:
        args.append(dest)
    proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE)
    return proc.wait()
