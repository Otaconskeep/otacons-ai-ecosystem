# Keep Expansion — Backup & Restore

## Scope

Backup includes **user-owned** state only:

- owner preferences / identity markers
- memories
- relationships (+ provenance on disk)
- emotions (+ provenance)
- journal / diary
- living dossier
- jobs / events
- agents / pages / preferences

Excluded:

- secrets / `.key` files
- signing private keys
- plaintext protected product dossiers from RC trees
- Core install tree

## API

```python
from expansion.qualify.backup import create_backup, restore_backup

create_backup(Path('/tmp/keep-user.zip'))
restore_backup(Path('/tmp/keep-user.zip'), overwrite=True)
```

Archive contains `BACKUP.json` metadata (`kind=expansion_user_backup_v1`).

## Restore targets

- Same installation (overwrite user trees)
- Fresh compatible Expansion install (same schema family)

After restore, run `repair_expansion` and acceptance matrix.
