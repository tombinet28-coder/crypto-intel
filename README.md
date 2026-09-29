# 🪙 Crypto Intel — ton terminal crypto personnel

Ce que fait ce système, une fois installé :
- **06h30** : un briefing complet (avec un plan B automatique si la tâche de 6h20 ne part pas) sur ton tableau de bord, et un résumé (TL;DR + watchlist) sur Telegram.
- **Toutes les 30 min** : il surveille les news, les comptes X officiels et les mouvements de prix.
- **🚨 CRITICAL** : notification immédiate sur ton téléphone, 6 maximum par jour.
- **🔔 IMPORTANT** : envoyées aussi tout de suite, 15 maximum par jour. Au-delà, elles sont regroupées dans les récaps de 12h30 et 18h30.
- **Nuit calme** : entre 23h et 6h30, seules les alertes critiques passent.

Pas besoin de savoir coder. Tout se fait depuis le site de GitHub.

**Temps d'installation** : environ 45 minutes. **Coût** : environ 20 à 30 $/mois, sans l'API X (détail dans `ARCHITECTURE.md`).

> Système d'information uniquement : il ne donne aucun conseil d'achat ou de vente et n'a jamais accès à tes fonds.

---

## Étape 1 — Créer le dépôt GitHub (10 min, possible depuis un téléphone)

Utilise le **navigateur** (Safari ou Chrome), pas l'application GitHub.

1. Sur **github.com**, touche **+ → New repository**. Nom : `crypto-intel`. Choisis **Public**, puis touche **Create repository**.
2. Sur la page du dépôt vide, touche **creating a new file**. Comme nom de fichier, tape `.github/workflows/crypto.yml`, colle le contenu du fichier `crypto.yml`, puis touche **Commit changes**.
3. Enregistre `crypto-intel.zip` dans les fichiers de ton téléphone. Dans le dépôt, touche **Add file → Upload files**, choisis le zip, puis touche **Commit changes**.
4. Onglet **Actions** → **Crypto Intel** → **Run workflow** → action **installer** → **Run workflow**. Au bout d'environ 1 minute, une coche verte apparaît et tous les fichiers sont en place.

Sur ordinateur, tu peux aussi glisser directement tout le contenu du dossier, y compris le dossier caché `.github`.

Si un bouton n'apparaît pas sur téléphone, active **« Version ordinateur »** dans le menu du navigateur.

## Étape 2 — Clé API Claude (5 min)

1. Va sur **console.anthropic.com**, crée un compte et ajoute un moyen de paiement.
2. Dans **Limits**, fixe une limite de dépense mensuelle, par exemple 40 $.
3. Dans **API Keys**, clique sur **Create Key**. Copie la clé (elle commence par `sk-ant-`) et garde-la de côté.

## Étape 3 — Ton bot Telegram (10 min)

1. Dans Telegram, cherche **@BotFather** et envoie `/newbot`. Choisis un nom, par exemple « Mon Crypto Daily ».
2. BotFather te donne un **token**, du type `123456:ABC-…`. Garde-le de côté.
3. Ouvre la conversation avec ton nouveau bot et envoie-lui « bonjour ».
4. Dans ton navigateur, ouvre `https://api.telegram.org/bot<TON_TOKEN>/getUpdates` (en remplaçant `<TON_TOKEN>`). Cherche `"chat":{"id":` : le nombre qui suit est ton **chat_id**.

## Étape 4 — Clé CoinGecko gratuite (3 min)

Sur **coingecko.com/en/api**, crée une clé **Demo**. Elle est gratuite.

## Étape 5 — Ranger les clés dans GitHub (5 min)

Dans ton dépôt : **Settings → Secrets and variables → Actions → New repository secret**. Ajoute ces secrets un par un :

| Nom | Valeur |
|---|---|
| `ANTHROPIC_API_KEY` | la clé de l'étape 2 |
| `TELEGRAM_BOT_TOKEN` | le token de l'étape 3 |
| `TELEGRAM_CHAT_ID` | le chat_id de l'étape 3 |
| `COINGECKO_API_KEY` | la clé de l'étape 4 |
| `CONTACT_EMAIL` | ton e-mail (demandé par la SEC pour lire ses flux) |
| `X_BEARER_TOKEN` | *(optionnel, voir étape 8)* |

Les secrets ne sont jamais visibles, même si le dépôt est public.

## Étape 6 — Publier le tableau de bord (3 min)

