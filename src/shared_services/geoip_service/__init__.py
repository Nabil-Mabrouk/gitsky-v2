"""GeoIP Service — service partagé de résolution IP -> pays/ville (Chap 13/18).

Lookup local dans la base MaxMind GeoLite2-City (.mmdb), jamais d'accès
réseau sortant — seul geoipupdate (service séparé, shared_services/docker-
compose.yml) a besoin d'Internet pour rafraîchir la base.
"""
