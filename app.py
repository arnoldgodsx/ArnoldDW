"""Arnold DW launcher (PyInstaller entry point)."""
import sys

if __name__ == "__main__":
    if sys.argv[1:] == ["--version"]:
        # Answered before any UI/engine import so packaging smoke tests stay fast.
        # In the windowed exe sys.stdout is None and print() is a no-op; the exit code
        # is what CI checks.
        from arnold_dw import __version__

        print(__version__)
        sys.exit(0)

    from arnold_dw.main import main

    main()
