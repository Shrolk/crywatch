# Documentation

## Configuration

| Option | Défaut | Description |
|---|---|---|
| `cameras` | — | Liste des caméras : `name` (libellé) + `rtsp_url` (URL RTSP complète, avec identifiants). Au moins une requise. |
| `cry_prob` | `0.4` | Probabilité de pleur (0-1) à partir de laquelle un échantillon compte comme "pleur". Monte si trop de faux positifs, baisse s'il en rate. |
| `sustain_samples` | `2` | Échantillons consécutifs au-dessus du seuil avant de déclencher. |
| `cooldown` | `60` | Secondes minimum entre deux déclenchements. |
| `sample_sec` | `2.0` | Durée (s) de chaque burst audio analysé. |
| `rms_gate_db` | `-60` | En dessous de ce niveau (silence), le modèle n'est même pas appelé. |
| `state_timeout` | `60` | Secondes sans nouveau pleur avant que le capteur "pleurs détectés" repasse à OFF. |
| `log_scores` | `false` | `true` = affiche le score de chaque échantillon dans les logs de l'add-on (utile pour calibrer `cry_prob`, à activer temporairement). |

## Après une modification de `cameras`

L'add-on doit redémarrer pour relire `cameras` (Supervisor le fait
automatiquement à la sauvegarde de la Configuration). Ensuite, dans Home
Assistant, recharge l'intégration **Crywatch** (Paramètres → Appareils et
services → Crywatch → ⋮ → Recharger) pour que les nouvelles entités
apparaissent.

## Vérifier que ça tourne

Onglet **Journal** de l'add-on : au démarrage tu dois voir
`[yamnet] ready. ...`, puis (avec `log_scores: true`) une ligne par caméra
toutes les ~2s du type :

```
[Chambre Simon] cry=0.02 rms=-45dB top='Speech' streak=0
```

## Ce n'est PAS exposé sur le réseau local

Aucun port n'est publié : l'API d'état (`/api/state`) n'est joignable que
depuis Home Assistant Core lui-même, via le réseau interne de Supervisor.
