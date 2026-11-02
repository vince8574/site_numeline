#!/usr/bin/env python3
"""Génère les pages « rappels en cours » du site, à partir des données officielles.

  public/fr/rappels-alimentaires.html  ← RappelConso (data.economie.gouv.fr)
  public/food-recalls.html             ← FDA (openFDA + export iRES) et USDA FSIS

Lancé chaque jour par .github/workflows/recall-pages.yml. Le HTML est écrit en
dur (pas de chargement en JavaScript) pour que Google indexe la liste.

Bibliothèque standard uniquement. Si une source est indisponible, la page
correspondante n'est PAS réécrite : mieux vaut une liste d'hier qu'une liste vide.
"""
import csv
import datetime as dt
import html
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = os.path.join(ROOT, 'public')
UA = {'User-Agent': 'Mozilla/5.0 (compatible; NumelineRecallPages/1.0; +https://numeline.com)'}
TODAY = dt.date.today()
FR_DAYS = 30
# Photos des fiches RappelConso : fournies par les entreprises (emballages, marques),
# elles ne relèvent pas de la Licence Ouverte des données. Affichées en vignette,
# chargées depuis rappel.conso.gouv.fr, avec la mention « Photo : RappelConso »
# (choix validé par Numeline le 24/10/2026).
SHOW_RC_IMAGES = True
US_DAYS = 60

MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
        'septembre', 'octobre', 'novembre', 'décembre']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
          'September', 'October', 'November', 'December']


def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def e(s):
    return html.escape(s or '', quote=True)


def clip(s, n):
    s = re.sub(r'\s+', ' ', s or '').strip(' ,;|')
    return s if len(s) <= n else s[:n].rsplit(' ', 1)[0].rstrip(' ,;') + '…'


def fr_date(d):
    return '%d %s %d' % (d.day, MOIS[d.month - 1], d.year)


def en_date(d):
    return '%s %d, %d' % (MONTHS[d.month - 1], d.day, d.year)


# ───────────────────────── articles du blog (liens « notre analyse ») ──────────

def blog_index(folder, url_prefix):
    """Titre, mots-clés et date de chaque article, pour relier un rappel à son analyse."""
    out = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith('.html') or f == 'index.html' or f.startswith('_'):
            continue
        s = io.open(os.path.join(folder, f), encoding='utf-8').read()
        title = re.search(r'<title>(.*?)</title>', s, re.S)
        kw = re.search(r'"keywords":\s*"(.*?)"', s)
        date = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})"', s)
        h1 = re.search(r'<h1>(.*?)</h1>', s, re.S)
        if not (title and date):
            continue
        out.append({
            'url': url_prefix + f[:-5],
            'title': html.unescape(re.sub(r'<[^>]+>', '', h1.group(1) if h1 else title.group(1))).strip(),
            'hay': html.unescape(title.group(1) + ' ' + (kw.group(1) if kw else '')).lower(),
            'date': dt.date.fromisoformat(date.group(1)),
        })
    return out


STOP = {'sans marque', 'neutre', 'aucune', 'non applicable', 'vendu en vrac', '/', '-', 'n/a',
        'inc', 'llc', 'corp', 'company', 'foods', 'food', 'the', 'farms', 'usa', 'products'}


# Marques d'enseigne : elles couvrent des centaines de produits sans rapport entre
# eux. Pour elles, la marque ne suffit pas, il faut aussi un mot du produit.
RETAIL = {'auchan', 'carrefour', 'leclerc', 'e.leclerc', 'monoprix', 'netto', 'lidl', 'aldi', 'intermarché',
          'intermarche', 'casino', 'franprix', 'metro', 'metro chef', 'bio village', 'marque repère', 'picard',
          'filière qualité carrefour', 'carrefour sensation', 'carrefour bio', 'carrefour le marché',
          'auchan le poissonnier', 'u', 'u saveurs', 'u bio', 'great value', 'kirkland', 'walmart', 'kroger'}


def words(s):
    return {w for w in re.findall(r'[a-zàâçéèêëîïôûùüÿœ]{5,}', (s or '').lower())}


def find_article(articles, names, day, product=''):
    pw = words(product)
    for n in names:
        n = (n or '').lower().strip()
        if len(n) < 4 or n in STOP:
            continue
        for a in articles:
            if not (-3 <= (a['date'] - day).days <= 30):
                continue
            if not re.search(r'(?<![a-z])' + re.escape(n) + r'(?![a-z])', a['hay']):
                continue
            if (n in RETAIL or any(n.startswith(x + ' ') for x in RETAIL)) and not (pw & words(a['hay'])):
                continue
            return a
    return None


# ───────────────────────── page commune ───────────────────────────────────────

