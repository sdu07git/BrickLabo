# BrickLabo — v0.1.47

Windows desktop software for LEGO catalogues, stock, construction searches and labels. This version continues the delivered v0.1.46, based on the original v0.1.28.

**v0.1.47 downloads:** [complete Windows version](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.47/BrickLabo_v0.1.47_Complet.zip) · [source code with resources](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.47/BrickLabo_v0.1.47_Sources.zip) · [release notes](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47). This release includes v0.1.46 and v0.1.47 fixes.


## Edge previews, default values and shutdown — v0.1.47

In **3D edges** and the individual label editor, **Default values** sets black strength to **86.3%** and width to **1 px**. The button updates the draft and preview; **Apply as general settings** or **Apply** saves it. **Cancel** keeps the previous settings. For an individual label, defaults become its own override; **Use general settings** restores inheritance of the current general values.

Black strength and width changes reuse the surface and depth calculation in RAM. All visible strokes are rasterised together, so crossings and duplicate lines no longer accumulate opacity. 0% hides the edges; hidden and conditional edges remain respected. Rapid changes stop obsolete requests between views and finish on the latest settings. These calculations create no temporary render files.

On shutdown, the window remains visible with **Closing: stopping background tasks…** until workers finish. New requests and queued tasks stop; a local operation already underway completes safely. Interrupted downloads close their files and remove partial copies. The temporary-session lease closes before cleanup. Cleanup supports long paths and read-only temporary files. Real failures are logged; free abandoned sessions are retried at the next startup.

Rebrickable photo fallbacks now use **1,278 additional explicit, unique part links** already checked in the supplied BrickArchitect data. Official set and minifigure pages can confirm further links; normalised small BrickLink **MN/0** images are supported. Catalogue references, variants, inventories, 3D models and colour choices remain distinct. Captions identify the photo source; equal IDs alone do not create a link. Ambiguous colour mappings still require an explicit choice. Cached photos are reused without rewriting them.

## Rebrickable set 030-2 photo — v0.1.46

If the Rebrickable photo for **030-2 — Building Set** is unavailable, its preview uses the BrickLink photo through a verified cross-reference. This fallback requires neither a BrickLink catalogue import nor an API key. The complete **030-2** reference, including its leading zero, and Rebrickable catalogue data are preserved. **Photo BrickLink : 030-2** is shown under the preview (translated in the English interface).

Set photos now accept a single explicit cross-reference in photo metadata; similar or ambiguous references are not treated as equivalent. An available Rebrickable photo keeps priority. The fallback supports large and normalised small BrickLink images. Later views reuse the shared cache without rewriting images.

## Storage, set actions and update cleanup — v0.1.45

In **My storage**, use the **wheel** or **− / +** buttons to zoom; **Shift + wheel** scrolls. **Zoom to cabinet** isolates and fits the selected cabinet. **Full view** enables **All cabinets** and fits the whole layout after zooming or panning. The percentage shows the current zoom. **Drawer preview size** changes thumbnail size inside the available face; it is retained and included in other-preference backups. Names, addresses and handles stay clear, including mixed or wide drawers. These controls reuse the shared thumbnail cache.

**Organise cabinet → Rename cabinet…** changes its name without moving drawers or changing their references. **Remove drawer references** removes selected rows from the lower table. With no selection, it offers to remove all references from that drawer and asks for confirmation. Parts, colours, quantities and links to other drawers are preserved in stock.

In **Sets containing**, right-click a set to **Show original box**, **View alternate builds** or **Show in the set catalogue**. Alternate builds use the existing Rebrickable window and the same API-key and availability requirements. Catalogue navigation selects the correct source, clears filters hiding the set and selects its exact reference. Remove the **Exact reference: … ×** tag to return to ordinary search results. The consultation stays open and sorted table actions retain the correct set identity.

After an integrated update and successful startup of the new version, old software copies created by the installer in **Donnees/maj/b…** are automatically removed in the background. Interrupted installation rollback files are preserved; a locked file is retried at the next startup. **Donnees**, personal backups and files outside the software are preserved. This does not scan the disk for other manually extracted installation folders.


## Category selection, drawer dragging and A4 printing — v0.1.44

**Categories.** In advanced filters, click **Select all categories**, then uncheck categories to exclude or remove their tags with ×. This also selects categories hidden by the search. The counter shows the selection, which can be saved as a preset. **Clear selected categories** restores a search without a category filter.

**Moving drawers.** Use **My storage → Organise cabinet → Move drawers** and drag a drawer to another cell. In **All cabinets** view, it can move to another cabinet. Drawers with the same width and height swap positions, even if both contain references. A large drawer can use several unnamed empty cells; its old cells become empty standard drawers. Incompatible occupied locations and drops outside a cabinet are rejected. Names, references, colours and stock quantities are preserved; the move is saved on mouse release. Uncheck **Move drawers** to finish. This mode and **Arrange cabinets** are mutually exclusive.

**A4 printing.** Use **Organise cabinet → Print cabinets on A4…**. The independent preview offers the selected cabinet, one page per cabinet or an overview preserving their positions, in portrait or landscape. The front view has a white background, names, column / drawer addresses and up to three thumbnails per drawer. Choose a printer or **Export to PDF…**. Thumbnails use the shared cache and are reused in memory for page changes, orientation changes and printing. Unavailable images fall back to references. The preview keeps the layout captured when it opened: reopen it after changing your storage.

## Cabinet arrangement and deletion — v0.1.43

In **My storage**, **All cabinets** displays every cabinet at its saved position and searches across the layout. Uncheck it to view only the selected cabinet. Clicking a drawer selects its cabinet and displays its contents.

