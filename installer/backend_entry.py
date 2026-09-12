import sys

if len(sys.argv) > 1 and sys.argv[1] == 'validate-chat':
    from installer.validate_chat import main
    main()
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-voice':
    from installer.validate_voice import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-memory':
    from installer.validate_memory import main
    main()
else:
    from installer.server import main
    main()
