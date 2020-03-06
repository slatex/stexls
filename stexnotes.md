### defi

`\adefi[name=edge]{Kanten}{Kante}` displays the string `Kanten` and indicates that the
base form is `Kante`. It is linked to the symbol `edge`.

`\adefii[name=empty-graph]{leere Graph}{leerer}{Graph}` displays the string `leere Graph`
and indicates that the base form is `leerer Graph`.
Longer base forms can be build with `\adefiii` and `\adefiv`.

`[name=...]` can be omitted, if the name is the base form with dashes (`-`) instead of spaces.
For example, `\adefii{index of summation}{summation}{index}` is an abbreviation for
`\adefii[name=summation-index]{index of summation}{summation}{index}`.


`\defi[name=node]{vertex}` is an abbreviation for `\adefi[name=node]{vertex}{vertex}`.
`\defii[name=eigenvector]{characteristic}{vector}`
is an abbreviation for `\adefii[name=eigenvector]{characteristic vector}{characteristic}{vector}`.
Same for `defiii` and `defiv`.
`[name=...]` can be omitted in the same way as for `\adefi`s.

`\Defi[name=node]{vertex}` is an abbreviation for `\adefi[name=node]{Vertex}{vertex}`,
i.e. the first letter in the displayed string gets capitalized.

`\defis[name=edge]{line}` is an abbreviation for `\adefi[name=edge]{lines}{line}`,
i.e. an `s` gets appended to the displayed string.

`Defis` capitalizes the first letter and appends an `s`.

For all `Defi`, `defis` and `Defis`, the `[name=...]` parameter is optional
and the `ii`, `iii` and `iv` forms exist as well.

### trefi

`\mtrefi[category?arrow]{Morphismus}` references the symbol `arrow` in module `category`
and displays it as the string `Morphismus`.
Similarly, `\mtrefii[cgroup?commutative-group]{Abelian}{group}`
references the symbol `commutative-group` in the module `cgroup` and displays it as `Abelian group`.
Same for `mtrefiii` and `mtrefiv`.

`\trefi[metric-space]{metric}` is an abbreviation for `\mtrefi[metric-space?metric]{metric}`.
If the module name is not specified, it is assumed to be the current module.
Similarly, `\trefii[vector-space]{vector}{addition}` is an abbreviation
for `\mtrefii[vector-space?vector-addition]{vector}{addition}`.
Same for `mtrefiii` and `mtrefiv`.

`Trefi`, `trefis`, `Trefis` etc. behave analogous to `Defi`, `defis`, `Defis`, etc.

`atrefi` etc. are deprecated and shouldn't be used anymore!


### symi

`\symi{homogeneity}` introduces the symbol `homogeneity`.
`\symii{affine}{space}` introduces the symbol `affine-space`.
Same for `symiii` and `symiv`.

If the `\symdef` command has the optional parameter `name=...`,
it introduces a new symbol with a the specified name.
Note that a symbol may be introduced multiple times this way.

`\symi*` is the same as `\symi`.


### module environments

`modsig`: signature module. It's the only type of module that may contain `symi`s.

`mhmodnl`: language module. There must be a signature module with the same name.
All symbols introduced with a `defi` variant in a language module must be
introduced in the signature module.

`module`: mono-lingual module. Here, the `defi` variants introduce new symbols themselves.

`modnl`: same as `mhmodnl` but with different parameters (it uses the `load` parameter, see discussion in *imports* section).

### imports

`\gimport[smglom/numthy]{kroneckerdelta}` imports all symbols from the `kroneckerdelta` module
in the `smglom/numthy` repository.
If the repository is not specified, it is assumed to be the current repository.
`gimport`s can only be used in signature modules and mono-lingual modules.

`\importmhmodule[mhrepos=MiKoMH/CompLog,dir=pl1/en]{pl1-syntax}` 
imports all symbols from from the `pl1-syntax` module in the directory `pl1/en` in the repository
`MiKoMH/CompLog`.
As always, the optional parameters are optional.

`guse` essentially does the same thing (and has the same arguments as) `gimport`. However, the imported symbols are 'exported',
i.e. if module *A* has a `guse` to *B* and module *C* imports module *A*, then module *C* won't import the symbols from *B*.

`usemhmodule` essentially does the same thing (and has the same arguments as) `importmhmodule`.
However, the symbols are again not exported.

`importmodule` and `usemodule` do the same as `importmhmodule` and `usemhmodule` except that they use the
`load` parameter instead.
For example `\importmhmodule[mhrepos=foo,dir=bar]{baz}` does the same as `\importmodule[load=/path/to/MathHub/<foo>/source/<bar>]{baz}`.
The are rarely (if ever) used.


```
  \begin{gstructure}{mul}{monoid}
    \tassign{op}{multiplication}
    \tassign{unit}{one}
  \end{gstructure}
```


### Other

- If a language file lacks a `\defi` for an introduced symbol (unless the symbol was introduced with the parameter `noverb`)

