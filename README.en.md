Version 0.1.36 — Category tags, previews and sorting

Advanced filters now support multiple removable category tags (OR between
categories, AND with other filters). Saved filters retain tags and older presets
remain supported. Buildable set parts display a 3D preview with photo fallback.
Click result table headers to sort sets, parts, MOCs and alternate builds.
Quantities sort numerically; actions and previews keep the correct row identity.
MOC windows retain construction photos: detailed MOC inventories are not supplied
by the API. Part previews apply to locally available set inventories.

Version 0.1.35: right-click a result in Buildable sets from My Stock and choose
View alternate builds. Uses the configured Rebrickable API key for the selected
set; stock quantities remain unchanged.

v0.1.33 — Part preview, exports and outlines

Double-click a part in the lower Buildable sets table to open its 3D/photo preview. Missing and owned part reports can be exported as CSV for the selected set. Owned reports distinguish total stock from the amount usable for the requested copies. Ignored colours remain marked *. These are BrickLabo reports, not direct Rebrickable import files. Reports use the displayed snapshot; rerun the search after stock changes.

Outlines now lists only categories used by parts. Set themes are excluded.

Extract the full ZIP into a new folder. Close the old version and copy its Donnees folder next to the new exe. Keep the old installation as backup.

## v0.1.32 — FTS5 search and buildable sets

Includes the indexed search and combined advanced filters from v0.1.28b, with saved presets. The first launch indexes existing records; subsequent imports maintain the index automatically. A classic-search fallback remains available if FTS5 trigram is unavailable.

In My Stock, open Buildable sets from My Stock. Choose a source, minimum percentage (100% by default), copy count and whether to ignore colours. Select a result to inspect required, owned and missing quantities; double-click to open its details. Calculations use locally available inventories. Incomplete inventories are excluded. Cached unambiguous BrickLink mappings are reused. Results are evaluated separately and do not reserve or deduct stock.

Extract into a new folder, close the old application and copy its Donnees folder next to the new executable. Keep the old installation as backup. Original folder layout and previous export/alternate-build features are preserved.

v0.1.31 — Export all stock as two Rebrickable lists

Mon Stock / My Stock now offers a review dialog. stock_sets.csv contains owned sets; stock_pieces.csv contains loose parts after subtracting tracked set components. Import into separate My Set Lists and My Parts Lists. Avoid duplicating existing collection lists. BrickLink references and colors can be converted using your Rebrickable API key; ambiguous or missing matches require review. Exclusions are recorded in stock_rapport.txt. Stock is not modified.

v0.1.30 — based on the original v0.1.28

Right-click a set and choose View alternate builds. Requires a Rebrickable API key and Internet. A separate window provides the paginated list, designer, part count, photo and instructions link. No stock changes.
Generated cache names and temporary file names are shorter. PNG/PDF writes are atomic; failed batches show an error without a success history entry. Original folder layout preserved.
Extract in a fresh folder and copy your old Donnees folder beside BrickLabo.exe while the application is closed. Keep a backup.

# BrickLabo by SDU7 — v0.1.28

[Français](README.md) · [English help](AIDE.en.html) · [Sources and licences](SOURCES_ET_LICENCES.en.html)

BrickLabo is a portable Windows application for browsing LEGO parts and sets, managing stock, designing labels, generating PDF/PNG files and printing them. It uses Python, PySide6/Qt, SQLite and LDraw, with Rebrickable and BrickLink photos when available.

## Windows portable package

Extract the entire Windows Portable ZIP into a short, writable path. Launch **BrickLabo.exe**. Python does not need to be installed separately. Keep all files and folders supplied with the executable.

When updating, close BrickLabo, extract the new version into a separate folder and copy your **Donnees** folder beside the new executable. Keep the previous installation for rollback. The v0.1.21 launcher and flat layout are retained; runtime files have not been relocated.

The complete portable package includes the supplied Rebrickable, BrickLink and LDraw resources. The source ZIP contains the application code, tests, documentation and supporting resources; use the complete portable package or import your own bulk catalogue files for the full data libraries.

## Interface language

Click **Langue / Language**, select **English**, save, then close and restart BrickLabo. The choice is stored in Donnees/atelier.sqlite. French remains the default.

Menus, submenus, right-click commands, tooltips, application messages, print-preview controls and help are translated. Part names, category names, references, imported colour names, user-entered text and saved label content remain unchanged. Native Windows file and printer windows use the Windows display language.

English documentation is provided in AIDE.en.html, README.en.md, SOURCES_ET_LICENCES.en.html and NOUVEAUTES.en.txt. Original third-party licence files are retained without translation or alteration.

## Main features

- Separate Rebrickable and BrickLink catalogues, BrickArchitect, minifigures, alternative parts and sets, My stock, label queue and history.
- Search references, names and categories; normalise dimensions such as 1x1 and 1 x 1; filter sets by year.
- Sort the entire catalogue before pagination; show, hide and reorder columns. Single-row selection is enough to use an action button; use Ctrl/Shift for multiple selections.
- Part/set relationship windows, original-box previews, local and online PDF instructions.
- Individual visual selection, multiple photos, local images, LDraw camera settings and saved viewpoints.
- General and per-label layouts, layers, free text, crop/zoom, category outlines and 3D edge presets up to 10 pixels.
- PDF, PNG and combined output; print preview with printer selection and supported system options.
- First import date, disk usage measurements, bounded thumbnail caches and selective temporary-file/LDraw-copy cleanup.

## Manual BrickLink inventories

Select a BrickLink set and click **Add inventory from a TXT file**. References, BrickLink colour IDs, quantities and inventory flags are saved in SQLite. The source TXT can then be deleted.

Extra parts are included in automatic additions; alternatives and counterparts are retained in the inventory but excluded from automatic additions to avoid double counting. Reimporting replaces the set inventory without changing existing stock quantities. S-reference.txt files can also be imported through Data updates after the Sets catalogue is imported. This feature does not require BrickLink API access.

## Backups and restoration

**Backups** creates a verified private ZIP of Donnees, including a consistent SQLite snapshot, stock, inventories, settings, API keys, images and instructions. Caches, logs, downloaded catalogue files and temporary files are excluded. Files outside Donnees are not copied.

Choose a backup destination outside Donnees. Keep backups private: they include API keys. Restoration is prepared while the application runs and applied at the next startup. The previous state is preserved in Donnees_avant_restauration_… beside the software. Cancel a scheduled restoration before restarting if needed.

## Files and diagnostics

Application-owned personal data is kept in **Donnees beside the executable**, without an AppData storage fallback. **ressources** contains supplied resources. Output uses your configured PNG/PDF folder.

Open **Logs**, or use OUVRIR_LOGS.bat, to inspect text logs. **Disk space** measures application folders. Double-click a row to open its folder. It can clear thumbnails, clean old unreferenced temporary files or remove inactive identical LDraw copies. It does not measure or clean the global Windows Temp folder.

## Running or building from source

On Windows, install Python 3.12, run INSTALLER_DEPENDANCES.bat, then DEMARRER.bat. Developer batch messages are bilingual. CONSTRUIRE_EXE.bat builds a PyInstaller folder; keep the entire output folder and included resources.

For development on another system, create a virtual environment, install requirements.txt, then run `python main.py`. The portable executable and native Windows printing require Windows.

The project is available at https://github.com/sdu07git/BrickLabo. Keep personal Donnees folders and private backups out of public source uploads.
