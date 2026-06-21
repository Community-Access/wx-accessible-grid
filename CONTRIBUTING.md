# Contributing

**Contributions are welcome — anyone can contribute, and we want them.** This is
a Community Access open-source project, created by Taylor Arndt.

## Ways to help
- **Report bugs** — open an issue with what you expected, what happened, your OS,
  wxPython version, whether you use a webview, and your screen reader.
- **Test with screen readers** — NVDA, JAWS, Narrator (Windows), VoiceOver
  (macOS), Orca (Linux). Real-world a11y reports are the most valuable thing here.
  Tell us how arrow navigation, in-cell editing, and selection announced.
- **Send pull requests** — features, fixes, docs, examples.

## Ground rules
- **Accessibility first.** The whole point is a data grid that is fully
  keyboard-operable and reads correctly in NVDA and JAWS. The grid must speak the
  column header as you move across a row, the row header as you move down a
  column, and only the focused cell (never the whole table on every arrow).
  Changes shouldn't regress that; note how you tested.
- **Real ARIA grid, never a div soup.** We render a semantic `<table role="grid">`
  so the screen reader gets header association and row/column counts for free. A
  hand-drawn grid reads worse.
- **The model owns the truth.** The grid never mutates data directly — it asks the
  model and shows what the model says is now true, so an edit the user hears
  confirmed is the validated, normalized value.
- Keep it **dependency-light** — wxPython plus its sibling `wx-accessible-webview`.
- Match the existing style; format with `ruff format` (line length 100).

## Dev setup
```bash
pip install -e ".[dev]"
python examples/demo.py        # try it with a screen reader running
pytest                         # the model and renderer are tested without wx
```

## Pull requests
- Describe the change and how you verified it (which screen reader / OS, native
  or webview).
- One focused change per PR is easiest to review.

Thanks for helping make accessible data grids in wxPython the default, not the
exception.
