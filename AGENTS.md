# BrickLabo development rules

Keep all French/English release notes and validation summaries in the single
`documentation/NOUVEAUTES.txt` journal, newest version first. Do not create
versioned NOUVEAUTES, CHANGELOG, CONTROLE or release-notes TXT files. Historical
reports are preserved verbatim in its archives section. Use
`python tools/release_notes.py --version X.Y.Z --add --fr INPUT_FR --en INPUT_EN`
and keep input drafts outside the repository. Run `python tools/check_release.py`
before packaging; distribution builds and CI enforce the same check.

Run Qt tests through `tools/run_tests.py` to retain GUI-thread collection and
task shutdown. Record the tested version, OS and evidence. A Linux pass does not
establish native Windows execution. A final 1.0 release requires a clean final
full suite, Windows qualification, reference-set counts, backup/restore/update,
and recorded manual PC sessions and physical 65 x 23 mm / A4 prints. Use
`tools/check_release.py --for-final --evidence PATH` before claiming completion.

Original application code uses MIT. Third-party resources keep their independent
terms. Maintain `licences/RESOURCE_RIGHTS.json`; do not invent permissions or
relicense external catalogues/images/models. Do not contact third parties without
explicit user authorization. Preserve user data; use only disposable collections
for validation and never publish keys, personal databases, backups or private logs.

Maintain stable French/English quick-start links in documentation. Do not add
photo recognition or QR codes to the regular version.
