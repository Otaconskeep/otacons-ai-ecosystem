import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if len(sys.argv) > 1 and sys.argv[1] == 'validate-chat':
    from installer.validate_chat import main
    main()
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-voice':
    from installer.validate_voice import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-stt':
    from installer.validate_stt import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-voice-loop':
    from installer.validate_voice_loop import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-resources':
    from installer.validate_resources import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-arbiter':
    from installer.validate_arbiter import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] in ('validate-image','validate-agent-image'):
    from installer.validate_image import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] in ('validate-video','validate-agent-video'):
    from installer.validate_video import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-integrations':
    from installer.validate_integrations import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] in ('validate-install','validate-update','validate-backup','validate-restore','validate-node-security','repair','beta-readiness'):
    from installer.validate_lifecycle import main
    raise SystemExit(main([sys.argv[1]]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-nodes':
    from installer.validate_nodes import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-distributed':
    from installer.validate_nodes import main
    raise SystemExit(main(sys.argv[2:]))
elif len(sys.argv) > 1 and sys.argv[1] == 'validate-memory':
    from installer.validate_memory import main
    main()
else:
    from installer.server import main
    main()