**Arrange cabinets** lets you drag a whole cabinet by its front or name, alongside or above others. Click **Finish arranging** to select drawers again. Positions are saved only when you release the mouse and survive restarting. Moving, rotating and zooming do not generate rendering files.

For precise placement, use **Organise cabinet → Position cabinet…**. Choose a reference cabinet and **To the left**, **To the right**, **Above** or **Below**, adjust the gap, then save. Coordinates use standard drawer units; a negative vertical value places the cabinet above the origin. This window also allows renaming. Cabinets cannot overlap; enlarging a drawer into a neighbouring cabinet is rejected until that cabinet is moved.

**Organise cabinet → Delete cabinet** asks for confirmation, then removes that cabinet, its drawers and their storage links. Loose parts, sets and their quantities are preserved. Editors belonging to the deleted cabinet close. Positions are included in **Cabinets and locations** backups; old cabinets and backups without coordinates are placed alongside each other.

## Updates from GitHub — v0.1.42

Use **Data updates → Check for a software update** to check public stable releases in the BrickLabo repository. Equal, older and prerelease versions are ignored. Checks are manual and require no API key. Release notes appear in an independent window.

**Download complete ZIP** prepares the Windows distribution and verifies GitHub’s SHA-256, the software version, the 64-bit executables and archive content. Source ZIPs, incomplete files, unsafe paths and archives containing `Donnees` are rejected. **Cancel download**, or close the window before installation, discards preparation without changing the installed software. Automatic installation requires the complete Windows distribution; source mode can view releases.

**Install and restart** closes BrickLabo after running tasks and SQLite are closed. Close other instances first; complete or cancel a pending data restoration. A small isolated runtime allows replacement without using DLLs still open in the application. Personal files, stock, templates, storage locations, settings and keys in **Donnees** remain in place. A replacement error or failure to launch the executable restores the previous files. A later startup error inside the new version still needs diagnosis using logs and a compatible backup.

Old application files stay in **Donnees/maj/b…** during replacement. From v0.1.45, recognised old copies are deleted automatically after successful startup, while interrupted transactions retain their rollback files and locked files are retried at the next startup. **Donnees** and personal backups are preserved. Work files remain in **Donnees/temp/u…**, using short names and Windows long-path access. The ZIP and unpacked copy are deleted after successful installation; inactive isolated-runtime leftovers are cleaned at the next startup or by temporary-file cleanup. Active installers and workspaces needed to recover interrupted transactions stay protected.

After a power loss during replacement, close every instance, inspect the `stage` field in `Donnees/maj/transaction.json`, open a terminal in the corresponding `Donnees/temp/u…` folder and run `r\python.exe -I -B i.py --recover`. Recovery verifies the retained plan, restores old files and restarts the application. If preparation is lost, use Explorer with all instances closed to copy the files in `Donnees/maj/b…` back into the installation folder, without moving `Donnees`. A deliberate downgrade also requires a compatible data backup if its format changed.

To move from a version older than v0.1.42, install this complete ZIP in a new folder and copy **Donnees** into it once, as described below. The new option will then handle future published releases. Version v0.1.47 is available in [GitHub releases](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47), with the complete Windows ZIP and source ZIP.

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

Version v0.1.47 is available in [GitHub releases](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.47), with the complete Windows ZIP and source ZIP.

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
| 0.1.43 | Cabinet deletion and persistent arrangements alongside or above others. |
| 0.1.44 | Select all categories, drawer dragging and swaps, A4 cabinet printing / PDF with thumbnails. |
| 0.1.45 | Storage zoom and preview sizing, cabinet rename and reference removal, containing-set actions and old update-copy cleanup. |
| 0.1.46 | Verified BrickLink photo for Rebrickable set 030-2, source caption and normalised small set images. |
| 0.1.47 | Faster RAM-based edge previews, default-value buttons, visible worker shutdown and stronger temporary cleanup; verified catalogue photo links. |

One bilingual [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) holds cumulative notes. This branch does not document a released 0.1.29. The 0.1.28b / Range variants were not used as the baseline. Test reports are excluded from the source package.

## Development and diagnostics

Install Python 3.12 and `app/requirements.txt` in a virtual environment, then run `python app/bootstrap.py`. Run `python tools/run_tests.py` for tests. On Linux with MinGW-w64, run `python tools/build_distribution.py path/BrickLabo_v0.1.37_Complet.zip output_folder`. The tool reuses libraries from the previous complete package and also accepts the old v0.1.36 layout. `BrickLabo.exe --self-test` writes `Donnees/diagnostic.json`; console equivalent: `app/python.exe -B app/bootstrap.py --self-test`. Tests run on Qt/Linux; the compiled launcher and archive structure are inspected. Native Windows execution remains to be checked on Windows.

Project: https://github.com/sdu07git/BrickLabo. Keep Donnees and private backups out of public repositories.

Check a built distribution: `python tools/check_distribution.py path/BrickLabo`.

For a compatible future update, publish a public stable release with tag `vX.Y.Z`, release notes and the **BrickLabo_vX.Y.Z_Complet.zip** file produced by this tool. GitHub must expose the asset’s SHA-256 `digest` in its API. GitHub’s automatically generated source archives cannot be installed. The application checks up to the 100 most recent releases and never publishes files.

When developing from this repository, copy `ressources/complete.zip` from the attached Sources ZIP: this LDraw archive exceeds GitHub’s file-size limit. GitHub’s automatic “Source code” archives include neither that resource nor the Windows runtime. The two attached ZIPs are the delivered and tested version; repository READMEs are adapted for publication.

**v0.1.47 validation:** 487 tests passed under Qt/Linux; archive consistency, dependency versions and the launcher’s embedded icon were verified. Native Windows execution remains to be checked.
