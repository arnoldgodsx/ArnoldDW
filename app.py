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

    if sys.argv[1:] == ["--install-components"]:
        # Headless first-launch setup (installer smoke test, scripted deployments):
        # downloads ffmpeg/Deno like the setup screen does. Exit code 0 = all installed.
        from arnold_dw.core.runtime.components import install_missing
        from arnold_dw.log import setup_logging

        setup_logging()
        sys.exit(install_missing())

    from arnold_dw.main import main

    main()