CSS = """
.rc-hero { margin: 8px 0 18px; }
.rc-hero h1 { margin-bottom: 10px; }
.rc-updated { font-size: 14px; color: var(--muted); margin: 0 0 6px; }
.rc-intro { font-size: 16px; line-height: 1.65; margin: 0 0 16px; }
.rc-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 22px; }
.rc-filters button {
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
  padding: 7px 12px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--surface); color: var(--accent-dark);
}
.rc-filters button[aria-pressed="true"] { background: var(--accent-dark); border-color: var(--accent-dark); color: #fff; }
.rc-filters button .n { opacity: 0.7; font-weight: 500; margin-left: 4px; }
.rc-day { font-family: "Fraunces", Georgia, serif; font-size: 20px; margin: 26px 0 10px; color: var(--accent-dark); }
.rc-list { display: grid; gap: 10px; }
.rc-item {
  background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 4px 14px rgba(10, 31, 31, 0.05);
}
.rc-item.has-img { display: grid; grid-template-columns: 84px minmax(0, 1fr); gap: 14px; align-items: start; }
.rc-fig { margin: 0; }
.rc-thumb {
  display: block; width: 84px; height: 84px; object-fit: contain; border-radius: 10px;
  background: #fff; border: 1px solid var(--line);
}
.rc-fig figcaption { font-size: 10px; line-height: 1.3; color: var(--muted); text-align: center; margin-top: 4px; }
@media (max-width: 520px) {
  .rc-item.has-img { grid-template-columns: 60px minmax(0, 1fr); gap: 10px; }
  .rc-thumb { width: 60px; height: 60px; }
}
.rc-item h3 { margin: 6px 0 4px; font-size: 16px; line-height: 1.35; color: var(--accent-dark); }
.rc-brand { font-size: 14px; font-weight: 600; color: var(--ink-soft); }
.rc-meta { font-size: 13.5px; color: var(--muted); line-height: 1.55; margin: 4px 0 0; overflow-wrap: anywhere; }
.rc-meta strong { color: var(--ink-soft); font-weight: 600; }
.rc-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.rc-tag { font-size: 11.5px; font-weight: 700; letter-spacing: 0.2px; padding: 3px 9px; border-radius: 999px; background: #e7f4f0; color: #0a5c47; }
.rc-tag.hot { background: #fde8e6; color: #9b1c12; }
.rc-tag.mid { background: #fff3dc; color: #7a4b00; }
.rc-links { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-top: 8px; font-size: 13.5px; font-weight: 600; }
.rc-links a { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
.rc-empty { display: none; color: var(--muted); }
.rc-faq h2 { margin-top: 40px; }
.rc-faq h3 { margin: 20px 0 6px; font-size: 17px; }
.rc-faq p { margin: 0 0 10px; line-height: 1.65; }
.rc-sources { font-size: 13px; color: var(--muted); margin-top: 26px; line-height: 1.6; }
"""

FILTER_JS = """
(function () {
  var btns = document.querySelectorAll('.rc-filters button');
  var items = document.querySelectorAll('.rc-item');
  var days = document.querySelectorAll('.rc-day');
  Array.prototype.forEach.call(btns, function (b) {
    b.addEventListener('click', function () {
      var f = b.getAttribute('data-f');
      Array.prototype.forEach.call(btns, function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      Array.prototype.forEach.call(items, function (it) {
        var ok = f === 'all' || it.getAttribute('data-cat') === f || (f.indexOf('agency:') === 0 && it.getAttribute('data-agency') === f.slice(7));
        it.style.display = ok ? '' : 'none';
        if (ok && it.classList.contains('has-img')) it.style.display = 'grid';
      });
      Array.prototype.forEach.call(days, function (d) {
        var list = d.nextElementSibling, any = false;
        Array.prototype.forEach.call(list.children, function (c) { if (c.style.display !== 'none') any = true; });
        d.style.display = list.style.display = any ? '' : 'none';
      });
    });
  });
})();
"""


def page(lang, canonical, title, description, h1, updated, intro, filters, groups, faq, sources, nav, footer, cta, breadcrumb, itemlist):
    faq_ld = {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
        {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub(r'<[^>]+>', '', a)}} for q, a in faq]}
    coll_ld = {'@context': 'https://schema.org', '@type': 'CollectionPage', 'name': h1, 'description': description,
               'url': canonical, 'inLanguage': 'fr-FR' if lang == 'fr' else 'en-US', 'dateModified': TODAY.isoformat(),
               'mainEntity': {'@type': 'ItemList', 'numberOfItems': len(itemlist),
                              'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'url': u}
                                                  for i, (n, u) in enumerate(itemlist[:30])]}}
    crumb_ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, **({'item': u} if u else {})} for i, (n, u) in enumerate(breadcrumb)]}
    lds = ''.join('  <script type="application/ld+json">\n%s\n  </script>\n' % json.dumps(x, ensure_ascii=False, indent=2) for x in (coll_ld, crumb_ld, faq_ld))
    home = '/fr/' if lang == 'fr' else '/'
    out = []
    out.append('''<!DOCTYPE html>
<html lang="%(lang)s">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
  <link rel="icon" type="image/png" sizes="48x48" href="/favicon-48.png" />
  <link rel="icon" type="image/png" sizes="96x96" href="/favicon-96.png" />
  <link rel="icon" type="image/png" sizes="192x192" href="/favicon-192.png" />
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
  <script src="/favicon-anim.js" defer></script>
  <script src="/nav-toggle.js" defer></script>
  <title>%(title)s</title>
  <meta name="description" content="%(desc)s" />
  <link rel="canonical" href="%(canon)s" />
  <meta name="robots" content="index, follow, max-image-preview:large" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Numeline" />
  <meta property="og:locale" content="%(locale)s" />
  <meta property="og:title" content="%(title)s" />
  <meta property="og:description" content="%(desc)s" />
  <meta property="og:url" content="%(canon)s" />
  <meta property="og:image" content="%(img)s" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700&family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="/blog/blog.css" />
  <style>%(css)s</style>
%(lds)s</head>
<body>
  <div class="page">
    <header class="topbar">
      <a class="brand" href="%(home)s"><img class="brand-mark" src="/logo-mark.png" alt="" width="36" height="36" />Numeline</a>
      <nav class="nav">
%(nav)s
      </nav>
    </header>

    <main class="article">
      <section class="rc-hero">
        <div class="eyebrow">%(eyebrow)s</div>
        <h1>%(h1)s</h1>
        <p class="rc-updated">%(updated)s</p>
        <p class="rc-intro">%(intro)s</p>
      </section>
''' % {'lang': lang, 'title': e(title), 'desc': e(description), 'canon': canonical,
       'locale': 'fr_FR' if lang == 'fr' else 'en_US',
       'img': 'https://numeline.com/fr/numeline-feature-graphic-fr-1024x500.png' if lang == 'fr' else 'https://numeline.com/feature-graphic-1024x500.png',
       'css': CSS, 'lds': lds, 'home': home, 'nav': nav, 'h1': e(h1), 'updated': updated, 'intro': intro,
       'eyebrow': 'Données officielles RappelConso' if lang == 'fr' else 'Official FDA &amp; USDA data'})
    out.append('      <div class="rc-filters" role="group" aria-label="%s">\n' % ('Filtrer par motif' if lang == 'fr' else 'Filter by reason'))
    for i, (key, label, n) in enumerate(filters):
        out.append('        <button type="button" data-f="%s" aria-pressed="%s">%s<span class="n">%d</span></button>\n'
                   % (key, 'true' if i == 0 else 'false', e(label), n))
    out.append('      </div>\n')
    for day_label, items in groups:
        out.append('      <h2 class="rc-day">%s</h2>\n      <div class="rc-list">\n%s      </div>\n' % (e(day_label), ''.join(items)))
    out.append('      <section class="rc-faq">\n')
    out.append('        <h2>%s</h2>\n' % ('Questions fréquentes' if lang == 'fr' else 'Frequently asked questions'))
    for q, a in faq:
        out.append('        <h3>%s</h3>\n        <p>%s</p>\n' % (e(q), a))
    out.append('      </section>\n')
    out.append(cta)
    out.append('      <p class="rc-sources">%s</p>\n    </main>\n\n%s\n  </div>\n  <script>%s</script>\n</body>\n</html>\n'
               % (sources, footer, FILTER_JS))
    return ''.join(out)


