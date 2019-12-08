from __future__ import annotations

from stex_language_server.util import download

class Label(IntEnum):
    """ Possible labels. """
    TEXT=0
    TREFI=1
    DEFI=2


def _alt_edge_detector(tokens: Iterable[Token]) -> List[bool]:
    """ Transforms an iterable of tokens to a list of bools that are True on the first token of an adefi or atrefi. """
    tokens = tuple(tokens)
    matcher = re.compile(r'm?am?(tr|d)efi+s?').fullmatch
    alt_token_envs = tuple(any(map(matcher, token.envs)) for token in tokens)
    f = [alt_token_envs[0]] + [
        (not p) and n
        for p, n in zip(alt_token_envs, alt_token_envs[1:])
    ]
    return f

def _make_stream(
    file: str,
    lang: str,
    lower: bool,
    split_into_definitions: bool) -> Union[List[LatexTokenStream], LatexTokenStream]:
    """ Makes a filetered token stream from a file path for each 'definition' environment in it. """
    parser = LatexParser(file)
    if parser is None or not parser.success:
        return None
    if split_into_definitions:
        return [
            LatexTokenStream(
                root=stream_root,
                lang=lang,
                lower=lower,
                perform_character_replacements=False,
                token_filter_fn=_alt_edge_detector
            )
            for stream_root
            in parser.root.finditer('definition')
            # finditer definition in order to filter out tokens outside of definitions
        ]
    else:
        return LatexTokenStream(
            root=parser.root,
            lang=lang,
            lower=lower,
            perform_character_replacements=False,
            token_filter_fn=_alt_edge_detector
        )

_TREFI_PATTERN = re.compile(r"""[ma]*trefi+s?""")
_DEFI_PATTERN = re.compile(r"""[ma]*defi+s?""")

def _envs2label(envs: Tuple[str, ...], binary_labels: bool) -> Label:
    """ Determines label by looking a list of environments. """
    if any(map(_TREFI_PATTERN.fullmatch, envs)):
        return Label.TREFI
    if any(map(_DEFI_PATTERN.fullmatch, envs)):
        return Label.TREFI if binary_labels else Label.DEFI
    return Label.TEXT

def parse_files(
    lang: str = 'en',
    lower: bool = True,
    split_into_definitions: bool = False,
    download_dir: str = 'data/',
    n_jobs: int = 4,
    show_progress: bool = False) -> Iterator[Iterable[LatexToken]]:
    """ Downloads all smglom repositories from github and parses the .tex files for the specified language.

    Keyword Arguments:
        :param lang: Language of files to load. Uses the pattern: "filename.lang.tex".
        :param lower: Enables token to lowercase transform.
        :param split_into_definitions: If true, splits token streams into smaller token streams based on the smglom \\begin{definition}...\\end{definition} environments.
        :param download_dir: Directory to where the git repositories are downloaded.
        :param n_jobs: Number of processes to use to parse tex files.
        :param show_progress: Uses tqdm to display loading progress.
    
    Returns:
        List of successfully parsed latex documents.
        
    """
    
    files = [
        file
        for folder
        in download_smglom.maybe_download(download_dir=download_dir, show_progress=show_progress)
        for file
        in glob(path.join(folder, f'**/*.{lang}.tex'))
    ]

    make_stream = functools.partial(
        _make_stream,
        lang=lang,
        lower=lower,
        split_into_definitions=split_into_definitions
    )

    with Pool(n_jobs) as pool:
        if show_progress:
            it = tqdm(pool.imap_unordered(make_stream, files))
        else:
            it = pool.map(make_stream, files)

        if split_into_definitions:
            # it contains lists of token streams -> yield recursively
            for definition_token_streams in filter(None, it):
                yield from definition_token_streams
        else:
            # it only contains token strean -> yield all
            yield from filter(None, it)

def parse_dataset(
    document_token_streams: Optional[List[LatexTokenStream]] = None,
    binary_labels: bool = False,
    math_token: str = '<math>',
    lower: bool = True,
    lang: Optional[str] = None,
    split_into_definitions: bool = False,
    show_progress: bool = False) -> Tuple[List[List[str]], List[List[Label]]]:
    """ Parses tex documents for labels and tokens assuming they are annotated
    with trefi and defi tags.

    Keyword Arguments:
        :param documents: List of documents to use for dataset creation. Downloads and parses smglom files, if None.
        :param binary_labels: If True, aliases TREFI and DEFI tags as a single KEYWORD tag with the ordinal value 1.    
        :param math_token: String to use instead of math tokens.
        :param lower: Enables lowercase transform of all tokens.
        :param lang: Language the files got parsed for. Changes the tokenization process depending on the value.
        :param split_into_definitions: If enabled, splits documents on smglom 'definition' environments.
    Returns:
        Tuple of list of lists of tokens and list of lists of labels.
    """
    if document_token_streams is None:
        document_token_streams = parse_files(
            lang=lang or 'en',
            show_progress=show_progress,
            lower=lower,
            split_into_definitions=split_into_definitions,
        )

    labeled_tokens = [
        [
            (
                (math_token
                if math_token
                and '$' in token.envs
                else token.lexeme),
                _envs2label(
                    token.envs,
                    binary_labels
                )
            )
            for token
            in token_stream
        ]
        for token_stream in document_token_streams
    ]

    list_of_X_y_pairs = [
        list(zip(*labeled))
        for labeled in labeled_tokens
    ]

    X, y = list(zip(*list_of_X_y_pairs))

    return X, y

def maybe_download(
    dest_dir: str = 'data/'):
    ' Clones all smglom git repositories into the given destination. '
    all_repositories = [
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
    ]
    return [
        download.maybe_download_git(
            repo_url=os.path.join('https://gl.mathhub.info/', repo),
            save_dir=path.join(dest_dir, '/'.join(repo.split('/')[:-1])))
        for repo in repositories
    ]