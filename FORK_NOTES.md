# Fork notes — crywatch pour Pierre

Fork de [drjc1001/crywatch](https://github.com/drjc1001/crywatch) (upstream conservé
dans l'historique git — `git log` montre les commits d'origine).

## Ce qui a changé

- **`cry-detector/yamnet_detect.py`** : ajout d'un client MQTT (paho-mqtt) publiant
  vers ton Mosquitto existant, avec **HA MQTT discovery** — le `binary_sensor`
  apparaît automatiquement dans Home Assistant sans config manuelle.
  - `ntfy` devient optionnel (`NTFY_URL` vide = désactivé). Avant : actif par défaut.
  - Nouveau : état ON/OFF avec **auto-retour à OFF** après `CRY_STATE_TIMEOUT` (60s
    par défaut) sans nouveau pleur — pensé pour un trigger HA `to: "on"`, pas juste
    une notification ponctuelle.
- **`.env.example`**, **`docker-compose.yml`**, **`run.sh`** : variables `MQTT_*` +
  `CRY_STATE_TIMEOUT` ajoutées ; service `ntfy` upstream commenté par défaut (tu n'en
  as pas besoin en local, MQTT suffit — réactivable si tu veux un jour un push mobile
  hors LAN).
- **`examples/go2rtc.example.yaml`** : adapté à une seule caméra (`simon` /
  `simon_hd`) au lieu de `cam1`/`cam2`, avec rappel de vérifier le micro RTSP côté
  app Tapo avant de débugger quoi que ce soit côté go2rtc.
- **`config-ui/`** (nouveau service Docker, port `8090`) : petite UI web pour
  ajouter/éditer des caméras (écrit `go2rtc.yaml` + `CAMS` dans `.env` en même
  temps, pour ne plus avoir à synchroniser les deux à la main) et éditer les
  réglages MQTT (`.env`). Protégée par login/mot de passe HTTP Basic obligatoire
  (`CONFIG_UI_USER`/`CONFIG_UI_PASSWORD`, pas de défaut — le service refuse de
  démarrer sans, `docker compose up` échoue aussi sans ces deux variables).
  **N'applique rien toute seule** : après un enregistrement, il faut relancer
  `docker compose up -d` (reprend les nouvelles valeurs `.env`, dont MQTT) puis
  `docker compose restart go2rtc` (relit `go2rtc.yaml` pour les caméras) —
  l'UI affiche la commande exacte après chaque sauvegarde.
  - Limite connue : l'UI réécrit entièrement la section `streams:` de
    `go2rtc.yaml` avec `ruamel.yaml` (les commentaires globaux du fichier —
    `api:`/`rtsp:`/`webrtc:` — sont préservés, mais les commentaires
    spécifiques à chaque flux caméra, comme dans l'exemple fourni, seront
    perdus dès le premier enregistrement).
  - Autre limite : elle ne touche pas les valeurs par défaut codées dans
    `viewer/multi.html` (`cams=cam1,cam2` si aucun paramètre d'URL) — sans
    `?cams=...&labels=...` dans l'URL, le viewer retombe sur ces valeurs
    d'origine. L'UI affiche l'URL `?cams=...&labels=...` à jour après chaque
    sauvegarde de caméra, mais ne modifie pas la page du viewer elle-même.

## Ce que je n'ai PAS fait

- **Pas de vrai fork GitHub** : je n'ai pas d'accès à ton compte GitHub, donc je ne
  peux pas cliquer "Fork" ni pousser quoi que ce soit à ta place. Ce dossier est un
  clone local modifié, avec l'historique git upstream intact. Pour en faire un vrai
  fork chez toi :
  ```bash
  # sur ton serveur / poste, dans ce dossier
  git remote rename origin upstream
  git remote add origin git@github.com:<toi>/crywatch.git   # ton propre repo, vide
  git add -A && git commit -m "MQTT + HA discovery, single-camera setup"
  git push -u origin main
  ```
  Ça te garde la possibilité de faire `git fetch upstream && git merge upstream/main`
  plus tard si le projet original évolue.
- **Pas testé** : je n'ai pas de broker MQTT ni de flux RTSP accessibles ici — la
  logique est relue et le fichier compile (`py_compile` OK), mais le comportement
  runtime (connexion MQTT, retained messages, timing de l'auto-OFF) est à valider chez
  toi avec `CRY_LOG=1` avant de brancher l'automation HA dessus.
  Idem pour `config-ui/` : relu attentivement (logique de lecture/écriture
  `go2rtc.yaml`/`.env`, auth Basic, validation) mais **jamais exécuté** — je
  n'ai ni Python ni Docker dans cet environnement pour le lancer réellement.
  À tester chez toi en premier avec des fichiers de test avant de lui faire
  confiance sur ton vrai `go2rtc.yaml` : `docker compose up -d --build
  config-ui` puis vérifier que la page s'ouvre sur `:8090`, que les caméras
  et le MQTT s'affichent correctement, et qu'un enregistrement produit bien
  le résultat attendu dans les fichiers avant de relancer les autres services.

## Pivot (2026-09-20) : add-on + intégration Home Assistant, à la place de MQTT

Sur demande de Pierre : plutôt qu'un `binary_sensor` créé via MQTT discovery,
la détection de pleurs devient une **vraie intégration Home Assistant**
(entités natives, réglages natifs), avec le calcul (ffmpeg + YAMNet) qui
tourne dans un **add-on Supervisor** — pas un docker-compose séparé à
maintenir à la main. La vidéo reste hors périmètre : Pierre a déjà ses
caméras en natif dans HA, donc `go2rtc`/`viewer`/`config-ui` de ce repo ne
sont plus son chemin de déploiement pour la partie caméra (ils restent dans
le repo pour la compatibilité upstream / d'autres utilisateurs de crywatch,
mais **Pierre n'en a plus besoin**).

- **`ha-addon/crywatch_cry_detector/`** : reprend `cry-detector/yamnet_detect.py`
  mais lit l'audio **RTSP directement depuis chaque caméra** (plus besoin de
  go2rtc comme intermédiaire), et sert un état JSON interne
  (`GET /api/state`) au lieu de MQTT/ntfy. Réglages natifs dans l'onglet
  **Configuration** de l'add-on (liste de caméras `name`/`rtsp_url` +
  `cry_prob`, `sustain_samples`, etc. — mêmes réglages que documentés dans le
  `README.md` principal, en snake_case). Aucun port publié : l'API n'est
  joignable que depuis Home Assistant Core, via le réseau Docker interne de
  Supervisor.
- **`custom_components/crywatch/`** : intégration HA (config_flow +
  `DataUpdateCoordinator` qui poll `/api/state` toutes les 5s) créant, par
  caméra, un `binary_sensor` (« Pleurs détectés », `device_class: sound`) et
  un `sensor` diagnostic (confiance %), groupés en un appareil HA par
  caméra — installable via un **dépôt HACS personnalisé** pointant sur ce
  repo (`hacs.json` à la racine).
- **`repository.yaml`** (racine du repo) : permet d'ajouter ce repo comme
  **dépôt d'add-ons** dans Supervisor (Paramètres → Add-ons → Boutique →
  ⋮ → Dépôts), en plus de l'ajout HACS pour l'intégration — les deux
  mécanismes lisent des sous-dossiers différents du même repo, pas de
  conflit.