def write_if_changed(path, content):
    old = io.open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if old == content:
        print('inchangé', path)
        return False
    io.open(path, 'w', encoding='utf-8', newline='\n').write(content)
    print('écrit', path)
    return True


# ───────────────────────── FRANCE : RappelConso ───────────────────────────────

FR_CATS = [
    ('listeria', 'Listeria', 'hot'),
    ('salmonelle', 'Salmonelle', 'hot'),
    ('ecoli', 'E. coli', 'hot'),
    ('allergenes', 'Allergènes', 'mid'),
    ('corps', 'Corps étrangers', 'mid'),
    ('chimique', 'Contaminants, résidus', 'mid'),
    ('fabrication', 'Défaut de fabrication', ''),
    ('autres', 'Autres motifs', ''),
]


def fr_cat(r):
    t = ((r.get('risques_encourus') or '') + ' ' + (r.get('motif_rappel') or '')).lower()
    if 'listeria' in t:
        return 'listeria'
    if 'salmonell' in t:
        return 'salmonelle'
    if 'coli' in t:
        return 'ecoli'
    if 'allerg' in t:
        return 'allergenes'
    if any(w in t for w in ('inertes', 'corps étranger', 'corps etranger', 'verre', 'métal', 'plastique')):
        return 'corps'
    if any(w in t for w in ('chimique', 'résidu', 'pesticide', 'histamine', 'toxine', 'mycotoxine', 'aflatoxine',
                            'ochratoxine', 'additif', 'substance interdite', 'oxyde', 'thc', 'plomb', 'cadmium')):
        return 'chimique'
    if any(w in t for w in ('fabrication', 'étanchéité', 'conditionnement')):
        return 'fabrication'
    return 'autres'


def cap(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s[:1].upper() + s[1:]


def brand(s):
    s = re.sub(r'\s+', ' ', s or '').strip()
    if s.lower() in STOP or len(s) < 2:
        return ''
    return ' '.join(w if any(c.isupper() for c in w) else w[:1].upper() + w[1:] for w in s.split(' '))


def fr_lots(ids):
    """identification_produits : [gtin, lot, type de date, date, '|gtin', ...] → texte court."""
    groups, cur = [], []
    for x in ids or []:
        x = str(x)
        if x.startswith('|'):
            groups.append(cur)
            cur = [x[1:]]
        else:
            cur.append(x)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        g = [x for x in g if x and x.lower() not in ('non concerné', 'date limite de consommation', 'date de durabilité minimale')]
        if not g:
            continue
        gtin = g[0] if re.fullmatch(r'\d{8,14}', g[0]) else ''
        lot = next((x for x in g[1:] if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)), '') if gtin else g[0]
        date = next((x for x in g if re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)), '')
        parts = []
        if lot:
            parts.append('lot ' + lot)
        if date:
            d = dt.date.fromisoformat(date)
            parts.append('date %02d/%02d/%d' % (d.day, d.month, d.year))
        if gtin:
            parts.append('EAN ' + gtin)
        if parts:
            out.append(', '.join(parts))
    uniq = list(dict.fromkeys(out))
    txt = ' · '.join(uniq[:3])
    if len(uniq) > 3:
        txt += ' · +%d autres' % (len(uniq) - 3)
    return txt


