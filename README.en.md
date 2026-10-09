# BrickLabo — v0.1.42

Windows desktop software for LEGO catalogues, stock, build searches and labels. This version uses the delivered v0.1.41 sources, based on the original v0.1.28.


## Updates from GitHub — v0.1.42

Use **Data updates → Check for a software update** to check public stable releases in the BrickLabo repository. Equal, older and prerelease versions are ignored. Checks are manual and require no API key. Release notes appear in an independent window.

**Download complete ZIP** prepares the Windows distribution and verifies GitHub’s SHA-256, the software version, the 64-bit executables and archive content. Source ZIPs, incomplete files, unsafe paths and archives containing `Donnees` are rejected. **Cancel download**, or close the window before installation, discards preparation without changing the installed software. Automatic installation requires the complete Windows distribution; source mode can view releases.

**Install and restart** closes BrickLabo after running tasks and SQLite are closed. Close other instances first; complete or cancel a pending data restoration. A small isolated runtime allows replacement without using DLLs still open in the application. Personal files, stock, templates, storage locations, settings and keys in **Donnees** remain in place. A replacement error or failure to launch the executable restores the previous files. A later startup error inside the new version still needs diagnosis using logs and a compatible backup.

Previous files are retained in **Donnees/maj/b…**, accessible through **Open the previous installation folder**. Work files remain in **Donnees/temp/u…**, using short names and Windows file access that supports long paths. The ZIP and unpacked copy are deleted after successful installation; inactive isolated-runtime leftovers are cleaned at the next startup or by temporary-file cleanup. Cleanup protects active installers and workspaces needed to recover interrupted transactions. Previous installations are excluded from data backups, measured in **Disk space**, and can be deleted manually after checking the new version.

After a power loss during replacement, close every instance, inspect the `stage` field in `Donnees/maj/transaction.json`, open a terminal in the corresponding `Donnees/temp/u…` folder and run `r\python.exe -I -B i.py --recover`. Recovery verifies the retained plan, restores old files and restarts the application. If preparation is lost, use Explorer with all instances closed to copy the files in `Donnees/maj/b…` back into the installation folder, without moving `Donnees`. A deliberate downgrade also requires a compatible data backup if its format changed.

To move from a version older than v0.1.42, install this complete ZIP in a new folder and copy **Donnees** into it once, as described below. The new option will then handle future published releases. 

## Transparent label backgrounds — v0.1.41

In **Label editor** or **Edit this label**, check **Transparent background**, then **Apply**. The setting is retained in the general or individual template, JSON templates and label-template backups. Uncheck it to restore the selected background colour. Existing templates remain opaque.

PNG files retain their alpha channel; PDF files and printing leave the label background unfilled. The editor checkerboard only shows transparency. Text, outlines and category bands remain visible. A photo with a white background keeps it; LDraw renders retain their transparent areas.

For adhesive vinyl, use media intended for inkjet printers, follow its manufacturer's instructions and check its thickness. A transparent background reveals the media; it does not create white ink. Print at actual size / 100% to preserve dimensions. Set media type and quality in the printer properties.

## Storage wall and inventory batches — v0.1.40

**My storage**, at the bottom of the left navigation, represents your cabinets in a projected 3D view or a front view. **Organise cabinet** creates cabinets and edits drawer names, positions, widths and heights. One unit is a standard drawer; enlarging a drawer merges empty neighbours. Populated neighbours must be moved first. Add new columns and rows as your storage grows.

Select a drawer and **Add stock references**. Link several loose-stock references and colours to one drawer or the same reference to several drawers without changing quantities. Drawer fronts show up to three shared previews and a custom name; the lower table lists every reference. **Total loose stock** is the global owned quantity, not a drawer count. Zero-stock references retain their locations.

Search by reference, name, dimensions, colour or drawer name. `1x1` and `1 x 1` are equivalent. **All cabinets** searches across the layout; selecting a result displays and highlights its drawer with an address such as **Column 3 · Drawer 5**. Adjust the angle, switch to front view, use **Ctrl + wheel** to zoom and **Fit wall** to recenter. Moving and rotating the wall writes no rendering files. **Backups → Cabinets and locations** exports storage separately; full backups include it too.

Consultation windows, construction searches, inventories, instructions, previews and editors are modeless. You can keep them open while using the main window or other windows. Changing stock invalidates old construction results and asks you to rerun the search. Confirmations, file choosers and certain immediate inputs still wait for an answer.

Use **Data updates → Load set inventories in batches** to list Rebrickable or BrickLink sets by reference / name / theme, select rows or enter known catalogue references. **Queue selected sets** saves a queue. Batch size ranges from 10 to 1000. **Load next batch** stops after one batch; **Continue through batches** runs until paused. Complete local inventories are skipped by default; refresh is an explicit queue option. Queues, successes and errors survive closing and restarting. **Retry failed items** requeues errors only. An interrupted inventory page is not published as a partial inventory. Downloads require the source API credentials. Rebrickable requests are spaced; authentication or throttling failures stop the batch and preserve the queue.

Loaded inventories do not mark sets as owned or add parts to stock. They feed **Buildable sets** and suggestions of alternatives from rebuildable sets. Official-set inventories are not a complete MOC inventory catalogue: API v3 does not provide general MOC inventories. Exact MOC comparisons require the MOC's own inventory. For a full Rebrickable catalogue, use its existing CSV downloads.



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
| 0.1.40 | Storage wall, independent windows and inventory batches. |
| 0.1.41 | Transparent label backgrounds, exports and printing. |
| 0.1.42 | Verified GitHub updates, installation after shutdown and rollback. |

One bilingual [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) holds cumulative notes. This branch does not document a released 0.1.29. The 0.1.28b / Range variants were not used as the baseline. Test reports are excluded from the source package.

## Development and diagnostics

The repository retains the source ZIP layout. `ressources/complete.zip` is excluded from Git because it exceeds GitHub’s file size limit. Copy this LDraw archive from **BrickLabo_v0.1.42_Sources.zip** or **BrickLabo_v0.1.42_Complet.zip**, available in [releases](https://github.com/sdu07git/BrickLabo/releases), to recover the shipped models and run tests that need them. GitHub’s automatic “Source code” archives omit this file.

Install Python 3.12 and `app/requirements.txt` in a virtual environment, then run `python app/bootstrap.py`. Run `python tools/run_tests.py` for tests. On Linux with MinGW-w64, run `python tools/build_distribution.py path/BrickLabo_v0.1.37_Complet.zip output_folder`. The tool reuses libraries from the previous complete package and also accepts the old v0.1.36 layout. `BrickLabo.exe --self-test` writes `Donnees/diagnostic.json`; console equivalent: `app/python.exe -B app/bootstrap.py --self-test`. Tests run on Qt/Linux; the compiled launcher and archive structure are inspected. Native Windows execution remains to be checked on Windows.

Project: https://github.com/sdu07git/BrickLabo. Keep Donnees and private backups out of public repositories.

Check a built distribution: `python tools/check_distribution.py path/BrickLabo`.

For a compatible future update, publish a public stable release with tag `vX.Y.Z`, release notes and the **BrickLabo_vX.Y.Z_Complet.zip** file produced by this tool. GitHub must expose the asset’s SHA-256 `digest` in its API. GitHub’s automatically generated source archives cannot be installed. The application checks up to the 100 most recent releases and never publishes files.
