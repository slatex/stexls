import sys
import os
from os import listdir
from os.path import join, splitext, exists, isdir, isfile
import shutil
import gzip
import zipfile
import tarfile
import urllib.request
from git import Repo
from glob import glob
import io
import datetime
from tqdm import tqdm

class Downloader:
    def __init__(self, url, download_location):
        self.url = url
        self.download_location = download_location
        self.finished = False
    
    def download(self, show_progress=True, blocksize=2**13):
        """ Blocks the thread until the file is downloaded.
        Keyword Arguments:
            :param show_progress: If enabled, uses tqdm to display download progress.
            :param blocksize: Download blocksize option.
        """
        progress = self.download_iterator(blocksize=blocksize)
        
        if show_progress:
            progress = tqdm(progress, total=self.content_length)
            update = progress.update
        else:
            update = lambda *args: None
        
        for chunk_size in progress:
            update(chunk_size)
        
        return self.finished
    
    @property
    def content_length(self):
        """ Attempts to download the size of the url. """
        with urllib.request.urlopen(self.url) as response:
            sz = response.headers['Content-Length']
            return int(sz) if sz else None
    
    def download_iterator(self, blocksize=2**13):
        """ Opens the url and downloads the file.
        Returns:
            Iterator of downloaded chunk sizes
        """
        if self.finished:
            raise Exception(f"File {self.download_location} already downloaded?")
        begin = datetime.datetime.now()
        bytes_downloaded = 0
        with urllib.request.urlopen(self.url) as response, open(self.download_location, 'wb') as out_file:
            while not self.finished:
                data = response.read(blocksize)
                if not data:
                    self.stats = {"begin":begin, "duration": datetime.datetime.now()-begin, "downloaded": bytes_downloaded}
                    self.finished = True
                else:
                    out_file.write(data)
                    bytes_downloaded += len(data)
                    yield len(data)
            out_file.flush()


def maybe_download_git(repo_url, save_dir='data/', silent=False):
    """
    :param repo_url: git repository to download
    :param save_dir: path to save directory
    :returns: path to the folder where the repo was cloned into
    """
   
    # name the repo from the url
    repo_name = splitext(repo_url)[0].split("/")[-1]
    
    # path to repo target directory
    clone_dir = join(save_dir, repo_name)

    if exists(clone_dir) and not isdir(clone_dir):
        raise Exception("Target clone path '%s' exists but is not a directory." % clone_dir)
    
    if os.path.exists(clone_dir):
        if not silent:
            print(f"Skipping {repo_url} as repository {clone_dir} is already present", flush=True)
    else:
        if not silent: print(f"Cloning {repo_url} into {clone_dir}...", end='', flush=True)
        try:
            Repo.clone_from(repo_url, clone_dir)
            if not silent: print("OK", flush=True)
        except:
            if not silent: print("Clone Failed", flush=True)
            raise
    return clone_dir

def maybe_download_and_extract(url, silent=False, return_name_of_single_file=True, return_all_extracted_file_names=True, save_dir='data/', cache='cache/'):
    """
    :param url: file to download
    :param return_name_of_single_file: if true, returns the name of the file that was extracted
    :param return_all_extracted_file_names: returns at least one and all extracted files
    :param save_dir: path to save directory
    :return: path to the folder where the url was extracted to (changes according to arguments)
    """

    # silent print function
    def sprint(*msg, endln=False, flush=True):
        if not silent:
            if endln: print(*msg, lush=flush)
            else: print(*msg, end='', lush=flush)
    
    # create missing directories
    if exists(cache) and not isdir(cache):
        raise RuntimeError(f"Can't create cache directory because path already exists and is not a directory: {cache}")
    if not exists(cache):
        os.makedirs(cache)
        
    if not exists(save_dir):
        os.makedirs(save_dir)

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

    # cache/file.ext
    path_to_file_in_cache = join(cache, file_name_with_ext)

    # data/file/ or data/file
    path_to_extract_location = join(save_dir, file_name_without_ext)    

    # do nothing if file is already extracted in data/
    if not exists(path_to_extract_location) or (isdir(path_to_extract_location) and listdir(path_to_extract_location) == []):
        # look for cached download
        if exists(path_to_file_in_cache):
            sprint(f"Using cached {path_to_file_in_cache} ...", flush=True)
        else:
            # download file
            sprint(f"Downloading {url} to {path_to_file_in_cache} ...", flush=True)
            downloader = Downloader(url, path_to_file_in_cache)
            success = downloader.download(show_progress=not silent)
            if not success:
                raise Exception("The download failed?")
        # extract all to extraction target directory
        if url.endswith(".zip"):
            # create extraction target directory if it doesn't exist (else it is empty)
            if not exists(path_to_extract_location):
                sprint("Making extraction directory at", path_to_extract_location, '...')
                os.makedirs(path_to_extract_location)
            with zipfile.ZipFile(path_to_file_in_cache, 'r') as zip_ref:
                sprint("Extracting .zip file ...")
                zip_ref.extractall(path_to_extract_location)
        elif url.endswith(".tar.gz"):
            # create extraction target directory if it doesn't exist (else it is empty)
            if not exists(path_to_extract_location):
                sprint("Making extraction directory at", path_to_extract_location, '...')
                os.makedirs(path_to_extract_location)
            with tarfile.open(path_to_file_in_cache, "r:gz") as tar_ref:
                sprint("Extracting .tar.gz file ...")
                tar_ref.extractall(path_to_extract_location)
        elif url.endswith(".gz"):
            with gzip.open(path_to_file_in_cache, 'rb') as gz_ref, open(path_to_extract_location, 'wb') as out_ref:
                sprint("Extracting .gz file ...")
                shutil.copyfileobj(gz_ref, out_ref)
        else:
            #raise Exception("Can't extract file with the extension %s..." % file_ext)
            sprint("Can't extract file with the extension %s... copying to %s instead..." % (file_ext, path_to_extract_location), flush=True)
            shutil.copy(path_to_file_in_cache, path_to_extract_location)
        sprint(" OK", endln=True)
    else:
        if not silent:
            print("{} is already present".format(path_to_extract_location))

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
                raise Exception(f"Expected a single file, but trying to return {len(extracted_file_names)} files")

    # if content of file is unknown, just return the directory
    return path_to_extract_location