def build_fr():
    since = (TODAY - dt.timedelta(days=FR_DAYS)).isoformat()
    q = urllib.parse.urlencode({
        'where': 'date_publication >= "%s" and categorie_produit = "alimentation"' % since,
        'order_by': 'date_publication desc'})
    rows = json.loads(get('https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/rappelconso-v2-gtin-espaces/exports/json?' + q))
    fiches = {}
    for r in rows:
        k = r.get('numero_fiche') or r.get('id')
        if k in fiches:
            # fiche multi-produits : on cumule les identifications
            fiches[k]['identification_produits'] = (fiches[k].get('identification_produits') or []) + ['|' + str(x) if i == 0 else x for i, x in enumerate(r.get('identification_produits') or [])]
            continue
        fiches[k] = dict(r)
    recs = sorted(fiches.values(), key=lambda r: r['date_publication'], reverse=True)
    RUN['rappelconso'] = '%d fiches' % len(fiches)
    if len(recs) < 10:
        raise RuntimeError('RappelConso : seulement %d fiches, on ne réécrit pas la page' % len(recs))
    articles = blog_index(os.path.join(PUBLIC, 'fr', 'blog'), '/fr/blog/')
    labels = {k: (l, c) for k, l, c in FR_CATS}
    counts = {k: 0 for k, _, _ in FR_CATS}
    groups, cur_day, cur = [], None, []
    itemlist = []
    for r in recs:
        day = dt.date.fromisoformat(r['date_publication'][:10])
        cat = fr_cat(r)
        counts[cat] += 1
        label, cls = labels[cat]
        name = cap(r.get('libelle') or r.get('modeles_ou_references') or 'Produit alimentaire')
        mq = brand(r.get('marque_produit'))
        sub = cap(r.get('sous_categorie_produit') or '')
        if sub.lower() in ('autres', 'autre'):
            sub = ''
        art = find_article(articles, [r.get('marque_produit')], day, r.get('libelle') or '')
        link = r.get('lien_vers_la_fiche_rappel') or 'https://rappel.conso.gouv.fr'
        itemlist.append(('%s%s' % (name, ' — ' + mq if mq else ''), link))
        meta = []
        motif = clip(cap(r.get('motif_rappel') or ''), 170)
        if motif:
            meta.append('<strong>Motif :</strong> ' + e(motif))
        lots = fr_lots(r.get('identification_produits'))
        if lots:
            meta.append('<strong>Identification :</strong> ' + e(clip(lots, 220)))
        # les fiches listent souvent les magasins en « - magasin, - magasin »
        dist = re.sub(r'[\t¤]+', '\n', r.get('distributeurs') or '')
        dist = re.sub(r'\s*(?:\n|(?:^|[,\s])-\s+)\s*-?\s*', ', ', dist)
        dist = re.sub(r'(?:,\s*)+', ', ', dist).strip(' ,-')
        dist = clip(cap(dist), 140)
        zone = clip(', '.join(cap(z) for z in (r.get('zone_geographique_de_vente') or '').split('|') if z), 90)
        where = ' — '.join(x for x in (dist, zone) if x)
        if where:
            meta.append('<strong>Où :</strong> ' + e(where))
        links = '<a href="%s" target="_blank" rel="noopener">Fiche officielle RappelConso</a>' % e(link)
        if art:
            links += '<a href="%s">Notre analyse</a>' % e(art['url'])
        # photo officielle de la fiche, en vignette de taille fixe (la carte ne grandit pas)
        img = SHOW_RC_IMAGES and next((u.strip() for u in re.split(r'[|\s]+', r.get('liens_vers_les_images') or '') if u.strip().startswith('https://')), '')
        thumb = ('          <figure class="rc-fig"><img class="rc-thumb" src="%s" alt="%s" width="84" height="84" loading="lazy" decoding="async" referrerpolicy="no-referrer-when-downgrade" />'
                 '<figcaption>Photo : RappelConso</figcaption></figure>\n'
                 % (e(img), e('Photo officielle : ' + name))) if img else ''
        item = ('        <article class="rc-item%s" data-cat="%s">\n%s          <div class="rc-body">\n          <div class="rc-tags"><span class="rc-tag %s">%s</span>%s</div>\n'
                '          <h3>%s</h3>\n%s          <p class="rc-meta">%s</p>\n          <div class="rc-links">%s</div>\n          </div>\n        </article>\n') % (
            ' has-img' if img else '', cat, thumb, cls, e(label), ('<span class="rc-tag">%s</span>' % e(sub)) if sub else '', e(name),
            ('          <div class="rc-brand">%s</div>\n' % e(mq)) if mq else '', '<br />'.join(meta), links)
        if day != cur_day:
            if cur:
                groups.append((fr_date(cur_day), cur))
            cur_day, cur = day, []
        cur.append(item)
    if cur:
        groups.append((fr_date(cur_day), cur))
    filters = [('all', 'Tous', len(recs))] + [(k, l, counts[k]) for k, l, _ in FR_CATS if counts[k]]
    n = len(recs)
    top = ', '.join('%d pour %s' % (counts[k], l if k != 'autres' else 'autres motifs') for k, l, _ in FR_CATS[:3] if counts[k])
    nav = '\n'.join('        ' + x for x in [
        '<a href="/fr/">Accueil</a>', '<a href="/fr/blog/">Blog</a>',
        '<a href="/fr/rappels-alimentaires" aria-current="page">Rappels en cours</a>',
        '<a href="/fr/contact">Contact</a>', '<a href="/food-recalls" hreflang="en">EN</a>'])
    faq = [
        ("Qu'est-ce qu'un rappel alimentaire ?",
         "C'est le retrait d'un produit déjà vendu, parce qu'il présente un risque : bactérie (Listeria, salmonelle, E. coli), allergène non déclaré, corps étranger, contaminant chimique ou défaut de fabrication. En France, chaque rappel fait l'objet d'une fiche publiée sur RappelConso, le site officiel géré par la DGCCRF et la DGAL."),
        ("Comment savoir si mon produit est rappelé ?",
         "Comparez la marque, le code-barres (EAN), le numéro de lot et la date limite inscrits sur l'emballage avec ceux de la fiche de rappel. Le produit n'est concerné que si le lot correspond. L'application <a href=\"/fr/\">Numeline</a> fait cette vérification à votre place : elle scanne le numéro de lot et le compare aux rappels officiels."),
        ("Que faire si j'ai un produit rappelé ?",
         "Ne le consommez pas. Rapportez-le au magasin, qui doit vous rembourser, ou détruisez-le selon les consignes de la fiche. Si vous en avez mangé et présentez des symptômes, consultez votre médecin en lui signalant cette consommation."),
        ("La congélation ou la cuisson rendent-elles un produit rappelé sans danger ?",
         "Non. La congélation n'élimine pas Listeria, et la cuisson ne fait disparaître ni un allergène, ni un corps étranger, ni un contaminant chimique. Suivez toujours la consigne de la fiche de rappel."),
        ("À quelle fréquence cette liste est-elle mise à jour ?",
         "Chaque jour, automatiquement, à partir des données ouvertes de RappelConso. Elle couvre les rappels alimentaires publiés au cours des %d derniers jours. Nos <a href=\"/fr/blog/\">articles de blog</a> analysent les rappels les plus importants." % FR_DAYS),
    ]
    cta = ('      <div class="cta-app">\n        <h3>Vérifier un produit en un scan</h3>\n'
           '        <p>Numeline lit le numéro de lot de vos produits et le compare aux rappels officiels. Gratuit sur iOS et Android.</p>\n'
           '        <div class="cta-buttons">\n'
           '          <a class="cta-btn" href="https://apps.apple.com/fr/app/numelinefr/id6772080722" target="_blank" rel="noopener"><span><span class="b-sub">Télécharger dans l&rsquo;</span><span class="b-main">App Store</span></span></a>\n'
           '          <a class="cta-btn" href="https://play.google.com/store/apps/details?id=com.numeline.app" target="_blank" rel="noopener"><span><span class="b-sub">Disponible sur</span><span class="b-main">Google Play</span></span></a>\n'
           '        </div>\n      </div>\n')
    footer = ('    <footer class="footer">\n      <div>Numeline — Le radar des rappels alimentaires</div>\n'
              '      <div><a href="/fr/blog/">Nos articles</a> · <a href="/fr/mentions-legales">Mentions légales</a> · <a href="/fr/contact">Contact</a></div>\n    </footer>')
    html_ = page(
        'fr', 'https://numeline.com/fr/rappels-alimentaires',
        'Rappels alimentaires en cours : la liste mise à jour chaque jour',
        'Tous les rappels alimentaires des %d derniers jours en France : produits, marques, lots, motifs et magasins. Mis à jour chaque jour depuis RappelConso.' % FR_DAYS,
        'Rappels alimentaires en cours',
        'Mis à jour le <time datetime="%s">%s</time> · %d rappels publiés depuis le %s' % (
            TODAY.isoformat(), fr_date(TODAY), n, fr_date(TODAY - dt.timedelta(days=FR_DAYS))),
        "La liste de tous les <strong>rappels alimentaires</strong> publiés en France ces %d derniers jours, à partir des fiches officielles de <strong>RappelConso</strong>. Dont %s. Pour chaque produit : la marque, le motif, les numéros de lot et les magasins concernés." % (FR_DAYS, top),
        filters, groups, faq,
        'Source : <a href="https://rappel.conso.gouv.fr" target="_blank" rel="noopener">RappelConso</a> (DGCCRF, DGAL), données ouvertes publiées sur <a href="https://data.economie.gouv.fr/explore/dataset/rappelconso-v2-gtin-espaces/" target="_blank" rel="noopener">data.economie.gouv.fr</a> (Licence Ouverte). Photos des produits : fiches RappelConso, fournies par les entreprises qui rappellent. Numeline est une application indépendante, non affiliée aux autorités. En cas de doute, la fiche officielle fait foi.',
        nav, footer, cta,
        [('Accueil', 'https://numeline.com/fr/'), ('Rappels alimentaires en cours', None)], itemlist)
    return write_if_changed(os.path.join(PUBLIC, 'fr', 'rappels-alimentaires.html'), html_)


