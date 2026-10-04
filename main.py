from atelier.storage import prepare_portable_storage

if __name__ == '__main__':
    prepare_portable_storage()
    from atelier.app import main
    raise SystemExit(main())
