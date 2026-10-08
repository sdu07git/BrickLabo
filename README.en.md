# BrickLabo — v0.1.39

Windows desktop software for LEGO catalogues, stock, build searches and labels. This update uses the delivered v0.1.38 sources, based on the original v0.1.28. The incorrectly modified GitHub checkout was not used as the baseline.

## v0.1.39 checks and fixes

Short SQLite reads share a read-only connection serialised between workers. Unchanged catalogue imports and visual settings avoid redundant updates and FTS5 rewrites. Computed minifigure categories survive reimport.

Decoded photos use a bounded 32 MiB RAM cache and LDraw text uses an 8 MiB cache. Repeated photo reads no longer reload the JSON provenance ledger. Rapid preview requests are coalesced and finish on the latest selection. Purging or changing settings prevents an older task from repopulating the cache.

Personal inventory imports are atomic, including inventory creation and stock updates. Multi-part additions form one undoable action. Colour changes retain totals and undo when rows merge. Failed BrickArchitect publication restores the previous catalogue and model archive.

Intermediate BrickArchitect downloads use the session in `Donnees/temp` and are removed after failure. **Clean temporary files older than 7 days** also handles the legacy `Donnees/temporaires` folder when present. Referenced files, recent files and active sessions are protected. Full backups exclude both temporary folders. Shutdown waits for workers before closing archives and cleaning the session. Browsing instructions no longer creates empty folders.

The launcher is rebuilt with the original icon in seven classic Windows bitmap sizes. Packaging verifies that embedded executable images match the supplied `.ico` and that bundled dependencies match the exact versions in `app/requirements.txt`. Explorer icon display still needs confirmation on Windows.

## Installation and new functions

Extract the entire complete ZIP into a new writable folder. Close the old version, keep a backup and copy **Donnees** beside the new **BrickLabo.exe**. Do not overlay installations. Migration preserves observed part totals and separates loose stock from tracked set components. It retains `Donnees/sauvegardes/avant_v37.sqlite` before moving legacy sets and never invents inventories for untracked sets.

- **My stock** contains loose parts and minifigures. **My set stock** contains sets and their saved total component quantities. The lower table supports previews, header sorting and double-click opening. Removing a set can discard components or move them to loose stock.
- **Undo last action / Ctrl+Z** reverses the latest stock or print-queue add, import, removal, quantity or colour change. Imports are single actions; the journal survives restarts and stock restores reset it. Later conflicting changes prevent undo.
- **Import collection** accepts Rebrickable parts / sets CSV and BrickLink CSV, tab-separated TXT or XML. Select the source and destination. Sets going to loose stock are decomposed; parts going to set stock attach to an owned set or a named personal inventory. References and complete inventories must exist locally. Validation errors stop the batch before stock quantities change.
- Rebrickable exports produce owned sets and loose parts CSV lists without double-counting tracked set components. Review colour and reference mappings. Personal ALT inventories are not official sets.
- Build searches combine loose stock and enabled set components. The upper table shows set photos; drag a header boundary to resize any column, including **Set**. Photos stay with their references after sorting and use the shared cache. Reserve sets or coloured parts without deleting them. Each proposal uses the same stock independently.
- **MOCs by keyword / creator** is available in the Rebrickable, BrickLink and alternative set catalogues, as well as stock screens. The button carries over the catalogue keyword: enter `falcon`, open this search and click **Search**. It searches all MOCs and alternate builds published on Rebrickable independently of owned sets. Enter an exact creator profile name on its own or with a keyword. Both original MOCs and alternatives are included by default; alternatives-only and free-only filters are optional. Public online search reads one page at a time; **Load more** continues. Selecting a result loads its photo and the base sets published by Rebrickable, with links to help plan a purchase. Original MOCs may have no base set. Previously viewed results form a non-exhaustive local cache. Open the same search on Rebrickable if a page cannot be read.
- The v3 API has no global MOC search or full MOC inventories. Public page structure may change. Stock-based suggestions use alternate builds of rebuildable sets; verify parts and instructions on the website.
- **Label editor → Add a part** binds another reference, colour and 3D / photo mode to image and reference layers. Move, resize, duplicate, hide or remove each layer, then Apply to save the composition for future prints.
- **Backups → Export selected families** creates separate JSON files for label templates, category colours, 3D views / render settings, loose stock, sets / components, print queue and preferences. API keys are optional and unchecked by default. Restore only selected families; all selected files are validated and applied together. References are portable rather than local database IDs. JSON excludes local photos, LDraw archives and complete catalogue inventories; full ZIP backups remain available.
- **Disk space** adjusts thumbnail budgets (32 MiB RAM / 256 MiB disk). 0 MiB disk enables RAM-only thumbnails. Identical renders share a bounded 64 MiB RAM cache and simultaneous requests are coalesced. Cache hits do not rewrite files or their timestamps. Purging protects active temporary sessions and referenced user data.