# ───────────────────────── USA : FDA + USDA ───────────────────────────────────

US_CATS = [
    ('listeria', 'Listeria', 'hot'),
    ('salmonella', 'Salmonella', 'hot'),
    ('ecoli', 'E. coli', 'hot'),
    ('allergens', 'Undeclared allergens', 'mid'),
    ('foreign', 'Foreign material', 'mid'),
    ('chemical', 'Lead & contaminants', 'mid'),
    ('uninspected', 'Uninspected or ineligible imports', 'mid'),
    ('other', 'Other reasons', ''),
]


def us_cat(t):
    t = (t or '').lower()
    if 'listeria' in t:
        return 'listeria'
    if 'salmonell' in t:
        return 'salmonella'
    if 'coli' in t or 'stec' in t or 'o157' in t:
        return 'ecoli'
    # avant les allergènes : un produit non inspecté est souvent aussi « misbranded »
    if any(w in t for w in ('without the benefit of', 'without benefit of', 'import violation', 'ineligible', 'reinspection', 'without inspection')):
        return 'uninspected'
    if 'undeclared' in t or 'allergen' in t or 'misbrand' in t:
        return 'allergens'
    if any(w in t for w in ('foreign', 'glass', 'metal', 'plastic', 'rubber', 'wood', 'bone fragment')):
        return 'foreign'
    if any(w in t for w in ('lead', 'arsenic', 'cadmium', 'mercury', 'pesticide', 'heavy metal', 'histamine', 'aflatoxin', 'dmaa', 'sildenafil', 'tadalafil', 'unapproved', 'patulin', 'cereulide')):
        return 'chemical'
    return 'other'


