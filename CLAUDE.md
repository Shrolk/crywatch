# crywatch (fork Pierre) — contexte pour Claude Code

Fork de [drjc1001/crywatch](https://github.com/drjc1001/crywatch) (baby monitor
self-hosté : go2rtc pour le stream WebRTC audio+vidéo, YAMNet pour distinguer un
vrai pleur d'un bruit fort). Voir `FORK_NOTES.md` pour le détail du diff.

**Ce fork a été fait par Claude (claude.ai), sans accès au terrain** : pas de
broker MQTT, pas de flux RTSP, pas de Proxmox accessibles depuis ce contexte.
Le code compile (`py_compile`) et a été relu, mais **rien n'a tourné en
conditions réelles**. Considère tout comme "à valider", pas "qui marche".

## Ce que Pierre veut au final

1. Une caméra Tapo C210 dans la chambre de son fils Simon, streamée en WebRTC
   (audio inclus) via go2rtc.
2. Un classifieur YAMNet qui distingue un vrai pleur d'un bruit fort (remplace
   le seuil dB natif de Tapo, trop de faux positifs).
3. Quand un pleur est détecté : publication MQTT vers son Mosquitto existant,
   avec HA MQTT discovery → `binary_sensor` auto-créé dans Home Assistant.
4. Une automation HA qui, sur ce binary_sensor passant à `on`, réveille un
   téléphone équipé de **Fully Kiosk Browser PLUS**, joue un bip d'alerte,
   affiche le flux caméra (son activé) pendant 1 minute, puis revient au
   dashboard précédent. (Cette automation HA a été conçue dans une conversation
   précédente — pas dans ce repo. Voir section "Automation HA" plus bas.)

## État du fork (ce qui a changé vs upstream)

- `cry-detector/yamnet_detect.py` : ajout MQTT (paho-mqtt) + HA discovery + état
  ON/OFF avec auto-retour à OFF après `CRY_STATE_TIMEOUT` (60s). `ntfy` devenu
  optionnel (vide = désactivé, avant actif par défaut).
- `.env.example`, `docker-compose.yml`, `run.sh` : variables `MQTT_*` ajoutées,
  service `ntfy` commenté par défaut.
- `examples/go2rtc.example.yaml` : adapté à une seule caméra (`simon`/`simon_hd`)
  au lieu de `cam1`/`cam2`.
- Détail complet, y compris les limites connues, dans `FORK_NOTES.md`.

## Ce qui manque pour que ça tourne (à faire avec/pour Pierre)

Ne devine pas ces valeurs — demande-les :

- [ ] IP + identifiants RTSP de la caméra Tapo C210 (Simon)
- [ ] Confirmer que le micro RTSP est activé côté app Tapo (`ffprobe` sur l'URL
      RTSP doit montrer une piste audio — sinon rien de tout ça ne peut marcher,
      c'est le préalable absolu)
- [ ] IP/port du Mosquitto de Pierre (existant, pas celui du docker-compose — il
      n'y en a pas dans ce repo) + identifiants si auth activée
- [ ] Où déployer ce docker-compose sur son Proxmox (nouvelle LXC ? VM Docker
      existante ? Il en a plusieurs : TrueNAS, Shinobi/NVR, GitLab CE, Z2M —
      demander avant de supposer)
- [ ] Est-ce que le téléphone Fully Kiosk et le serveur go2rtc seront sur le même
      réseau plat, ou faut-il renseigner `candidates:` dans go2rtc.yaml pour le
      WebRTC (NAT/VLAN) ?

## Premiers pas suggérés

1. Vérifier l'audio RTSP du C210 en premier (`ffprobe`) — c'est le point qui peut
   tout bloquer, à confirmer avant d'investir du temps ailleurs.
2. `cp examples/go2rtc.example.yaml go2rtc.yaml`, remplir, `docker compose up
   go2rtc viewer -d` seuls d'abord (sans le détecteur) pour valider le stream
   WebRTC + son dans un navigateur, avant d'ajouter la couche ML.
3. Une fois le stream validé, ajouter le cry-detector, calibrer `CRY_PROB` avec
   `CRY_LOG=1` pendant quelques minutes de bruits normaux de la pièce.
4. Vérifier dans HA que le binary_sensor apparaît (Paramètres → Appareils et
   services → MQTT) une fois le premier événement discovery publié.
5. Mettre à jour l'automation HA existante (entity_id du trigger) — voir
   `FORK_NOTES.md`, section "Lien avec l'automation Fully Kiosk".

## Style attendu

Pierre préfère un retour critique honnête à de l'approbation systématique —
signale les hypothèses fragiles, les trade-offs, les régressions potentielles,
plutôt que de simplement exécuter sans commentaire.

## Pousser ce fork sur son propre GitHub

Historique upstream conservé dans `.git` (voir `git log`). Pas de remote
configuré — c'est à faire avec Pierre (créer un repo vide côté GitHub, puis) :

```bash
git remote rename origin upstream
git remote add origin git@github.com:<pierre>/crywatch.git
git push -u origin main
```
