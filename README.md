# numeline.com

Site de Numeline, l'application qui vérifie les rappels alimentaires par numéro de lot.

- `public/` : le site statique, déployé par Vercel (numeline.com, numeline.com/fr).
- `site-tools/recall_pages.py` : génère les pages « rappels en cours »
  (`/fr/rappels-alimentaires`, `/food-recalls`) à partir des données officielles
  RappelConso, FDA et USDA FSIS.
- `.github/workflows/recall-pages.yml` : lance ce générateur deux fois par jour,
  publie le résultat et prévient Bing (IndexNow).
