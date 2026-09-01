# Upgrades, migrations, and rollback

Database changes use the ordered Alembic revisions under `migrations/`; rehearse both upgrade and downgrade on a disposable database before deployment. Persisted `.sdpstudio` documents use explicit schema versions and migration helpers that create a backup before rewriting a document.

Back up the database, project repository, and `.sdpstudio` metadata before upgrading. Rollback restores the application and database revision together; generated source and user-owned custom regions must be preserved separately because a database downgrade cannot reconstruct discarded repository history.