def us_date(s):
    s = (s or '').strip()
    if re.fullmatch(r'\d{8}', s):
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def fda_records():
    """openFDA (historique, avec une à deux semaines de retard) + export iRES (les plus récents)."""
    recs = {}
    since = TODAY - dt.timedelta(days=US_DAYS)
    url = 'https://api.fda.gov/food/enforcement.json?search=report_date:[%s+TO+%s]&limit=1000' % (
        since.strftime('%Y%m%d'), (TODAY + dt.timedelta(days=14)).strftime('%Y%m%d'))
    for r in json.loads(get(url)).get('results', []):
        recs[r['recall_number']] = {
            'num': r['recall_number'], 'event': r.get('event_id'), 'firm': r.get('recalling_firm', ''),
            'product': r.get('product_description', ''), 'reason': r.get('reason_for_recall', ''),
            'class': r.get('classification', ''), 'dist': r.get('distribution_pattern', ''),
            'code': r.get('code_info', ''), 'date': us_date(r.get('center_classification_date')) or us_date(r.get('report_date')),
            'state': r.get('state', ''), 'agency': 'FDA'}
    try:
        raw = get('https://www.accessdata.fda.gov/scripts/ires/index.cfm?action=export.getDailyExportCSVResult&fromDateVal='
                  + TODAY.strftime('%m/%d/%Y')).decode('utf-8', 'ignore')
        rows = list(csv.reader(io.StringIO(raw)))
        i = next(k for k, r in enumerate(rows) if any('Product Description' in c for c in r))
        h = rows[i]
        for row in rows[i + 1:]:
            r = dict(zip(h, row))
            if r.get('Product Type') != 'Food' or not r.get('Recall Number'):
                continue
            recs.setdefault(r['Recall Number'], {
                'num': r['Recall Number'], 'event': r.get('Event ID'), 'firm': r.get('Recalling Firm', ''),
                'product': r.get('Product Description', ''), 'reason': r.get('Reason for Recall', ''),
                'class': r.get('Classification', ''), 'dist': r.get('Distribution Pattern', ''),
                'code': r.get('Code Info', ''), 'date': us_date(r.get('Center Classification Date')),
                'state': r.get('State/Province', ''), 'agency': 'FDA'})
    except Exception as ex:  # l'export iRES est un bonus : openFDA suffit
        print('iRES indisponible :', ex)
    return [r for r in recs.values() if r['date'] and r['date'] >= since]


FSIS_CACHE = os.path.join(ROOT, 'site-tools', 'data', 'fsis-recalls.json')
BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.fsis.usda.gov/recalls',
}


def text(s):
    if isinstance(s, list):  # l'API renvoie souvent des listes de valeurs
        s = '; '.join(str(x) for x in s if x)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def text_join(s):
    return '; '.join(str(x) for x in s if x) if isinstance(s, list) else (s or '')


# Relais Firebase (us-central1) : le pare-feu du FSIS refuse la France et GitHub
# Actions, mais répond aux serveurs de Google. Voir firebase/functions/src/fsisRecalls.ts.
FSIS_RELAY = 'https://us-central1-eatsok-6d19f.cloudfunctions.net/fsisRecalls'


def fsis_from_api():
    """Rappels USDA FSIS, via le relais Firebase, sinon directement (au cas où le blocage serait levé)."""
    data = None
    errors = []
    for url, headers, unwrap in ((FSIS_RELAY, UA, True), ('https://www.fsis.usda.gov/fsis/api/recall/v/1', BROWSER, False)):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                payload = json.loads(r.read())
            data = payload.get('items', []) if unwrap else payload
            RUN['usda_source'] = 'relais Firebase' if unwrap else 'API FSIS directe'
            break
        except Exception as ex:
            errors.append('%s : %s' % (url.split('/')[2], ex))
    if data is None:
        raise RuntimeError(' | '.join(errors))
    out = []
    for r in data:
        if (r.get('langcode') or 'English') != 'English':
            continue  # chaque rappel existe aussi en espagnol
        try:
            d = dt.date.fromisoformat((r.get('field_recall_date') or '')[:10])
        except ValueError:
            continue
        summary = text(r.get('field_summary'))
        title = text(r.get('field_title'))
        url = r.get('field_recall_url') or ''
        if url.startswith('/'):
            url = 'https://www.fsis.usda.gov' + url
        url = url.replace('http://', 'https://', 1)
        est =sorted(set(re.findall(r'EST\.?\s*(?:No\.\s*)?(?:[MPV]/?){0,3}\s*\d+[A-Z]?', summary)))
        out.append({
            'num': r.get('field_recall_number') or title[:60], 'date': d.isoformat(),
            'firm': text(r.get('field_establishment')), 'title': title,
            'product': text(re.sub(r'</li>', '; ', text_join(r.get('field_product_items')))).strip(' ;') or title,
            'reason': ' '.join(x for x in (text(r.get('field_recall_reason')), title, summary[:600]) if x),
            'reason_short': text(r.get('field_recall_reason')),
            'class': text(r.get('field_recall_classification')), 'type': text(r.get('field_recall_type')),
            'dist': text(r.get('field_states')), 'code': ', '.join(est),
            'url': url or 'https://www.fsis.usda.gov/recalls'})
    return out


def fsis_records():
    """USDA FSIS, avec mémoire locale : une panne de leur côté n'efface pas les rappels déjà connus.

    Leur pare-feu (Akamai) refuse les connexions depuis l'étranger et certains robots ;
    depuis les serveurs GitHub (États-Unis), l'API répond en principe.
    """
    cache = {}
    if os.path.exists(FSIS_CACHE):
        cache = {r['num']: r for r in json.load(io.open(FSIS_CACHE, encoding='utf-8'))}
    status = 'cache'
    try:
        fresh = fsis_from_api()
        for r in fresh:
            cache[r['num']] = r
        status = 'api (%d)' % len(fresh)
    except Exception as ex:
        print('FSIS indisponible, on garde la mémoire locale :', ex)
        status = 'erreur : %s' % ex
    since = TODAY - dt.timedelta(days=US_DAYS)
    keep = [r for r in cache.values() if dt.date.fromisoformat(r['date']) >= since - dt.timedelta(days=30)]
    os.makedirs(os.path.dirname(FSIS_CACHE), exist_ok=True)
    io.open(FSIS_CACHE, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(sorted(keep, key=lambda r: r['date'], reverse=True), ensure_ascii=False, indent=1))
    RUN['usda'] = status
    out = []
    for r in keep:
        d = dt.date.fromisoformat(r['date'])
        if d >= since:
            out.append(dict(r, date=d, event=r['num'], state='', agency='USDA'))
    return out


RUN = {}


