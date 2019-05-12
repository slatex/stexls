
class TokenizerFilters:
    # list of characters used to split the original text
    DEFAULT_DELIMETER = ' \n\t\r!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    DEFAULT_FILTER = DEFAULT_DELIMETER
    WHITESPACE_FILTER = ' \n\t\r'
    KEEP_MEANINGFUL_CHARACTERS = ' \n\t\r$%\'/<>@[\\]^`{|}~'
