"""Point d'entrée du lanceur Windows portable (sans installation Python)."""
import sys
from pathlib import Path

if Path(sys.executable).stem.lower() in ('legoatelier','bricklabo'):
    try:
        from atelier.storage import prepare_portable_storage
        prepare_portable_storage()
        from atelier.diagnostics import setup_logging
        setup_logging()
        from atelier.app import main
        status = main()
    except BaseException:
        import os
        import traceback
        import ctypes
        try:
            from atelier.i18n import tr
        except Exception:
            tr=lambda text:text
        folder=Path(sys.executable).resolve().parent/'Donnees'/'logs'
        text=traceback.format_exc()
        try:
            from atelier.diagnostics import setup_logging
            logger,log_folder=setup_logging()
            logger.error(tr('Échec du démarrage'),exc_info=True)
        except BaseException:
            pass
        try:
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'BrickLabo_demarrage_erreur.txt').write_text(text,encoding='utf-8')
        except OSError:pass
        ctypes.windll.user32.MessageBoxW(None,tr('Démarrage impossible.\nLe détail est dans :\n')+str(folder/'BrickLabo_demarrage_erreur.txt')+'\n\n'+text[-1200:],'BrickLabo by SDU7 — v0.1.36',16)
        status=1
    # Un SystemExit pendant l'import automatique de site empêche le démarrage du REPL.
    # os._exit évite aussi que Python traite la fin normale comme une erreur de site.
    import os
    os._exit(status)