## Layout, paths and help

Root files: **BrickLabo.exe**, **LISEZ-MOI.txt**, **PROJET_GITHUB.url**. Folders: **app**, **ressources**, **documentation**, **licences**; **Donnees** is created at startup. No BAT files are shipped. Libraries live in `app/lib`; `app/bootstrap.py` is the single entry point. Resources resolve from the software folder, independent of the working directory. Python / Qt temporary sessions live in `Donnees/temp` and are configured before Qt; abandoned sessions are cleaned. Short generated names provide extra margin. All Windows SQLite connections use win32-longpath with normal database locking. Windows and library limits still apply.

Read [English help](documentation/AIDE.en.html) and [component licences](documentation/SOURCES_ET_LICENCES.en.html).

## History since 0.1.27

| Version | Documented additions |
| --- | --- |
| 0.1.27 | BrickLink TXT inventories; full backups and restores. |
| 0.1.28 | French and English interface and help. |
| 0.1.30 | Alternate set builds; short cache and temporary names; atomic exports. |
| 0.1.31 | Separate Rebrickable sets and parts exports; BrickLink mappings. |
| 0.1.32 | FTS5, saved multi-criteria filters and buildable sets. |
| 0.1.33 | Part previews; missing / owned exports; part-category outlines. |
| 0.1.34 | Local Rebrickable / BrickLink / LEGO / LDraw colour mappings; explicit choices for ambiguous IDs 72 and 77. |
| 0.1.35 | MOC suggestions from rebuildable sets; stock filters for sets and parts. |
| 0.1.36 | Category tags, previews and sortable results. |
| 0.1.37 | Separate stocks, undo, collection imports, MOC search, multiple-part labels, selective backups, bounded caches and app layout. |
| 0.1.38 | Photos of buildable sets, resizable columns and global MOC / alternate-build search from all set catalogues independently of stock. |
| 0.1.39 | Optimised reads and caches, atomic imports, cleaned temporary work, worker shutdown and verified embedded icon. |

One bilingual [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) holds cumulative notes. This branch does not document a released 0.1.29. The 0.1.28b / Range variants were not used as the baseline. Test reports are excluded from the source package.

## Development and diagnostics

The repository follows the source ZIP layout: `app`, `ressources`, `documentation`, `licences`, `tests` and `tools`. The LDraw archive `ressources/complete.zip` exceeds GitHub's regular file size limit and is excluded from Git. To reproduce the delivered models, copy that file from the downloaded v0.1.39 source or complete ZIP. An [official LDraw archive](https://library.ldraw.org/library/updates/complete.zip) can also be placed at that path; models may change between versions. First-launch tests and the 3D diagnostic require this archive.

Install Python 3.12 and `app/requirements.txt` in a virtual environment, then run `python app/bootstrap.py`. Run `python tools/run_tests.py` for tests. On Linux with MinGW-w64, run `python tools/build_distribution.py path/BrickLabo_v0.1.38_Complet.zip output_folder`. The tool reuses libraries from the previous complete package and also accepts the old v0.1.36 layout. `BrickLabo.exe --self-test` writes `Donnees/diagnostic.json`; console equivalent: `app/python.exe -B app/bootstrap.py --self-test`. Tests run on Qt/Linux; the compiled launcher and archive structure are inspected. Native Windows execution remains to be checked on Windows.

Project: https://github.com/sdu07git/BrickLabo. Keep Donnees and private backups out of public repositories.

Check a built distribution: `python tools/check_distribution.py path/BrickLabo`.
