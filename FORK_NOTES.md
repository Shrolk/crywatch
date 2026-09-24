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

**Mise à jour (même jour) : plus de champ RTSP à saisir.** L'intégration
sélectionne des **entités caméra HA existantes** (`EntitySelector(domain=
"camera")`, dans le config_flow puis dans son Options flow pour en changer
plus tard) et résout elle-même leur source RTSP via
`homeassistant.components.camera.async_get_stream_source(hass, entity_id)` —
l'API HA standard pour ça, censée marcher quel que soit le type d'intégration
caméra sous-jacente (Generic/ONVIF/Tapo). Elle pousse ensuite la liste
(`{key: entity_id, name, rtsp_url}`) à l'add-on via `POST /api/cameras` — à
la création de l'intégration, et à chaque `Recharger`/changement d'options.
L'add-on démarre maintenant **sans caméra du tout** et applique la liste
reçue à chaud (démarre/arrête les threads concernés, sans redémarrer). Donc
`ha-addon/.../config.yaml` n'a plus d'option `cameras`.

Nouvelle inconnue, en plus du hostname (voir plus bas) : je n'ai jamais vu
`async_get_stream_source` tourner en vrai contre une caméra Tapo (ou
n'importe quelle caméra) — si elle renvoie `None` pour ton entité, l'add-on
recevra une liste vide et le log de l'intégration dira "no RTSP stream
source (unsupported camera platform?)". Si ça arrive, dis-moi comment ta
caméra Simon est intégrée dans HA (Generic Camera / ONVIF / Tapo Control /
autre) — ça se contourne (certaines intégrations exposent le flux
différemment) mais je ne peux pas deviner laquelle sans le savoir.

**Résolu (2026-09-20) : le hostname deviné était faux, en deux temps.**
`crywatch_cry_detector` seul ne fonctionne pas — Supervisor préfixe le slug
d'un add-on en dépôt (non-officiel) avec un hash de l'URL du dépôt. Trouvé
via `ha apps list` en SSH (le CLI Supervisor a renommé `addons` en `apps`
sur la version de Pierre — `ha addons info ...` répond "does not exist",
`ha apps list` donne le `slug:`) : `aff0293d_crywatch_cry_detector`. Mais
même ce slug complet ne se connectait toujours pas — le **hostname DNS
réel** n'est pas identique au slug : Supervisor remplace les underscores
par des tirets pour le hostname. Confirmé via `ha apps info
aff0293d_crywatch_cry_detector` → `hostname: aff0293d-crywatch-cry-detector`
(tirets). C'est cette valeur (avec tirets) qui est maintenant le
`DEFAULT_HOST` dans `const.py`. Pour un autre fork/URL de dépôt, le hash
différera — méthode pour le retrouver : `ha apps list` (slug) puis
`ha apps info <slug>` (`hostname:`, avec tirets).

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

## Bug de démarrage résolu chez Pierre (2026-09-20) : `ModuleNotFoundError: pkg_resources`

Premier vrai test de l'add-on chez Pierre : crash immédiat au chargement de
`tensorflow_hub` (`from pkg_resources import parse_version`). Trois tentatives
de fix ont échoué **à l'identique** malgré des changements de contenu du
Dockerfile (ajout de `setuptools` à `requirements.txt`, puis un `RUN pip
install --upgrade pip setuptools wheel` dédié) et même après désinstallation
complète de l'add-on + suppression/réajout du dépôt + réinstallation à
froid — ce qui écarte un problème de cache Docker/Supervisor.

Cause probable : `python:3.12-slim` n'embarque plus `setuptools` par défaut
dans son venv/ensurepip (contrairement à 3.11 et avant), et `tensorflow_hub`
importe encore `pkg_resources` (fourni par `setuptools`) au chargement.
Pourquoi l'installer explicitement n'a rien changé reste **non expliqué** —
possible spécificité de la façon dont Supervisor construit l'image pour un
add-on en dépôt (à creuser si ça revient). Fix appliqué : basculer sur
`python:3.11-slim`, qui embarque encore `setuptools`, exactement comme
`cry-detector/Dockerfile` (upstream) qui n'a jamais eu ce problème. Version
`1.0.3`. **Confirmé résolu chez Pierre** : `[yamnet] ready.` et l'API sert
bien `:8091` en attente du premier `POST /api/cameras`. Le rebuild se
faisait donc correctement à chaque tentative précédente (le cache n'était
pas en cause) — pourquoi l'ajout explicite de `setuptools` sur
`python:3.12-slim` n'a pas suffi reste non expliqué, mais sans intérêt
pratique maintenant que `python:3.11-slim` fonctionne. À garder en tête si
`cry-detector/` (legacy, upstream) est retouché un jour : rester sur
`3.11-slim`, pas `3.12`.

## Bug résolu chez Pierre : la caméra ne s'affichait pas (2026-09-24)

Diagnostiqué en direct avec le connecteur MCP plutôt qu'en devinant :
`fully_kiosk.load_url` appelé seul (via `ha_call_service`, sans le reste
de la séquence) affichait bien la caméra sur la tablette. Mais dans
`async_alert()`, il était appelé **avant** `button.press` sur
`-toForeground` — et « mettre au premier plan » réinitialise/recharge
l'appli Fully Kiosk, écrasant la page tout juste chargée. D'où : réveil
au premier plan OK, mais retour à la page HA par défaut au lieu de la
caméra. Fix : réordonné pour que `load_url` soit la **dernière** action
(foreground puis volume puis load_url) — pas encore re-testé avec ce
nouvel ordre sur l'appareil réel, à confirmer après mise à jour vers
1.3.2.

## URL de l'alerte générée dynamiquement (2026-09-24)

Sur demande de Pierre : plus besoin de coller une URL complète. Le champ
« URL » devient un **chemin de tableau de bord** (ex. `dashboard-test/
simon`), et `kiosk.py` construit l'URL complète tout seul via l'API HA
`homeassistant.helpers.network.get_url()` (préférant l'URL interne,
n'utilisant jamais le cloud Nabu Casa) — donc ça continue de marcher si
l'IP/le port de HA changent un jour. Une valeur commençant par `http://`
ou `https://` est utilisée telle quelle (échappatoire pour pointer
ailleurs qu'un chemin de ce HA).

**Fait en direct via le connecteur MCP** (voir plus haut) : création d'une
nouvelle vue `simon` (type `panel`, carte `picture-entity` sur
`camera.simon` en direct, plein écran, sans chrome) dans le dashboard
**`dashboard-test`** de Pierre — celui déjà chargé sur sa tablette
Ozhora-S21 (confirmé : ses cartes de navigation appellent
`browser_mod.refresh` sur le `device_id` de cette même tablette, et
utilisent `input_boolean.kiosk_mode`). URL résultante :
`dashboard-test/simon`, à renseigner tel quel dans le champ « chemin »
côté intégration. Écriture confirmée (`post_write_verified: true`), mais
jamais vue rendue réellement sur l'appareil — vérifie que la vue
s'affiche correctement avant de compter dessus lors d'une vraie alerte.

Attention notée mais pas vérifiable à distance : le navigateur Fully
Kiosk de la tablette doit déjà être connecté/authentifié à HA pour que
`load_url` affiche la caméra directement plutôt qu'un écran de connexion.

## Alerte Fully Kiosk intégrée (2026-09-24)

Sur demande de Pierre : au lieu d'une automation HA séparée (qu'il n'avait
en fait jamais créée — la mention dans une conversation précédente était
restée au stade d'idée), l'intégration Crywatch peut elle-même réveiller un
appareil Fully Kiosk PLUS, y afficher une URL (dashboard caméra) et monter
le son, quand un pleur est détecté — et revenir en arrière quand le
`binary_sensor` repasse à OFF (`CRY_STATE_TIMEOUT` côté add-on).

**Vérifié en direct contre le HA de Pierre** (via le connecteur MCP
Home Assistant disponible dans cette session — utilisé pour la première
fois ici ; aurait dû l'être plus tôt pour le débogage du hostname de
l'add-on). Points confirmés, pas devinés :
- `ha_list_services(domain="fully_kiosk")` : seulement 3 services —
  `load_url`, `start_application`, `set_config`. Rien pour allumer l'écran
  ou monter le son directement.
- Mais l'intégration crée aussi des entités standards par appareil :
  `button` (dont *Mettre au premier/arrière-plan*, *Charger l'URL de
  démarrage*), `media_player` (volume), `number` (luminosité), etc. — ce
  sont ces entités, pas des services `fully_kiosk.*`, qui permettent le
  reste.
- Les noms affichés sont traduits en français (« Mettre au premier
  plan ») donc **jamais** utilisés pour identifier l'entité dans le code —
  le `unique_id` est stable et en anglais quel que soit la langue de
  l'installation : `<id>-toForeground`, `<id>-toBackground`,
  `<id>-loadStartUrl`, `<id>-mediaplayer`. `custom_components/crywatch/
  kiosk.py` les retrouve via le registre d'entités par leur `device_id`
  (choisi dans l'intégration via un `DeviceSelector`) + ce suffixe, jamais
  par nom.
- Testé uniquement en lecture (services listés, entités inspectées) —
  **les appels de service (`button.press`, `media_player.volume_set`,
  `fully_kiosk.load_url`) n'ont pas été déclenchés réellement**, donc pas
  de garantie que `toForeground` réveille vraiment l'écran (vs juste
  ramener l'app au premier plan sans sortir de veille) — à valider en
  vrai en déclenchant un pleur devant la caméra.

## Écran éteint ne se réveillait pas (2026-09-24, suite tests réels)

Confirmé par Pierre en conditions réelles : le bouton de test fonctionnait
tant que l'écran de la tablette restait allumé, mais **rien ne se passait
écran éteint** — exactement le trou anticipé ci-dessus. `-toForeground`
ramène l'app Fully Kiosk au premier plan mais ne sort pas l'écran de veille.

Fix : l'intégration officielle `fully_kiosk` expose aussi un `switch` pour
l'écran (`unique_id` suffixe `-screenOn`, ex. `switch.ozhora_s21_ecran`,
nom affiché « Écran ») — confirmé via le connecteur MCP HA
(`ha_get_entity` sur l'entité réelle de Pierre, `platform: fully_kiosk`,
même `device_id` que les autres entités kiosk). `kiosk.py` le résout comme
les autres (même pattern `_find_entity` par suffixe) et l'allume
(`switch.turn_on`) **avant** `-toForeground`, puisque rien de tout le reste
n'a d'effet visible tant que l'écran physique est éteint.

Pas de `switch.turn_off` symétrique dans `async_revert()` — on laisse le
minuteur de veille natif de Fully Kiosk ré-éteindre l'écran plutôt que de
forcer l'extinction (qui couperait aussi un usage normal de la tablette en
cours). Toujours pas re-testé en conditions réelles après ce fix
(nécessite un vrai cycle écran éteint → pleur/bouton test → écran qui
s'allume) — c'est l'action immédiate suivante.

**Bouton de test** (`button.py`, même jour) : si un appareil Fully Kiosk est
configuré, un bouton `button.crywatch_tester_l_alerte_fully_kiosk` apparaît
(appareil HA « Crywatch ») — le presser rejoue exactement la même séquence
qu'un vrai pleur détecté (`KioskAlertManager.async_alert()`), puis revient
en arrière automatiquement 10s après (`async_revert()`), sans attendre ni
simuler un vrai pleur. Utile pour valider que `-toForeground` réveille
vraiment l'écran avant de faire confiance au déclenchement automatique.

**Nouveaux réglages** (dans la même étape que le choix des caméras,
config initiale et Options) : appareil Fully Kiosk (optionnel — vide =
fonctionnalité désactivée), URL à charger (dashboard HA affichant la
caméra — **doit déjà être accessible sans re-login dans le navigateur
Fully Kiosk**, sinon `load_url` affichera un écran de connexion au lieu
de la caméra), volume d'alerte (0-100 %).

## Dépendance internet de l'add-on (2026-09-21)

Pierre a demandé si le projet tourne 100% en local. Réponse honnête : ça
devait être le cas (c'est tout le principe du projet — voir README, section
"Why" de l'upstream), mais l'add-on tel qu'écrit avait un vrai trou :
`run.py` charge YAMNet via `hub.load("https://tfhub.dev/google/yamnet/1")`
**au démarrage du conteneur**, sans qu'il soit mis en cache de façon
persistante — donc un redémarrage de l'add-on (reboot Supervisor, coupure
de courant, mise à jour) aurait retéléchargé le modèle à chaque fois,
nécessitant internet à chaque démarrage. Le vieux `cry-detector/Dockerfile`
(upstream) évitait déjà ça en téléchargeant le modèle **au moment du build**
(`TFHUB_CACHE_DIR` + `hub.load(...)` dans un `RUN`) — mon Dockerfile pour
l'add-on ne le faisait pas. Corrigé en 1.0.4 : même pattern, modèle
maintenant cuit dans l'image. Après ce rebuild (qui a besoin d'internet,
comme n'importe quelle installation), l'add-on démarre et redémarre sans
réseau. Non testé en conditions réelles (coupure internet volontaire) —
mais la mécanique (`TFHUB_CACHE_DIR` pointant vers un dossier pré-rempli au
build) est identique à celle du `cry-detector/` upstream, qui fonctionne.

Le reste de la chaîne (caméra RTSP, add-on, intégration HA, automation) est
déjà 100% local — aucune autre dépendance internet identifiée pour le
fonctionnement courant.

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
