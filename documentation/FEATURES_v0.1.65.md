# Collection workflows — v0.1.65

**Data and settings → Collection tools** opens guided counts, build comparisons, purchase/import lots and the getting-started assistant.

## 2. Saved storage proposals

In **My storage → Sort by category and stud size**, use **Save a draft…**, then **Resume a draft…** after restarting. Criteria, category order, drawer counts, manual groupings, quantities and chosen destinations are saved. If stock or cabinet data changed, explicitly allow recalculation and review the updated preview before applying. Unavailable destinations may change. Missing item identities or cabinets block restoration. Loading a draft never applies it; Apply remains a separate, undoable operation.

## 3. Guided inventories

Use **Guided inventory…** to count a set, a cabinet, or resume a previous session. The cabinet menu also provides a direct entry. Enter observed quantities next to expected quantities. **Not counted** differs from zero; unknown drawer expectations appear as **?** and do not generate false shortages. Set counts use the complete local inventory, excluding spares.

Filter pending, missing or surplus rows. Counts autosave after a brief typing pause; Save count forces saving. Export count creates a CSV. Observations do not change owned stock or drawer quantities. Expected quantities are a snapshot taken when the session starts; start a new count to inspect a changed inventory.

## 4. Multiple-build comparison

Choose up to **16 set references** and copy counts in **Compare multiple builds…**. Each row is an indivisible bundle. The exact comparison maximizes the number of copies buildable together, then the number of different references, then insertion order. Parts cannot be reused across the proposed builds. Existing reservations are deducted.

Usable stock selection can include loose stock, inventories of selected owned sets to dismantle, or both, without transferring set inventories to loose stock. Colour matching, minifigure exclusion and known alternative-brick equivalents are available. Non-selected rows show their shortage against the stock left after the chosen combination. Complete local inventories are required. This searches the user’s selection, not every combination in the entire LEGO catalogue.

Create selected projects stores their requirements atomically as one undoable action, without reserving or moving parts. Respect colours before creating these projects. Stock changes invalidate the comparison.

## 5. Purchase and import lots

Each lot stores name, provenance, price in euros and a comment. Add a catalogue item, colour and quantity: parts go to loose stock, sets to owned-set stock with tracked components. The catalogue metadata is preserved. New collection imports automatically create named lots; resumed imports track additions without duplicating already imported rows. Earlier historical additions are not reconstructed.

Correct one contribution, or remove all of a lot’s tracked additions. Complete-set quantities adjust components proportionally. Attached or non-divisible inventories require cancellation and corrected reimport. If remaining stock would not cover counted drawers or project reservations, the entire correction/cancellation is rejected. Cancelled lots remain in history. Quantity corrections and cancellation are undoable. Prices are metadata, not automatic per-part valuations.

## 6. Project pick lists

Select a project in **My projects → Pick list…**. **To pick** lists cabinet, drawer, reference, colour and quantity. Parts may come from several drawers. Rows without counted locations must be located/count-managed first.

Pick from selected row records the quantity actually taken. It decreases the drawer count and reserves that quantity for the project, without reducing ownership. A unit cannot be counted in a drawer and picked simultaneously. **Already picked** retains the details even when all requirements are covered. CSV export includes locations and quantities.

Return all picks requires confirming their physical return and restores original drawer counts. Reservations remain until explicitly released. Return picks before deleting a project/source drawer, releasing the associated reservation or clearing loose stock. Picks and returns can be undone; the recorded operation must match the physical movement.

## 7. Getting started

Four steps explain catalogues, LDraw renders, stock and cabinets, with buttons to existing windows. The assistant appears for a new empty collection, after bundled-resource automatic import when applicable. It remains accessible through Collection tools. Resume later closes it; Finish records completion. No new automatic network download is introduced.

## Cabinet alignment

**My storage → Organize cabinet → Align cabinets…** aligns all cabinets horizontally or vertically with an adjustable gap in standard-drawer units. Current reading order is retained, starting at the first cabinet’s position. Drawer formats, contents and quantities are unchanged. Alignment is one undoable action and checks for concurrent edits.

Cabinets now always use a front view; the angle control is hidden. Part and label view settings are unaffected.

## Data and backups

All workflows persist locally. Full backups include drafts, counts, lots and picks. Existing selective exports keep their original scope; use full backups to transfer the new tracking records too. Photo-based reference recognition is not included.
