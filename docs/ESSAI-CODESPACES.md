# Essayer Universal RAG Engine gratuitement (GitHub Codespaces)

Codespaces prête une machine Linux dans le navigateur, liée à votre compte GitHub. Un compte
personnel gratuit dispose de **120 heures-cœur par mois** : avec la machine de 4 cœurs et 16 Go
demandée ici, cela fait **environ 30 heures d'essai par mois**, sans carte bancaire. L'adresse
de l'essai est **privée** : seule votre session GitHub y donne accès.

Limites de l'essai : pas de GPU, donc un **petit modèle de génération** (qwen2.5:1.5b) qui
répond en 30 secondes à 1 minute, et moins fiable que le modèle recommandé sur un vrai serveur.
La recherche, les citations, l'administration et les droits fonctionnent comme en production.

## 1. Lancer l'essai : un lien, puis attendre ≈ 20 minutes

1. Connecté à GitHub (de préférence sur un ordinateur), ouvrez :
   **https://codespaces.new/DanitechChabi/universal-rag-engine/tree/claude/phase-8-licences-securite**
2. Vérifiez que la machine est **4-core / 16 GB**, puis **« Create codespace »**.
3. Attendez : tout s'installe seul (construction, 6 documents publics, modèles, indexation,
   vérification d'une recherche). Pour suivre l'avancement : en bas de l'éditeur, le lien
   « View creation log » ou l'onglet « TERMINAL ».

Si l'installation s'est interrompue, relancez-la dans le terminal (sans rien perdre) :

```bash
bash infrastructure/scripts/essai-codespaces.sh
```

## 2. Ouvrir l'application

- L'application s'ouvre normalement seule dans un nouvel onglet. Sinon : onglet **« PORTS »** →
  ligne **8443 « Universal RAG Engine »** → icône du **globe**.
- **Identifiant et mot de passe** : dans l'éditeur, ouvrez le fichier `~/ACCES-ESSAI.txt`
  (menu ☰ → File → Open File…, ou dans le terminal : `cat ~/ACCES-ESSAI.txt`).

## 3. Questions à essayer

| Question | Réponse attendue |
|---|---|
| Quel est le capital social minimum des banques dans l'UMOA depuis 2024 ? | 20 milliards FCFA |
| Quel est le taux moyen pondéré de l'adjudication n°36/H/2026 du 7 septembre 2026 ? | 3,2973 % |
| Combien de banques sont agréées au Bénin selon la liste mise à jour au 29 juin 2026 ? | 14 banques (dont 2 succursales) |
| Quels établissements de monnaie électronique sont agréés au Bénin ? | International Digital Money, Moov Money Bénin, MTN Mobile Money Bénin |
| À quelle date a été signé l'avis n°002-04-2023 de la BCEAO ? | le 11 avril 2023, à Dakar |
| Combien d'institutions de microfinance comptait l'UMOA à fin décembre 2025 ? | 524 |
| How many responses did the FSB receive to its consultation on responsible AI adoption? | around 160 |
| Quel est le salaire annuel du Gouverneur de la BCEAO ? | **aucune** : l'assistant doit dire que les documents ne le permettent pas |

À regarder aussi : les **sources** citées (cliquer sur le numéro), **« Ouvrir le document »**,
les écrans **Documents**, **Sources**, **Tableau de bord** et **Administration** (créer un
utilisateur, lui donner ou non l'accès à l'espace et vérifier qu'il ne voit que ce qu'il doit voir).

Réponses plus rapides : dans **Administration → Modèles d'IA**, ajoutez un fournisseur externe
avec **votre propre clé** (ex. Groq ou OpenRouter, offres gratuites), autorisez l'externe dans la
politique, puis testez le modèle. Les extraits des documents partent alors chez ce fournisseur :
à réserver à des documents publics comme ceux de l'essai.

## 4. Arrêter, reprendre, supprimer

- **Arrêter** : menu ☰ → « Codespaces : Stop Current Codespace » (ou github.com/codespaces). Le
  temps gratuit n'est décompté que pendant que le codespace tourne. Il s'arrête aussi seul après
  30 minutes d'inactivité.
- **Reprendre** : github.com/codespaces → votre codespace ; les services redémarrent seuls et
  les données sont conservées.
- **Supprimer** après l'essai : github.com/codespaces → « … » → Delete. L'espace disque est
  aussi décompté (15 Go-mois gratuits) tant que le codespace existe.

## En cas de problème

- Le script s'arrête sur une erreur : relancez-le, il reprend sans rien perdre.
- La page ne s'ouvre pas : onglet PORTS, vérifiez que le port 8443 est présent ; sinon
  `cd infrastructure && sudo docker compose ps`.
- Réponse « modèle indisponible » : le modèle de génération ne s'est pas téléchargé ;
  `cd infrastructure && sudo docker compose exec ollama ollama pull qwen2.5:1.5b`.