**Hypothèse non vérifiée, à confirmer en premier** : l'intégration devine
`crywatch_cry_detector` comme nom d'hôte interne pour joindre l'add-on
(`const.py` → `DEFAULT_HOST`). C'est la convention Supervisor habituelle
(hostname = slug de l'add-on sur le réseau Docker `hassio`), mais je n'ai
aucun Home Assistant/Supervisor accessible ici pour le vérifier. Si la
connexion échoue dans le config_flow (« impossible de joindre l'add-on »),
regarde le nom réel du conteneur de l'add-on (logs Supervisor, ou
`ha addons info crywatch_cry_detector` en SSH) et entre-le à la main dans le
formulaire — c'est un champ libre, pas figé.

**Rien de tout ça n'a tourné** : ni l'add-on (pas de Supervisor accessible
ici), ni l'intégration (pas de Home Assistant pour charger le
`custom_component` et vérifier que `config_flow`/`DataUpdateCoordinator`
s'enregistrent sans erreur). Relu attentivement contre les patterns HA
habituels (comparable à l'intégration Frigate : add-on séparé pour le calcul
lourd + intégration légère qui poll son API — pas du bricolage inédit), mais
à valider pas à pas :
1. Add-on d'abord, seul — vérifier dans son onglet **Journal** que YAMNet
   charge et qu'il n'y a pas d'erreur ffmpeg/RTSP.
2. Puis l'intégration — si le config_flow échoue à se connecter, c'est
   probablement le hostname (voir ci-dessus).
3. Puis vérifier que les deux entités par caméra apparaissent et bougent
   quand tu fais du bruit devant la caméra.

## Déploiement chez toi

1. Vérifier le micro RTSP du C210 (`ffprobe` sur l'URL RTSP — piste audio présente ?).
2. `cp examples/go2rtc.example.yaml go2rtc.yaml` → renseigner IP/identifiants Tapo.
3. `cp .env.example .env` → renseigner `MQTT_HOST` (IP de ton Mosquitto), `CAMS=simon=Chambre Simon`.
4. `docker compose up -d --build`.
5. `docker logs -f baby-cry-detector` avec `CRY_LOG=1` : observer les scores quelques
   minutes (bruits normaux de la pièce, TV, toi qui parles) pour calibrer `CRY_PROB`
   avant de faire confiance à l'auto-classification.
6. Dans HA : le binary_sensor `binary_sensor.pleurs_detectes_chambre_simon` (nom exact
   selon le slug — vérifier dans **Paramètres → Appareils et services → MQTT**) doit
   apparaître automatiquement une fois le premier événement discovery publié.

## Lien avec l'automation Fully Kiosk (voir échange précédent)

Remplacer le trigger de l'automation HA :
```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.pleurs_detectes_chambre_simon   # au lieu de camera_simon_noise
    to: "on"
```
Le reste (screenOn, playSound, loadURL vers le viewer `multi.html?cams=simon`, retour
au dashboard après 1 min) reste valable tel quel — `CRY_STATE_TIMEOUT=60` côté
détecteur est volontairement aligné sur cette fenêtre d'affichage, mais les deux
minuteurs sont indépendants : ajuste-les ensemble si tu changes l'un des deux.
