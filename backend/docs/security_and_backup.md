# Security And Backup

## Secrets

- Runtime secrets are loaded from `.env` via `python-dotenv`.
- `.env` and `.env.*` are ignored by Git.
- Recommended practice: keep only a sanitized `.env.example` in the repository.

## Roles

- `Admin` and `Editor` can approve, reject and edit approval items.
- `Viewer` is denied write actions at the service layer.
- Role lookup is based on `public.users.tg_id`, `role`, `is_active`, `is_deleted`.

## Soft Delete And Anonymization

- Business entities use `is_deleted` and, where relevant, `is_active`.
- For contacts, anonymization can be performed with:

```powershell
python .\scripts\anonymize_contact.py --contact-id 123
```

- To anonymize and additionally mark the contact as deleted:

```powershell
python .\scripts\anonymize_contact.py --contact-id 123 --soft-delete
```

## PostgreSQL Backup

Example manual backup:

```powershell
.\scripts\backup_postgres.ps1
```

With custom folder and retention:

```powershell
.\scripts\backup_postgres.ps1 -BackupDir ".\secure_backups" -RetentionDays 30
```

Recommended for daily automation:

- Windows Task Scheduler for local/stand environments
- cron/systemd timer for Linux deployments
- restricted access to the backup directory and dump files