1. Va dans **Settings → Pages**. Source : **Deploy from a branch**, branche `main`, dossier `/docs`. Clique sur **Save**.
2. Après une minute, GitHub affiche ton adresse, du type `https://ton-pseudo.github.io/crypto-intel/`.
3. Ouvre `config.yaml` dans GitHub (icône crayon), colle cette adresse dans `dashboard_url`, puis clique sur **Commit**.
4. Sur ton téléphone, ouvre l'adresse puis **Partager → Sur l'écran d'accueil** : le tableau de bord s'ouvre alors comme une appli.

## Étape 7 — Tester (5 min)

1. Onglet **Actions** : si GitHub le demande, touche **I understand… enable them**.
2. **Crypto Intel → Run workflow → test-telegram** : tu dois recevoir un message sur Telegram.
3. **Crypto Intel → Run workflow → briefing** : après 2 à 4 minutes, le briefing arrive sur Telegram et sur ton tableau de bord.

C'est fini : le système tourne maintenant tout seul.

## Étape 8 — (Optionnel) Surveiller X

1. Sur **console.x.com**, crée une application, ajoute du crédit (quelques dollars suffisent pour commencer) et fixe une limite de dépense.
2. Copie le **Bearer Token** dans le secret `X_BEARER_TOKEN`.
3. Dans **Actions → Crypto Intel → Run workflow**, choisis **resolve-x**. Il affiche l'identifiant numérique de chaque compte.
4. Colle ces identifiants dans `config.yaml` (champ `id`), puis vérifie chaque compte une fois sur x.com. C'est ce qui protège contre les faux comptes qui imitent un pseudo.

---

## Personnaliser

Tout se règle dans `config.yaml` :
- **Tes cryptos prioritaires** : `priority_assets`.
- **Les seuils d'alerte** : +5 % / +10 % en 1 h, plafond quotidien, heures des récaps, heures calmes.
- **Les sources** et leur niveau de fiabilité.
- **Les comptes X** surveillés.

Les règles de rédaction du briefing (pas de hype, sources obligatoires, niveaux de confiance…) sont dans `prompts/briefing_system.md`, en français.

## Public ou privé ?

- **Public (recommandé)** : GitHub Actions et Pages sont gratuits et illimités. Tes clés restent secrètes, mais n'importe qui peut lire tes briefings et voir tes cryptos prioritaires.
- **Privé** : 2 000 minutes gratuites par mois (ça suffit, tout juste), mais GitHub Pages devient payant. Tu gardes alors Telegram et le tableau de bord dans Claude, ou tu héberges la page sur Cloudflare Pages, qui est gratuit.

## Heure exacte

GitHub peut retarder les tâches planifiées de quelques minutes aux heures chargées. Le briefing arrive donc généralement entre 6h20 et 6h40.

Pour une heure garantie : crée un compte gratuit sur **cron-job.org** et programme un appel à 6h25 vers l'API GitHub `workflow_dispatch` du workflow « Crypto Intel », avec l'action `briefing`. Il te faudra un jeton GitHub limité à ce dépôt, avec la permission « Actions : read and write ».

## En cas de problème

- **Rien sur Telegram** : lance l'action `test-telegram`, puis vérifie les deux secrets Telegram.
- **Le briefing échoue** : tu reçois « ⚠️ Le briefing a échoué » avec la raison. Ouvre **Actions**, clique sur l'exécution en rouge et lis la ligne d'erreur. Le plus souvent, la clé API est invalide ou la limite de dépense est atteinte.
- **Un flux RSS ne répond plus** : il est ignoré automatiquement. Tu peux le retirer de `config.yaml`.
- **Les tâches planifiées se sont arrêtées** : GitHub les suspend après 60 jours sans activité dans le dépôt. Les enregistrements automatiques du bot comptent normalement comme de l'activité ; sinon, réactive-les dans **Actions**.

## Structure

```
config.yaml                  tes réglages
prompts/                     les consignes éditoriales (tes règles, en français)
src/briefing.py              le briefing de 06h30
src/monitor.py               la surveillance toutes les 30 min
src/collectors.py            la collecte (CoinGecko, DefiLlama, RSS, X)
src/reliability.py           les règles de fiabilité des sources
src/notify.py                les messages Telegram
docs/index.html              le tableau de bord (mobile, dark mode)
docs/data/                   les briefings (fichiers JSON)
.github/workflows/crypto.yml  la planification automatique et l'installation
tests/test_offline.py        les vérifications (python -m tests.test_offline)
```
