''' This module contains methods for downloading and extracting
files or git repositories. '''
import datetime
import gzip
import os
import shutil
import tarfile
import urllib.request
import zipfile
from glob import glob
from os.path import exists, isdir, join, splitext
from pathlib import Path

from .git import clone

__all__ = ['maybe_download_git', 'maybe_download_and_extract']


class Downloader:
    ' Contains the state of a download operation. '

    def __init__(self, url, download_location):
        ''' Initializes the downloader with url and destination location.
            Also initializes a finished flag to false, which is set to Trueu
            after the download has finished.
        Parameters:
            url: Url to download.
            download_location: Location to where the files should be saved.
        '''
        self.url = url
        self.download_location = download_location
        self.finished = False

    @property
    def content_length(self):
        ' Attempts to download the size of the url. '
        with urllib.request.urlopen(self.url) as response:
            sz = response.headers['Content-Length']
            return int(sz) if sz else None

    def download(self, blocksize: int = 4096):
        ''' Opens the url and downloads the file.
        Returns:
            Iterator of downloaded chunksizes.
        '''
        if self.finished:
            raise Exception(
                f"File {self.download_location} already downloaded?")
        begin = datetime.datetime.now()
        bytes_downloaded = 0
        with urllib.request.urlopen(self.url) as response, open(self.download_location, 'wb') as out_file:
            while not self.finished:
                data = response.read(blocksize)
                if not data:
                    self.stats = {"begin": begin, "duration": datetime.datetime.now(
                    )-begin, "downloaded": bytes_downloaded}
                    self.finished = True
                else:
                    out_file.write(data)
                    bytes_downloaded += len(data)
                    yield len(data)
            out_file.flush()


def maybe_download_git(repo_url: str, save_dir: Path):
    ''' Downloads a git repository if it doesn't exist.
    Parameters:
        repo_url: git repository to download.
        save_dir: path to save directory.
    Returns:
        Path to the folder where the repo was cloned into.
    '''
    # name the repo from the url
    repo_name = splitext(repo_url)[0].split("/")[-1]

    # path to repo target directory
    clone_dir = save_dir / repo_name

    if exists(clone_dir) and not isdir(clone_dir):
        raise Exception(
            "Target clone path '%s' exists but is not a directory." % clone_dir)

    if os.path.exists(clone_dir):
        print(
            f"Skipping {repo_url} as repository {clone_dir} is already present", flush=True)
    else:
        print(f'Cloning {repo_url} into {clone_dir}...', end=' ', flush=True)
        try:
            clone(repo_url, dest=clone_dir, depth=1)
            print('OK', flush=True)
        except Exception:
            print('Failed', flush=True)
            raise

    return clone_dir


def maybe_download_and_extract(
        url,
        save_dir: str,
        extract_dir: str = None,
        silent=False,
        return_name_of_single_file=True,
        return_all_extracted_file_names=True):
    ''' Downloads any file and extracts it if it is a .zip, .tar.gz or .gz file.
    Parameters:
        url: Resource to download.
        save_dir: Directory to where the files should be stored.
        extract_dir: Directory to where the downloaded files should be extracted to if necessary.
            No extraction will be attempted if this is None.
        silent: Enables some info output to stdout.
        return_name_of_single_file: Enables returning of the path of the only file that was downloaded.
        return_all_extracted_file_names: Returns paths of all extracted files, raises if unable to.
    Returns:
        Path to the folder where the url was extracted to (changes according to arguments).
    '''
    # silent print function
    def sprint(*msg, endln=False, flush=True):
        if not silent:
            if endln:
                print(*msg, flush=flush)
            else:
                print(*msg, end='', flush=flush)

    # create missing directories
    if extract_dir is not None:
        extract_dir = os.path.abspath(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

    save_dir = os.path.abspath(save_dir)
    if extract_dir != save_dir:
        os.makedirs(save_dir, exist_ok=True)

    if url.endswith(".tar.gz"):
        # special case for .tar.gz
        url_file_name = url[:-len(".tar.gz")]
        file_ext = ".tar.gz"
    else:
        # http://domain.com/file, .ext
        url_file_name, file_ext = splitext(url)

    # file
    file_name_without_ext = url_file_name.split("/")[-1]

    # file.ext
    file_name_with_ext = file_name_without_ext + file_ext

    # <save_dir>/file.ext
    path_to_save_location = join(save_dir, file_name_with_ext)

    # <extract_dir>/file
    if extract_dir is not None:
        path_to_extract_location = join(extract_dir, file_name_without_ext)
    else:
        path_to_extract_location = path_to_save_location

    # do nothing if file is already extracted in data/
    if exists(path_to_extract_location):
        sprint(f'{path_to_extract_location} OK')
    else:
        # look for cached download
        if exists(path_to_save_location):
            sprint(f"Using cached {path_to_save_location} ...", flush=True)
        else:
            # download file
            sprint(
                f"Downloading {url} to {path_to_save_location} ...", flush=True)
            downloader = Downloader(url, path_to_save_location)
            chunksizes = list(downloader.download())
            if not downloader.finished:
                raise Exception(
                    f"The download failed. Last downloaded chunksize: {chunksizes}")
        # extract all to extraction target directory
        if extract_dir is not None:
            if url.endswith(".zip"):
                # create extraction target directory if it doesn't exist (else it is empty)
                os.makedirs(path_to_extract_location)
                with zipfile.ZipFile(path_to_save_location, 'r') as zip_ref:
                    sprint("Extracting .zip file to %s..." %
                           path_to_extract_location)
                    zip_ref.extractall(path_to_extract_location)
            elif url.endswith(".tar.gz"):
                # create extraction target directory if it doesn't exist (else it is empty)
                os.makedirs(path_to_extract_location)
                with tarfile.open(path_to_save_location, "r:gz") as tar_ref:
                    sprint("Extracting .tar.gz file to %s..." %
                           path_to_extract_location)
                    tar_ref.extractall(path_to_extract_location)
            elif url.endswith(".gz"):
                with gzip.open(path_to_save_location, 'rb') as gz_ref, open(path_to_extract_location, 'wb') as out_ref:
                    sprint("Extracting .gz file to %s..." %
                           path_to_extract_location)
                    shutil.copyfileobj(gz_ref, out_ref)
            else:
                sprint("Can't extract file with the extension %s... copying to %s instead..." % (
                    file_ext, path_to_extract_location), flush=True)
                shutil.copy(path_to_save_location, path_to_extract_location)
        sprint(" OK", endln=True)

    if isdir(path_to_extract_location):
        if return_all_extracted_file_names:
            # return all files inside the extraction directory target
            extracted_file_names = glob(join(path_to_extract_location, '*'))
            # at least one has to be there
            return extracted_file_names

        if return_name_of_single_file:
            # find extracted files inside the extraction target
            extracted_file_names = glob(join(path_to_extract_location, '*'))
            # return single file
            if len(extracted_file_names) == 1:
                return extracted_file_names[0]
            else:
                raise Exception(
                    f"Expected a single file, but trying to return {len(extracted_file_names)} files")

    # if content of file is unknown, just return the directory
    return path_to_extract_location
