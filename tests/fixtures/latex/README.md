# Recorded LaTeX builds

Logs of real builds, read by the tests of the compile check (design 0020 §8). Each came from a small made-up document
built with `latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1` in Clank's TeX layer
(TeX Live 2023 as Ubuntu 24.04 packages it, latexmk 4.83), on 2026-10-25:

| File | The document |
| --- | --- |
| `clean.log` | Builds with no warning: a section, its reference, a citation of an entry in its bibliography |
| `warn.log`, `warn.blg` | Builds, with a label defined twice, an undefined reference and an undefined citation (natbib) |
| `broken.log` | Fails: `$\frac{1}{2$`, an argument never closed (TeX's own error, with no file and line) |
| `broken2.log` | Fails: an undefined control sequence on line 5 (`./broken2.tex:5:`) |
