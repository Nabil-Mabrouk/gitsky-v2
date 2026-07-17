# Calendrier de maintenance de la flotte GitSky

Adapté du Chap 23 §6. Sur une flotte, la maintenance est **mutualisée** : un seul
jeu de crons (`crontab.fleet`) et un tableau unique, plutôt que N projets gérés
à la main. Les tâches automatiques tournent seules ; les tâches manuelles sont à
faire depuis le fleet dashboard.

## Tâches automatiques (cron — `crontab.fleet`)

| Fréquence | Tâche | Script |
|---|---|---|
| 60 s | Poll `/health` de la flotte → alerte `deployment_failed` | `fleet-health.sh` |
| Quotidien 02:00 | Sauvegarde 3-2-1 de toutes les bases projet | `backup-fleet.sh` |
| Quotidien 03:00 | Kill check (déclenché par le dashboard, Chap 20) | — |
| Horaire | Jauge disque consolidée | `fleet-disk.sh` |
| Hebdo (dim 05:00) | Purge des images Docker orphelines | `docker image prune` |
| Mensuel | Rotation des logs de maintenance (> 30 j) | `find … -delete` |

La sauvegarde de 02:00 précède **volontairement** le kill_check de 03:00 : un
projet sur le point d'être tué a ainsi une sauvegarde fraîche.

## Tâches manuelles

| Fréquence | Tâche | Outil |
|---|---|---|
| Hebdo | Revue des logs d'erreurs (5xx Traefik) | `check_errors.sh` (par projet) |
| Hebdo | Revue des `security_events` suspects | dashboard / module security |
| Hebdo | Vérifier que la dernière sauvegarde de flotte existe | colonne « dernière sauvegarde OK » |
| Mensuel | Test de restauration d'un projet au hasard | `test_restore.sh` |
| Mensuel | Analyse santé DB (lignes mortes, tailles) | `db_health.sql` par projet |
| Mensuel | Scan CVE des dépendances | `pip-audit`, `npm audit` |
| Semestriel | Rotation `SECRET_KEY` + mots de passe DB | automatisée par le dashboard (Chap 23) |
| Semestriel | Revue des clés SSH autorisées sur le VPS | manuel |
| Sur incident | Rotation immédiate de TOUS les secrets + analyse logs | runbook incident (Chap 23 §7) |

## Note : scripts par projet vs flotte

Les scripts par projet (`backup_db.sh`, `test_restore.sh`, `emergency_restore.sh`,
`check_*.sh` — livrés dans chaque projet généré) servent à une intervention
ciblée sur **un** projet ou à un déploiement autonome. Sur la flotte, la
sauvegarde quotidienne passe par `backup-fleet.sh` : **ne pas** programmer en
plus les `backup_db.sh` par projet (doublon de sauvegardes).
