import sys
if len(sys.argv)>1 and sys.argv[1]=='validate-chat':
 from installer.validate_chat import main
 main()
else:
 from installer.server import main
 main()