def build_us():
    fda = fda_records()
    if len(fda) < 10:
        raise RuntimeError('FDA : seulement %d enregistrements, on ne réécrit pas la page' % len(fda))
    # un événement FDA = plusieurs produits : on regroupe par événement
    events = {}
    for r in fda:
        key = ('FDA', r['event'] or r['num'])
        ev = events.setdefault(key, dict(r, products=[], codes=[], nums=[]))
        ev['products'].append(r['product'])
        ev['codes'].append(r['code'])
        ev['nums'].append(r['num'])
        ev['date'] = max(ev['date'], r['date'])
    usda = fsis_records()
    for r in usda:
        events[('USDA', r['num'])] = dict(r, products=[r['product']], codes=[r['code']], nums=[r['num']])
    RUN['fda'] = '%d produits, %d rappels' % (len(fda), len([k for k in events if k[0] == 'FDA']))
    recs = sorted(events.values(), key=lambda r: (r['date'], r['firm']), reverse=True)
    articles = blog_index(os.path.join(PUBLIC, 'blog'), '/blog/')
    labels = {k: (l, c) for k, l, c in US_CATS}
    counts = {k: 0 for k, _, _ in US_CATS}
    groups, cur_day, cur, itemlist = [], None, [], []
    for r in recs:
        cat = us_cat(r['reason'])
        counts[cat] += 1
        label, cls = labels[cat]
        usda = r['agency'] == 'USDA'
        if usda:
            # le titre FSIS dit déjà tout : « X Recalls Y Due to Z »
            first = clip(r.get('title') or r['products'][0], 140)
            more = 0
        else:
            # titre court : on coupe avant le poids, l'UPC, le distributeur ou les ingrédients
            first = re.split(r';|\s{2,}|[,.]?\s+\b(?:net\s*wt|net\s*weight|upc|distributed\s+by|manufactured\s+(?:by|for)|ingredients|product\s+of|sold\s+in)\b',
                             r['products'][0], flags=re.I)[0].rstrip(' .,:')
            first = clip(first, 110)
            more = len(r['products']) - 1
        firm = re.sub(r'\s+', ' ', r['firm']).strip()
        if usda and not firm:
            m = re.match(r'(.+?)\s+(?:Recalls?|Expands|Issues)(?![a-z])', r.get('title') or '')
            firm = m.group(1) if m and not m.group(1).startswith('FSIS') else ('USDA FSIS' if (r.get('title') or '').startswith('FSIS') else '')
        firm_key = re.sub(r'[,.]|\b(inc|llc|ltd|corp|corporation|co|company)\b', '', firm, flags=re.I).strip()
        names = [firm_key] if firm != 'USDA FSIS' else []
        if usda and len(firm_key.split(' ')[0]) >= 5:
            names.append(firm_key.split(' ')[0])  # « Kayem Foods » → « Kayem »
        art = find_article(articles, names, r['date'])
        link = r.get('url') or 'https://www.accessdata.fda.gov/scripts/ires/index.cfm'
        itemlist.append(('%s — %s' % (first, firm), link if r['agency'] == 'USDA' else 'https://numeline.com/food-recalls'))
        if usda:
            why = re.search(r'\b(?:due to|because of)\s+(.+)$', r.get('title') or '', re.I)
            short = cap(why.group(1)) if why else (r.get('reason_short') or clip(r['reason'], 170))
            meta = ['<strong>Reason:</strong> ' + e(short)]
            if r['product'] and r['product'] != r.get('title'):
                meta.append('<strong>Products:</strong> ' + e(clip(r['product'], 220)))
        else:
            meta = ['<strong>Reason:</strong> ' + e(clip(r['reason'], 170))]
        codes = clip(' · '.join(dict.fromkeys(c for c in r['codes'] if c)), 200)
        if codes:
            meta.append('<strong>%s</strong> ' % ('Establishment:' if usda else 'Codes:') + e(codes))
        if r['dist']:
            meta.append('<strong>Distribution:</strong> ' + e(clip(r['dist'], 150)))
        meta.append('<strong>Recall:</strong> ' + e(', '.join(r['nums'][:3]) + (' +%d' % (len(r['nums']) - 3) if len(r['nums']) > 3 else '')))
        cls_tag = ('<span class="rc-tag">%s</span>' % e(r['class'])) if r['class'] and 'health alert' not in r['class'].lower() else ''
        if usda and 'health alert' in (r.get('type') or '').lower():
            cls_tag += '<span class="rc-tag mid">Public health alert</span>'
        links = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (
            e(link), 'USDA FSIS notice' if r['agency'] == 'USDA' else 'FDA enforcement records')
        if art:
            links += '<a href="%s">Our analysis</a>' % e(art['url'])
        title = first + (' (+%d more product%s)' % (more, 's' if more > 1 else '') if more > 0 else '')
        item = ('        <article class="rc-item" data-cat="%s" data-agency="%s">\n          <div class="rc-tags"><span class="rc-tag %s">%s</span><span class="rc-tag">%s</span>%s</div>\n'
                '          <h3>%s</h3>\n          <div class="rc-brand">%s</div>\n          <p class="rc-meta">%s</p>\n          <div class="rc-links">%s</div>\n        </article>\n') % (
            cat, r['agency'], cls, e(label), r['agency'], cls_tag, e(title), e(firm), '<br />'.join(meta), links)
        if r['date'] != cur_day:
            if cur:
                groups.append((en_date(cur_day), cur))
            cur_day, cur = r['date'], []
        cur.append(item)
    if cur:
        groups.append((en_date(cur_day), cur))
    n = len(recs)
    n_fda = sum(1 for r in recs if r['agency'] == 'FDA')
    n_usda = n - n_fda
    filters = [('all', 'All', n), ('agency:FDA', 'FDA', n_fda)] + ([('agency:USDA', 'USDA (meat, poultry, eggs)', n_usda)] if n_usda else []) \
        + [(k, l, counts[k]) for k, l, _ in US_CATS if counts[k]]
    top = ', '.join('%d for %s' % (counts[k], l) for k, l, _ in US_CATS[:3] if counts[k])
    split = '%d from the FDA and %d from the USDA' % (n_fda, n_usda) if n_usda else '%d from the FDA' % n_fda
    nav = '\n'.join('        ' + x for x in [
        '<a href="/">Home</a>', '<a href="/blog/">Blog</a>',
        '<a href="/food-recalls" aria-current="page">Food recalls</a>',
        '<a href="/contact">Contact</a>', '<a href="/fr/rappels-alimentaires" hreflang="fr">FR</a>'])
    faq = [
        ('What is a food recall?',
         'A food recall removes a product from sale, and from homes, because it may be unsafe: bacteria such as Listeria, Salmonella or E. coli, an undeclared allergen, foreign material, a contaminant such as lead, or a processing problem. The FDA oversees most foods; the USDA Food Safety and Inspection Service (FSIS) oversees meat, poultry and egg products.'),
        ('What do Class I, II and III mean?',
         'Class I is the most serious: a reasonable probability that the product will cause serious health problems or death. Class II may cause temporary or medically reversible health problems. Class III is unlikely to cause adverse health consequences.'),
        ('How do I know if my product is recalled?',
         'Compare the brand, UPC, lot code and best-by date printed on the package with the recall notice. A product is only affected if its codes match. The <a href="/">Numeline app</a> does this for you: scan the lot number and it checks it against official FDA and USDA recalls.'),
        ('What should I do with a recalled food?',
         'Do not eat it. Return it to the store for a refund or throw it away, as the notice says. If you ate it and feel sick, contact a healthcare provider and mention the product.'),
        ('How often is this list updated?',
         'Every day, automatically, from FDA enforcement data and USDA FSIS recall notices. It covers food recalls classified over the last %d days. Our <a href="/blog/">blog</a> explains the most important ones.' % US_DAYS),
    ]
    cta = ('      <div class="cta-app">\n        <h3>Check a product in one scan</h3>\n'
           '        <p>Numeline reads the lot number on your food and checks it against official FDA and USDA recalls. Free on iOS and Android.</p>\n'
           '        <div class="cta-buttons">\n'
           '          <a class="cta-btn" href="https://apps.apple.com/us/app/numeline/id6758400953" target="_blank" rel="noopener"><span><span class="b-sub">Download on the</span><span class="b-main">App Store</span></span></a>\n'
           '          <a class="cta-btn" href="https://play.google.com/store/apps/details?id=com.eatsafe.app" target="_blank" rel="noopener"><span><span class="b-sub">Get it on</span><span class="b-main">Google Play</span></span></a>\n'
           '        </div>\n      </div>\n')
    footer = ('    <footer class="footer">\n      <div>Numeline — Food recall radar</div>\n'
              '      <div><a href="/blog/">More articles</a> · <a href="/privacy-policy">Privacy</a> · <a href="/contact">Contact</a></div>\n    </footer>')
    html_ = page(
        'en', 'https://numeline.com/food-recalls',
        'Food Recalls Today: FDA & USDA Recall List, Updated Daily',
        'Every FDA and USDA food recall from the last %d days: products, companies, lot codes, reasons and states. Updated daily from official data.' % US_DAYS,
        'Current food recalls',
        'Updated <time datetime="%s">%s</time> · %d recalls classified since %s' % (
            TODAY.isoformat(), en_date(TODAY), n, en_date(TODAY - dt.timedelta(days=US_DAYS))),
        'Every <strong>food recall</strong> classified by the <strong>FDA</strong> and the <strong>USDA</strong> over the last %d days: %s, including %s. For each one: the product, the company, the lot codes or establishment number, and where it was sold.' % (US_DAYS, split, top),
        filters, groups, faq,
        'Sources: <a href="https://open.fda.gov/apis/food/enforcement/" target="_blank" rel="noopener">openFDA food enforcement data</a>, the <a href="https://www.accessdata.fda.gov/scripts/ires/index.cfm" target="_blank" rel="noopener">FDA Enforcement Report</a> and <a href="https://www.fsis.usda.gov/recalls" target="_blank" rel="noopener">USDA FSIS recalls</a> (U.S. government works, public domain). FDA enforcement records can appear a few days after a company announces a recall. Numeline is an independent app, not affiliated with any agency; the official notice always prevails.',
        nav, footer, cta,
        [('Home', 'https://numeline.com/'), ('Current food recalls', None)], itemlist)
    return write_if_changed(os.path.join(PUBLIC, 'food-recalls.html'), html_)


