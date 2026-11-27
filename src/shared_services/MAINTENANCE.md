# Calendrier de maintenance de la flotte GitSky

Le calendrier (tâches automatiques et manuelles) vit désormais dans le guide d'exploitation, source unique publiée sur 0-hitl.com (onglet Apprentissage, comptes admin) :

- [Maintenance de la flotte](../../docs/exploitation/05-maintenance-de-la-flotte.md) — cron, tâches manuelles, services partagés, sauvegardes.
- [Maintenance d'un projet](../../docs/exploitation/04-maintenance-d-un-projet.md) — déploiement, `copier update`, rotation des secrets, restauration.

## Note : scripts par projet vs flotte

Les scripts par projet (`backup_db.sh`, `test_restore.sh`, `emergency_restore.sh`, `check_*.sh` — livrés dans chaque projet généré) servent à une intervention ciblée sur **un** projet. Sur la flotte, la sauvegarde quotidienne passe par `backup-fleet.sh` : **ne pas** programmer en plus les `backup_db.sh` par projet (doublon). `test_restore.sh` attend le format de `backup_db.sh` (`.sql.gz`, `psql`) et ne peut pas valider les sauvegardes de `backup-fleet.sh` (`.dump.gz`, `pg_restore`) : le test mensuel de la flotte passe par `test-restore-fleet.sh`.
