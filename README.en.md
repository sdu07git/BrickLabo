# BrickLabo — v0.1.59

Windows desktop software for LEGO catalogues, stock, construction searches and labels. This version continues the published v0.1.58, based on the original v0.1.28.

**Downloads v0.1.59 :** [complete Windows package](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.59/BrickLabo_v0.1.59_Complet.zip) · [sources with resources](https://github.com/sdu07git/BrickLabo/releases/download/v0.1.59/BrickLabo_v0.1.59_Sources.zip) · [release notes](https://github.com/sdu07git/BrickLabo/releases/tag/v0.1.59).

## Loose stock partial transfers and excluded words — v0.1.59

**Loose stock only** : In Buildable sets → Choose usable stock, uncheck Use parts from My set stock to exclude all tracked components of owned sets, including future additions. Only loose parts and minifigures remain usable after project reservations. Details, exports and MOC suggestions use this choice. Individual set exclusions are preserved for later reactivation.

**Partial drag and drop** : Dragging counted entries from one drawer to another opens Quantities to move. Choose 20 out of 40: 20 stay in the source and 20 move to the destination. Multiple selected references have individual counts, applied atomically with undo/redo. Cancelling leaves all drawers unchanged. Uncounted references are moved in full without inventing quantities.

**Stock additions and cabinets** : After adding loose stock, a reference and color fully counted in one drawer follows the new total: 40 plus 10 becomes 50. Split, partial or unknown counts are preserved and new pieces remain unplaced. Owned set components remain separate from loose stock. Stock additions and automatic drawer changes are undone or redone together. Visible storage and open inventories refresh; hidden storage is refreshed when opened.

**Visible drawer counts** : The cabinet face displays the total when all drawer counts are known. Hover still lists each reference and color. Zero and unknown quantities remain distinct.

**Exclude search words** : Normal and advanced search accept -modulex to exclude items containing modulex in name, reference or category. brick -modulex -duplo combines required and excluded words. Set themes follow the same rule. Indexed and compatible searches agree; hyphens inside references such as 75192-1 remain literal.

**Validation v0.1.59:** all 762 tests passed on Qt/Linux, including 22 new tests; dialogs and cabinet checked at normal and compact sizes. [Detailed report](documentation/CONTROLE_v0.1.59.txt). Native Windows execution remains to be confirmed.

## Projects, drawer inventories and fixes — v0.1.58

- **Buildable sets** can create a project with the search copy count and **Exclude minifigures** option.
- **My projects** show the set in the right preview; double-click or **View set** opens its photo and inventory.
- **Choose a set** provides a paginated catalogue with thumbnails, photo preview, search, theme/year/source filters, advanced filters and saved filters. The new-project form also previews the chosen set.
- **Exclude minifigures** applies to requirements, percentages, details, exports and project creation. Intact stock figures are preserved. Legacy flattened API caches require a batch refresh; full Rebrickable CSV inventories can be used directly.
- **Drawers** show references, colours and physical counts on hover. Double-click opens an editable inventory. Unknown counts remain distinct from zero; stock bounds, edit conflicts and Undo/Redo are enforced.
- **Rebrickable CSV import** accepts **Set Number, Quantity, Inventory Ver**, preserving copy counts and requested inventory versions. Missing versions remain pending for correction; the latest version is never silently substituted.
- **Labels → Apply to → Entire Minifigures catalogue** applies a layout to every source, existing individual layouts and future references, preserving label colours, angles and 3D edges.
- **Stability** defers cyclic Python/Qt collection to the idle GUI thread after native tasks finish, and explicitly destroys windows there during shutdown. This addresses the v0.1.57 heap-corruption reports; native Windows confirmation is still required.


## Drawer quantities, action history and construction projects — v0.1.57

**My storage → Drawer contents** now shows **Quantity in this drawer** separately from **Global loose stock**. Select a reference and use **Quantity in this drawer…** to declare its count. The same reference and colour can be split between drawers: 100 owned parts can be 30 in one drawer and 70 in another, while total stock remains 100. **Transfer a quantity…** moves part of a count to another drawer or cabinet. Dragging a reference from a drawer also moves its declared quantity and merges it with the destination count.

In **Parts to store**, the **Remaining to store** column and **Remaining quantities to store** checkbox account for saved counts. From loose stock, dragging or **Assign to selected drawer** places the remaining quantity. For a partial allocation, adjust the drawer count or transfer part afterwards. Automatic storage offers **Allocate remaining quantities**: review counts in **Proposed cabinet → Drawer contents**, then apply. Reorganisation preserves existing declared counts. Catalogue references can still be assigned without owning the part; their quantities are **To be entered**.

Migration from v0.1.56 retains cabinets and assignments with quantities **To be entered** rather than copying total stock into each drawer. An explicit zero differs from an unknown count. Declared totals for each reference, source and colour cannot exceed loose stock. Reduce or remove affected drawer counts before lowering stock below its allocated quantity. **My stock → Columns** offers **Allocated to drawers** and **Remaining to store** to track allocations.

The top toolbar offers **Undo last action / Ctrl+Z**, **Redo / Ctrl+Y** and **Action history**. The journal retains 100 actions by default and survives restarts. Its window lists dates, descriptions and applied or undone states; **Retained actions** sets a limit from 1 to 500. It covers stock, the print queue, general and individual 3D colours, drawer assignments and counts, applied proposals and projects. Grouped imports and proposals restore atomically. Undo runs backwards through actions and redo replays their original order. A new change after undo replaces the remaining redo tail; rejected operations and unchanged values preserve it. Conflicting later edits prevent restoration. The last compatible v0.1.56 action is migrated without inventing its date.

**My projects** appears in navigation. **New project…** offers a **Catalogue set** or **Custom build**. A set catalogue’s context menu also offers **Create a construction project…**. For a set, load its complete local inventory, choose the number of copies and whether to include spare parts. Creation snapshots the requirements without adding or reserving stock. For a custom build, **Project parts → Add a part…** selects a local reference, colour and required count. That menu also edits requirements, removes selected rows and adjusts their reservations.

The project table shows **Planned**, **In progress** or **Completed**, requirements, reservations and missing quantities. Details show **Required**, **Reserved**, **Free in stock** and **Missing** for each reference and colour. **Reserve available stock** allocates free parts up to the requirements; **Reserve selection** only handles selected rows. **Adjust reservation…** sets an exact count. Projects share the same free pool: parts held by one cannot be reserved again by another. Reservations use only loose stock with the exact same source, reference and colour, without automatic equivalence or taking tracked components from owned sets.

Reservations preserve ownership and physical locations. **My stock → Columns** offers **Reserved for projects** and **Available for building**; buildable-set searches exclude reserved loose parts. A **Completed** project keeps reservations until **Release reservations**. Deleting the project releases them too. Release affected reservations before lowering stock or requirements below reserved counts. A drawer allocation and a project reservation describe the same part in different ways and are not added together to reduce stock.

**Backups → Projects and reservations** exports a new JSON family; **Cabinets and locations** includes drawer quantities. Restore the necessary loose stock too, or retain enough existing stock. Inconsistent restores roll back entirely. Old storage backups remain readable with unknown counts. Selective restoration clears the action journal; full ZIP backups preserve the database and its history. These functions use local data and require no API key.

## History: cabinet proposal preview and undo — v0.1.56

In **My storage → Store by category and size in studs**, choose **By category and size**, **One reference per drawer** or **Free reference grouping**. The first keeps the smallest-to-largest size order. The second gives each reference its own drawer: sources and variants stay distinct; colours of the same reference stay together unless **Separate colours** is checked. In free mode, select several rows with Ctrl or Shift, then **Group the selection…** to choose their shared drawer. The **Proposed drawer** lists also allow individual adjustments. Reference and free modes include parts and minifigures with unknown dimensions without inventing their sizes.

**Proposed cabinet** displays the cabinet front and proposed contents before saving. Assigned drawers are green; conflicts are red and prevent applying. Clicking a drawer selects its groups; double-clicking opens **Drawer contents**, with references, categories, colours, thumbnails and quantities. Quantities show global loose stock, not a physical distribution across drawers; an unowned catalogue reference shows 0. Reserved and mixed drawers remain visible. Zoom or drag the divider between the table and preview to inspect the cabinet. **Category** is also added to drawer contents in the main window.

The **Parts to store** selection is captured when this window opens; without a selection, displayed references are used. **Prepare a proposal** recalculates the draft. Groups without space remain reported and unassigned. **Close** discards the draft; only **Apply proposed storage layout** writes assignments. Prepare a new proposal if stock or storage has changed meanwhile. Stock quantities remain unchanged.

**Undo last action / Ctrl+Z** now also handles general 3D colour, individual reference colour, drawer assignments, reference moves between drawers, removals and applied storage proposals. The journal keeps one latest action and survives restarts. Storage undo restores affected drawer names and contents without changing stock. A new stock action becomes the latest action; incompatible later edits prevent undo instead of overwriting data.

## Background-task memory-crash fix — v0.1.55

This version keeps background tasks and their Qt signals alive until the native thread pool has finished using them, then releases callbacks and signal objects on the GUI thread. Results and progress are explicitly queued to that thread; late callbacks after closure are ignored. Error, cancellation and application-shutdown paths are covered too.

The v0.1.54 diagnostic reproduced Qt signal destruction on worker threads during BrickArchitect parsing. The fix removes that ownership defect without changing catalogues, stock, cabinets or labels. The exact Windows crash still requires a retest on the affected PC.

## Factory colour and wheel back views — v0.1.55

In the top panel, **3D colour → Defaults** restores the original yellow (`#f3d55b`) in the picker. **Apply** saves the choice and refreshes previews; **Cancel** keeps the previous colour. Individual colours and palettes retain priority.

The **Main and bottom views** layout now shows the back face of wheels and tyres along their axle, instead of their tread profile. Historical LDraw aliases retain their signed axle rotation. Brick undersides, the other views and custom main-view angles keep their orientation. The fix is included in previews and PNG/PDF exports.

## Small screens and adjustable top panel — v0.1.54

Catalogue search stays compact. Search, categories, columns, advanced filters and **Hide / Show decorated parts** share one row. When space is limited, move the horizontal scrollbar below these controls; filters no longer create extra rows. **Selection layout…** joins the actions below the table. Categories can be ticked or unticked in their menu, with search and select-all controls. No selected-category tag bar takes space above the table. The active exact-reference filter remains visible separately.

**Drag the horizontal border below the top button groups** up or down to shrink or enlarge the panel. Its height survives restart and preference backups. A vertical scrollbar keeps every top button accessible when the panel is reduced. Groups have smaller margins and fit their contents. The initial window fits the screen, with a minimum size of 800 × 480.

To exclude a group, open **Advanced filters → Categories**, click **Select all categories**, search for **duplo**, then **Uncheck search results**. Only matching categories are removed; other choices are kept. **Check search results** does the reverse. The catalogue category menu offers the same commands. No checked category removes the category filter and shows all categories.

In set catalogues, right-click offers **Add inventory to My stock** to add loose parts and minifigures, or **Add set to My set stock** to own the set with tracked components. **Add to stock…** offers both destinations. Multiple selections are supported; inventory colours and quantities are preserved, nested sets are expanded and spare parts are included. Missing or incomplete inventories stop the entire addition. Load inventories first; these actions trigger no download. Ctrl+Z undoes the addition.

In **My storage → Parts to store**, choose **Destination cabinet**. This focuses the cabinet for drag and drop and targets **Automatic storage…** and **Store by category and size…**. Automatic storage uses selected rows, or displayed references if none are selected, from the chosen stock or catalogue source. Categories are grouped and stud sizes sorted smallest first; drawers are proposed top to bottom, left to right. Review and apply the proposal; it creates storage links while preserving quantities. Unknown dimensions, groups without available drawers and occupied drawers remain identified.

**Right-click a drawer → Remove a reference from the drawer** lets you choose the part and colour to remove from that location. Other references, links to other drawers and stock are preserved. **Remove all references from the drawer…** requires confirmation. For drawers containing more than thirty rows, the menu also opens their contents table.

## Button help and API features — v0.1.53

Keep the pointer over a button for **two seconds** to see a brief explanation. Leaving, clicking or closing the window cancels the tooltip. Each new button starts its own two-second delay. Help covers controls across windows, standard buttons, checkboxes and controls created later; existing explanations are preserved. Help follows changing captions and the FR / EN language. It triggers no action and changes no data. Label-model hover previews remain immediate.

A **Rebrickable key** is required for these API operations: updating an RB reference’s photo and external matches; batch downloads of RB set inventories; downloading RB minifigure parts; fetching a set’s alternate builds; **MOCs using available parts…** (alternatives of sets covered by stock, without verifying the MOC’s own inventory); and online automatic BrickLink-to-Rebrickable part and colour conversion through **Convert BrickLink (RB API)** during stock export.

The **four BrickLink credentials** (Consumer Key, Consumer Secret, Token, Token Secret) are required for these API operations: updating a BL reference’s photo and fetching its colour palette; downloading BL set and minifigure inventories, including set batches; and fetching a reference’s available colours through **Load via BrickLink API (optional)**.

CSV / TXT imports, public Rebrickable exports, keyword / creator MOC search, public instructions, LDraw, stock, storage, label editing and printing remain available without keys. Buildable-set calculations use local inventories and require no key when the necessary data is present. Rebrickable CSV export also works without a key using known or manually corrected references; only automatic API conversion requires the key. Photo searches remain available without an API; configured credentials can add photos and reference matches. Credentials never appear in the new tooltips.


## Custom label models, categories and selections — v0.1.52

**Label editor → Label models** lists the three built-in layouts and models saved with **Save a model…**. Hover over an entry to see its label beside the menu without changing the draft. Click to choose a layout, edit its layers, then **Apply** to save it. **Delete this model** removes the menu choice while preserving applied layouts. JSON Load / Save as remain available.

**Apply to → Category** associates the draft with the chosen category across catalogues and future references. Priority: individual layout, category model, general model. Category colours follow the general settings. The physical sheet format remains general; layouts scale accordingly. **Follow the general model** removes the category association.

In **Print Labels**, part catalogues, stock or history, select multiple rows with Ctrl / Shift then use **Selection layout…**, also available in the context menu. The shared draft starts with the first selected row. Choose a model or adjust its layers, then **Apply**. Rows are captured on opening, including across pages; a deleted target interrupts application. All layouts commit together. Quantities, stock, colours, angles and individual edges are preserved. Catalogue selections configure references; Print Labels selections configure only those scoped entries and colours. Resetting an individual layout returns to its category model, or to the general model when none is assigned.

**Data updates → Update LDraw (complete.zip)** downloads the official library, validates the ZIP and indexes explicit header links. Failure preserves the active library. After successful activation, the previous managed archive in Donnees is removed if no other setting refers to it. The bundled complete.zip and external files are preserved. Manual complete.zip imports remain available and retain their earlier versions.

LDraw shortcuts recursively load their parts, stickers, subparts and primitives using each file’s positions and transformations. Bare parts do not receive arbitrary stickers. Only explicit, unique Rebrickable / BrickLink header links are used. Missing dependencies or unsupported TEXMAP patterns fall back to photographs. Verified example: **87552d02.dat**, official UPDATE 2026-09, loads **87552.dat** and **6177954b.dat** and identifies BrickLink **87552pb065R**. This version includes official library update 2026-09. Named models, category assignments and individual layouts are included in selective model backups.


## Two new label layouts — v0.1.51

In **Label editor → Label models**, choose **Centred main view** for a single centred view, without top or side views. Category and stud dimensions sit in the header, with references at the bottom. **Main and bottom views** places the main view on the left and a true underside view on the right. The classic layout with top and side views remains available.

The choice changes the draft: adjust layers if needed, then **Apply** to save. Presets are also available in the individual label editor. Current format, colours, transparency and edge settings are retained. Undo / redo, JSON templates and selective label backups preserve the layout.

The LDraw bottom view keeps its orientation when the main view rotates. Its layer supports adding, moving, resizing, cropping and zooming. A photograph alone cannot provide an underside; the preview explains when it is unavailable. Only requested views are rendered. PNG, PDF and printing share the same layout.




## Assign catalogue references directly to drawers — v0.1.50

In a part or minifigure catalogue, select one or more references and click **Assign to a drawer…**, using the button or right-click menu. Choose the cabinet and drawer, then **Assign references to drawer**. This creates storage links without adding stock, asking for a quantity or specifying a colour. It can reserve a drawer for a reference you do not own yet.

In **My storage → Parts to store**, **Source of parts to store** offers **Loose stock**, **All catalogues**, or Rebrickable, BrickLink, BrickArchitect, Alternative Bricks and Minifigures. Search or filter, select rows and drag them onto a drawer. **Add from a catalogue** also opens this view. Quantity is hidden in catalogue mode. **Unassigned only** hides references already assigned; clear it to assign a reference to multiple drawers.

Drawer contents can still be moved, searched, printed and backed up without owned stock. Variants and sources remain distinct. Stock shown in drawer contents remains informational and never creates ownership. With no specified colour, it shows total owned stock across all colours. A category already assigned to this cabinet can be reorganised by stud dimensions even with no owned quantity. **Loose stock** keeps its validation of actual owned references and colours.

## Spaced controls, external exports and assisted storage — v0.1.49

Top buttons have wider gaps and group margins. **PNG / PDF folder** accepts a folder on any PC drive and keeps it after restart. An offline external drive does not prevent startup; export reports a write error when needed.

Edge strength and width affect large renders, the right-hand preview and labels. Table and drawer thumbnails retain thin edges, including after restart or individual label changes. Changing only edges no longer reloads tables.

In **My storage → Parts to store**, search or filter loose stock, select multiple rows with Ctrl / Shift, then drag them onto a drawer in the cabinet view. The target is highlighted. Assigned parts are hidden by default; clear **Unassigned only** to show them. **Assign to selected drawer** also supports keyboard use. Dragging from **Drawer contents** moves only selected location links, preserving stock quantities and other locations.

**Store by category and size…** proposes drawers by category and dimensions in studs written in part names, from small to large: for example 1 × 1, 1 × 2, then 2 × 2. Explicit heights remain separate. Choose **Bricks** for a 30-drawer cabinet. Colours and variants share a size group unless **Separate colours** is selected; references retain their identities. Adjust the proposed drawers before applying.

By default, the proposal uses unassigned parts and empty unnamed drawers. Groups exceeding capacity and references without dimensions remain for manual assignment. **Reorganise this category in this cabinet** can replace associations in drawers containing only that category, provided every existing reference receives a proposed location. Mixed drawers and other cabinets remain intact. A stock or storage change invalidates the preview. Physical parts still need to be moved according to the selected plan.

## Import correction assistant and readable buttons — v0.1.48

In **My stock** or **My set stock → Import collection**, open a Rebrickable CSV or BrickLink CSV / TXT / XML list. The application saves a correction job and its original rows inside **Donnees**. **Add ready rows** imports valid references, colours and quantities; other rows remain pending. Unknown references, invalid quantities, colours absent from their source palette and incomplete set inventories no longer block valid rows.

Select a pending row, edit **Source / type**, **Reference**, **Colour** and **Quantity**, then **Save correction**. **Search the catalogue…** chooses a local reference by name, reference or category. Changing source requires a new colour choice: BrickLink and Rebrickable colour IDs remain separate. Variants are never merged automatically. If a set inventory has been loaded in the meantime, use **Recheck rows**.

Close and reopen the assistant, choose the job in **Pending imports…**, then **Resume this import**. The original file is no longer required. Applied rows are marked and cannot be added twice; later corrected parts join the same personal inventory. The destination is retained after the first addition. If only sets have been added, the inventory for pending parts can still be chosen. A deleted destination inventory can be replaced explicitly, without reimporting earlier rows. **Undo last action / Ctrl+Z** restores both stock quantities and pending markers from the latest addition. Full **Donnees** backups include these jobs.

The right preview panel is wider. Long action bars wrap according to available width, and photo-link buttons use separate rows. Catalogues, notices, imports and cabinets scroll in smaller windows so their controls remain accessible. The Rebrickable instructions button wraps its label where needed. Cabinet controls remain accessible at **950 × 650** and **1366 × 768**.

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

To move from a version older than v0.1.42, install this complete ZIP in a new folder and copy **Donnees** into it once, as described below. The new option will then handle future published releases. Version v0.1.50 is published on GitHub with the complete and source ZIPs already delivered and verified.

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

Version v0.1.50 is published on GitHub with the complete and source ZIPs already delivered and verified.

## v0.1.39 checks and fixes

Short SQLite reads share a read-only connection serialised between workers. Unchanged catalogue imports and visual settings avoid redundant updates and FTS5 rewrites. Computed minifigure categories survive reimport.

Decoded photos use a bounded 32 MiB RAM cache and LDraw text uses an 8 MiB cache. Repeated photo reads no longer reload the JSON provenance ledger. Rapid preview requests are coalesced and finish on the latest selection. Purging or changing settings prevents an older task from repopulating the cache.

Personal inventory imports are atomic, including inventory creation and stock updates. Multi-part additions form one undoable action. Colour changes retain totals and undo when rows merge. Failed BrickArchitect publication restores the previous catalogue and model archive.

Intermediate BrickArchitect downloads use the session in `Donnees/temp` and are removed after failure. **Clean temporary files older than 7 days** also handles the legacy `Donnees/temporaires` folder when present. Referenced files, recent files and active sessions are protected. Full backups exclude both temporary folders. Shutdown waits for workers before closing archives and cleaning the session. Browsing instructions no longer creates empty folders.

The launcher is rebuilt with the original icon in seven classic Windows bitmap sizes. Packaging verifies that embedded executable images match the supplied `.ico` and that bundled dependencies match the exact versions in `app/requirements.txt`. Explorer icon display still needs confirmation on Windows.

## Installation and new functions

Extract the entire complete ZIP into a new writable folder. Close the old version, keep a backup and copy **Donnees** beside the new **BrickLabo.exe**. Do not overlay installations. Migration preserves observed part totals and separates loose stock from tracked set components. It retains `Donnees/sauvegardes/avant_v37.sqlite` before moving legacy sets and never invents inventories for untracked sets.

- **My stock** contains loose parts and minifigures. **My set stock** contains sets and their saved total component quantities. The lower table supports previews, header sorting and double-click opening. Removing a set can discard components or move them to loose stock.
- **Undo / Redo / Action history** restores multiple changes to stock, the print queue, 3D colours, drawer contents and quantities, or projects and reservations. Ctrl+Z undoes; Ctrl+Y redoes. The journal survives restarts and is cleared by selective restoration. Conflicting changes prevent replay.
- **Import collection** accepts Rebrickable parts / sets CSV and BrickLink CSV, tab-separated TXT or XML. Select the source and destination. Sets going to loose stock are decomposed; parts going to set stock attach to an owned set or a named personal inventory. Valid rows are added; unknown references, invalid colours or quantities and incomplete inventories remain pending in the correction assistant. Save corrections and resume ready rows, even after closing.
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
| 0.1.48 | Partial imports with saved corrections, resumption, duplicate prevention and undo; buttons and scrolling adapted to small windows. |
| 0.1.49 | Spaced top controls, external exports, stable thin-edge thumbnails, part drag-and-drop and assisted storage by category and size. |
| 0.1.50 | Direct catalogue-to-drawer associations without stock or quantities; catalogue choices in Parts to store. |
| 0.1.51 | Centred main view and main plus bottom view label presets; editable LDraw underside and rendering of requested views only. |
| 0.1.52 | Named layouts with previews, categories and selections; official LDraw update. |
| 0.1.53 | Two-second button help and API access documentation. |
| 0.1.54 | Small screens, categories, set stock and destination cabinet for storage. |
| 0.1.55 | Qt task lifetime, factory colour and wheel back faces. |
| 0.1.56 | Cabinet proposal preview, one reference per drawer or free grouping, Category column and undo for 3D colours and assignments. |
| 0.1.58 | Projects and previews, drawer inventories, versioned CSV imports, figure layouts and memory protection. |
| 0.1.57 | Drawer counts and partial transfers, persistent undo/redo history, projects with requirements, reservations and missing parts. |

One bilingual [NOUVEAUTES.txt](documentation/NOUVEAUTES.txt) holds cumulative notes. This branch does not document a released 0.1.29. The 0.1.28b / Range variants were not used as the baseline. The [v0.1.59 validation report](documentation/CONTROLE_v0.1.59.txt) describes the checks for this delivery.

## Development and diagnostics

Install Python 3.12 and `app/requirements.txt` in a virtual environment, then run `python app/bootstrap.py`. Run `python tools/run_tests.py` for tests. On Linux with MinGW-w64, run `python tools/build_distribution.py path/BrickLabo_v0.1.37_Complet.zip output_folder`. The tool reuses libraries from the previous complete package and also accepts the old v0.1.36 layout. `BrickLabo.exe --self-test` writes `Donnees/diagnostic.json`; console equivalent: `app/python.exe -B app/bootstrap.py --self-test`. Tests run on Qt/Linux; the compiled launcher and archive structure are inspected. Native Windows execution remains to be checked on Windows.

Project: https://github.com/sdu07git/BrickLabo. Keep Donnees and private backups out of public repositories.

Check a built distribution: `python tools/check_distribution.py path/BrickLabo`.

For a compatible future update, publish a public stable release with tag `vX.Y.Z`, release notes and the **BrickLabo_vX.Y.Z_Complet.zip** file produced by this tool. GitHub must expose the asset’s SHA-256 `digest` in its API. GitHub’s automatically generated source archives cannot be installed. The application checks up to the 100 most recent releases and never publishes files.

To develop from this repository, take `ressources/complete.zip` from the source ZIP attached to the release: this LDraw archive exceeds GitHub's regular file size limit. GitHub's automatic source archives contain neither this resource nor the Windows runtime. Both attached ZIPs are the delivered and tested version; the repository READMEs are adapted for publication.

The [v0.1.59 validation report](documentation/CONTROLE_v0.1.59.txt) describes the checks for this delivery. Native Windows execution remains to be confirmed.



**Validation v0.1.54:** 617 tests covered on Qt/Linux, including 153 successfully rerun checks for changed features. Windows launcher, icon, dependencies and ZIPs checked. Native Windows execution remains to be confirmed.


**Validation v0.1.55:** 627 stabilisation tests passed on Qt/Linux, followed by 141 targeted tests after the colour / wheel additions, including 11 new regressions; 800 additional tasks checked in eight processes. Signals are destroyed on the GUI thread with no remaining wrappers after cleanup. Launcher, dependencies and ZIPs checked. The exact Windows crash still needs a retest on the affected PC.


**Validation v0.1.56:** 657 full-suite tests passed, followed by 86 targeted tests after individual colour undo was added and 49 after the final visual and help adjustments. The 21 new tests cover proposals, grouping, thumbnails, Category and persistent undo. Visual checks at 1360 × 790 and 800 × 540. Windows launcher and both ZIPs checked; native Windows execution remains to be confirmed.


**Validation v0.1.57:** 695 tests passed on Qt/Linux (Python 3.12, PySide6 6.11.2), including 36 new checks of counts, transfers, projects, backups and persistent history. Additional scenario with 183 references in 183 drawers, reservations, restart and Undo/Redo. Visual checks at 1360 × 790 and 800 × 540. Packaging validates the Windows launcher and both archives; native Windows execution remains to be confirmed.

**Validation v0.1.58:** all 740 tests passed on Qt/Linux, including 45 new tests. Versioned imports, projects, drawers and figure layouts checked; 120 real 3D tasks and 120 window workflows without errors. [Detailed report](documentation/CONTROLE_v0.1.58.txt). Native Windows confirmation remains required.
