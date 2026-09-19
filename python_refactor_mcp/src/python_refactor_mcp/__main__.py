def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in {"setup", "doctor", "uninstall"}:
        from python_refactor_mcp.install import main as install_main

        raise SystemExit(install_main(sys.argv[1:]))

    from python_refactor_mcp.server import run

    run()


if __name__ == "__main__":
    main()