def touch_sitemap():
    p = os.path.join(PUBLIC, 'sitemap.xml')
    s = io.open(p, encoding='utf-8').read()
    for loc in ('https://numeline.com/fr/rappels-alimentaires', 'https://numeline.com/food-recalls'):
        entry = '  <url><loc>%s</loc><lastmod>%s</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n' % (loc, TODAY.isoformat())
        if loc + '</loc>' in s:
            s = re.sub(r'  <url><loc>%s</loc>.*?</url>\n' % re.escape(loc), lambda m: entry, s)
        else:
            s = s.replace('</urlset>', entry + '</urlset>')
    io.open(p, 'w', encoding='utf-8', newline='').write(s)


if __name__ == '__main__':
    ok = True
    changed = False
    for name, fn in (('FR', build_fr), ('US', build_us)):
        try:
            changed = fn() or changed
        except Exception as ex:
            ok = False
            print('ERREUR %s :' % name, repr(ex), file=sys.stderr)
    if changed:
        touch_sitemap()
    # rapport du passage, versionné avec la page : permet de voir quelle source a répondu
    # heure incluse : chaque passage laisse une trace visible dans l'historique git
    RUN['date'] = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    os.makedirs(os.path.join(ROOT, 'site-tools', 'data'), exist_ok=True)
    io.open(os.path.join(ROOT, 'site-tools', 'data', 'last-run.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(RUN, ensure_ascii=False, indent=1))
    sys.exit(0 if ok else 1)
