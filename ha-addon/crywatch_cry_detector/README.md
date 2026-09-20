# Crywatch Cry Detector

Détecteur de pleurs bébé basé sur YAMNet (Google), tournant en add-on Home
Assistant — CPU only, pas de GPU requis.

Il lit l'audio RTSP **directement depuis chaque caméra** (pas besoin de
go2rtc) et classifie chaque burst de ~2s. Pas de MQTT, pas de ntfy : l'état
(pleur en cours / niveau de confiance) est servi en interne pour
l'intégration **[Crywatch](../../custom_components/crywatch)**, qui crée les
capteurs Home Assistant natifs.

## Installation

1. Ajoute ce dépôt comme dépôt d'add-ons : **Paramètres → Add-ons → Boutique
   des add-ons → ⋮ → Dépôts** → colle l'URL de ce repo GitHub.
2. Installe **Crywatch Cry Detector**, configure au moins une caméra dans
   l'onglet **Configuration** (nom + URL RTSP complète, ex.
   `rtsp://user:pass@192.168.1.50:554/stream2`), démarre l'add-on.
3. Installe l'intégration **Crywatch** (voir son propre README) pour obtenir
   les capteurs dans Home Assistant.

## Réglages

Voir la description de chaque champ dans l'onglet Configuration de l'add-on ;
ce sont les mêmes réglages que documentés dans le `README.md` principal du
dépôt (`CRY_PROB`, `sustain_samples`, `cooldown`, etc.), juste renommés en
snake_case pour le schéma d'add-on.

## Limites connues

- Testé par relecture de code uniquement — jamais exécuté en add-on réel
  (écrit dans un environnement sans Home Assistant/Docker/Supervisor
  accessible). Vérifie en premier les logs de l'add-on après le premier
  démarrage.
- Une caméra ajoutée/retirée dans la Configuration nécessite un redémarrage
  de l'add-on **et** un rechargement de l'intégration Crywatch côté HA pour
  que les entités correspondantes apparaissent/disparaissent.
