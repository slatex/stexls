' Interface to git. '

from pathlib import Path
import subprocess
from typing import Optional, Union

__all__ = ['clone']


def clone(
        repo: str,
        dest: Optional[Union[Path, str]] = None,
        depth: Optional[int] = None,
        executable: str = 'git',
) -> int:
    ' Clones a repository into the current pwd or dest if given. Returns git process exit code. '
    args = [executable, 'clone']
    if depth is not None:
        args.extend(('--depth', str(depth)))
    args.append(repo)
    if dest is not None:
        args.append(str(dest))
    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    return proc.wait()
