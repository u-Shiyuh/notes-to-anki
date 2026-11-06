# sources/

Pinned copies of the data `words.tsv` and `verbs.tsv` were built from, so `tools/check_data.py` runs offline and stays reproducible if upstream changes or disappears. Rebuild them with `python3 tools/check_data.py --refresh` after adding rows to either `.tsv` file. The pinned versions are set in `tools/check_data.py`.

| File | Source | Licence |
|---|---|---|
| `n5.csv`, `n4.csv` | [open-anki-jlpt-decks](https://github.com/jamsinclair/open-anki-jlpt-decks) `src/`, commit `1ad66734417aca9dbcca6b2d5ee440cb13ab3ba0`, unmodified. Built on [Jonathan Waller's JLPT lists](https://www.tanos.co.uk/jlpt/). | MIT, Copyright (c) 2020 Jamie Sinclair (notice below). Waller's lists: [CC BY](https://creativecommons.org/licenses/by/4.0/). |
| `jmdict-subset.json` | [JMdict](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project) via [jmdict-simplified](https://github.com/scriptin/jmdict-simplified) 3.6.2+20261102210542 (`jmdict-eng`, dictionary date 2026-11-02). **Changed:** only the entries for the words in `words.tsv` and `verbs.tsv` are kept (listed under `keys`); the entries themselves are unmodified. | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), © the Electronic Dictionary Research and Development Group ([EDRDG licence](https://www.edrdg.org/edrdg/licence.html)). This subset is shared under the same licence. |

The rest of this repository is not covered by these licences.

## open-anki-jlpt-decks licence

```
MIT License

Copyright (c) 2020 Jamie Sinclair

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
