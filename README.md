# crywatch (fork Pierre) 👶

Détecteur de pleurs de bébé auto-hébergé, **intégré nativement à Home
Assistant** : pas de MQTT, pas de webpage séparée, pas de docker-compose à
maintenir à la main pour la détection. Fork de
[drjc1001/crywatch](https://github.com/drjc1001/crywatch) — voir
[FORK_NOTES.md](FORK_NOTES.md) pour l'historique complet du diff, et
[CLAUDE.md](CLAUDE.md) pour le contexte côté assistant.

## Ce que ça fait

- La caméra (une Tapo C210, dans mon cas) est **déjà intégrée nativement
  dans Home Assistant** (Generic Camera / ONVIF / etc.) — ce fork ne
  s'occupe pas du streaming vidéo, HA le fait déjà très bien.
- Un **add-on Home Assistant** ([`ha-addon/crywatch_cry_detector/`](ha-addon/crywatch_cry_detector))
  tire l'audio RTSP de cette caméra et fait tourner **YAMNet** (Google,
  CPU-only, pas de GPU requis) pour distinguer un vrai pleur d'un bruit fort
  (télé, aspirateur, toi qui parles).
- Une **intégration Home Assistant** ([`custom_components/crywatch/`](custom_components/crywatch))
  transforme ça en entités natives : un `binary_sensor` (« Pleurs
  détectés ») + un `sensor` diagnostic (confiance %), par caméra — utilisable
  directement comme trigger d'automation.

## Architecture

```
caméra (déjà native dans HA) ──RTSP──▶ add-on crywatch_cry_detector ──YAMNet──▶ état interne
                                                                            │
                                                    intégration crywatch (poll /api/state, 5s)
                                                                            │
                                                    binary_sensor + sensor natifs, par caméra
```

L'intégration choisit les caméras à surveiller parmi tes entités `camera.*`
existantes — **pas d'URL RTSP à saisir à la main**, elle la résout
elle-même via l'API caméra de Home Assistant
(`camera.async_get_stream_source`) et la transmet à l'add-on.

## Installation

### 1. Ajouter ce dépôt à Home Assistant (deux ajouts séparés, même repo)

- **Comme dépôt d'add-ons** : *Paramètres → Add-ons → Boutique des add-ons →
  ⋮ (en haut à droite) → Dépôts* → colle l'URL de ce repo GitHub.
- **Comme dépôt HACS personnalisé** : *HACS → ⋮ → Dépôts personnalisés* →
  colle la même URL, catégorie *Intégration*.

### 2. Installer et démarrer l'add-on

Boutique des add-ons → **Crywatch Cry Detector** → Installer. Ajuste si
besoin les réglages de détection dans l'onglet **Configuration** (voir la
table plus bas, ou sa [DOCS.md](ha-addon/crywatch_cry_detector/DOCS.md)),
puis démarre-le. Il tourne **sans caméra** pour l'instant, c'est normal —
vérifie son onglet **Journal** : tu dois voir `[yamnet] ready. ...`.

### 3. Installer l'intégration et choisir les caméras

*HACS → Intégrations →* recherche **Crywatch** → Télécharger → redémarre
Home Assistant. Puis *Paramètres → Appareils et services → Ajouter une
intégration →* **Crywatch** :

1. Hôte/port de l'add-on (par défaut `crywatch_cry_detector` / `8091` — si
   la connexion échoue, vérifie le nom réel du conteneur de l'add-on).
2. Sélectionne les caméras `camera.*` à surveiller.

Deux entités apparaissent par caméra choisie, groupées en un appareil HA :
`binary_sensor.<caméra>_pleurs_detectes` et
`sensor.<caméra>_confiance_pleurs`. Pour ajouter/retirer une caméra plus
tard : *Paramètres → Appareils et services → Crywatch → ⋮ → Configurer*.

### 4. Brancher ton automation

Utilise `binary_sensor.<caméra>_pleurs_detectes` passant à `on` comme
trigger (ex. réveil d'un tableau Fully Kiosk — voir
[FORK_NOTES.md](FORK_NOTES.md), section *Lien avec l'automation Fully
Kiosk*).

## Réglages de détection

Dans l'onglet **Configuration** de l'add-on :

| Réglage | Défaut | Effet |
|---|---|---|
| `cry_prob` | `0.4` | Probabilité de pleur (0-1) à partir de laquelle un échantillon compte comme "pleur". Monte si trop de faux positifs, baisse s'il en rate. |
| `sustain_samples` | `2` | Échantillons consécutifs au-dessus du seuil avant de déclencher. |
| `cooldown` | `60` | Secondes minimum entre deux déclenchements. |
| `sample_sec` | `2.0` | Durée (s) de chaque burst audio analysé. |
| `rms_gate_db` | `-60` | En dessous de ce niveau (silence), le modèle n'est même pas appelé. |
| `state_timeout` | `60` | Secondes sans nouveau pleur avant que le `binary_sensor` repasse à OFF. |
| `log_scores` | `false` | `true` = log le score de chaque échantillon dans le Journal (calibration). |

Watch avec `log_scores: true` : dans mes tests (upstream), un vrai pleur
score **0.5–1.0** ; la parole plafonne vers **0.27** ; toux / claquement /
chien / rire / alarme — et un **aspirateur** (le plus fort du lot) — tous
autour de **~0.00**. C'est tout l'intérêt : fort ≠ pleure.

## Statut — rien de tout ça n'a tourné en conditions réelles

Écrit et relu sans accès à un Home Assistant/Supervisor pour tester. Avant
de faire confiance à l'automation dessus :

1. Vérifie le Journal de l'add-on après son premier démarrage.
2. Ajoute l'intégration — si le config_flow n'arrive pas à se connecter,
   c'est probablement le hostname deviné pour l'add-on (voir
   [FORK_NOTES.md](FORK_NOTES.md)).
3. Vérifie que les deux entités par caméra apparaissent et bougent quand tu
   fais du bruit devant la caméra.
4. Si une caméra n'a pas de source RTSP résolvable
   (`camera.async_get_stream_source` renvoie `None`), l'intégration le logue
   — dis-moi alors comment cette caméra est intégrée dans HA (Generic
   Camera / ONVIF / Tapo Control / autre).

Détail complet des hypothèses à vérifier et de l'historique du fork dans
[FORK_NOTES.md](FORK_NOTES.md).

## Ce qui reste du repo upstream (pas utilisé dans cette installation)

`go2rtc/`, `viewer/`, `cry-detector/` (version Docker/MQTT), `config-ui/` et
`docker-compose.yml` viennent du projet
[upstream](https://github.com/drjc1001/crywatch) et restent dans ce repo
pour compatibilité (`git fetch upstream && git merge upstream/main` reste
possible), mais **ne font pas partie de cette installation** : la vidéo est
déjà native dans Home Assistant, et la détection de pleurs passe par
l'add-on + l'intégration ci-dessus plutôt que par MQTT/ntfy.

## Sécurité

Voir [SECURITY.md](SECURITY.md). L'add-on ne publie aucun port sur le LAN :
son API d'état n'est joignable que depuis Home Assistant Core, via le
réseau interne de Supervisor.

## License

[Apache License 2.0](LICENSE) (upstream).
