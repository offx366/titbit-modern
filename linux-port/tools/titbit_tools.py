"""One executable for the Linux package: game data import and Titbit Studio.

  titbit-tools setup [options]    import wizard (no options: window)
  titbit-tools studio [options]   scene editor in the browser

Built by tools/build_tools.sh with PyInstaller, so players need no Python.
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv and argv[0] in ('setup', 'studio', 'launcher') else 'setup'
    if command == 'launcher':
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
        import titbit_launcher
        return titbit_launcher.main(argv)
    if command == 'studio':
        import start_studio
        sys.argv = ['titbit-tools studio', *argv]
        return start_studio.main()
    import titbit_setup
    return titbit_setup.main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
