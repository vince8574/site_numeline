#!/usr/bin/env python3
"""Prévient Bing (et les autres moteurs IndexNow) que des pages ont changé.

  python site-tools/indexnow.py                  → toutes les URL du sitemap
  python site-tools/indexnow.py URL [URL ...]    → seulement ces URL

La clé est le fichier public/<clé>.txt, servi à la racine du site : c'est ce qui
prouve aux moteurs que les notifications viennent bien du propriétaire du domaine.
"""
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = 'numeline.com'


def key():
    for p in glob.glob(os.path.join(ROOT, 'public', '*.txt')):
        k = os.path.basename(p)[:-4]
        if re.fullmatch(r'[0-9a-f]{32}', k) and open(p, encoding='utf-8').read().strip() == k:
            return k
    raise SystemExit('clé IndexNow introuvable dans public/')


def sitemap_urls():
    s = open(os.path.join(ROOT, 'public', 'sitemap.xml'), encoding='utf-8').read()
    return re.findall(r'<loc>(https://numeline\.com[^<]*)</loc>', s)


def main():
    urls = sys.argv[1:] or sitemap_urls()
    k = key()
    body = json.dumps({'host': HOST, 'key': k, 'keyLocation': 'https://%s/%s.txt' % (HOST, k), 'urlList': urls[:10000]}).encode()
    req = urllib.request.Request('https://api.indexnow.org/indexnow', data=body,
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print('IndexNow : HTTP %d, %d URL envoyées' % (r.status, len(urls)))
    except urllib.error.HTTPError as ex:
        # 202 = accepté, 200 = OK ; 422/403 = clé ou URL refusées
        print('IndexNow : HTTP %d %s' % (ex.code, ex.read()[:300]))
        sys.exit(0 if ex.code in (200, 202) else 1)


if __name__ == '__main__':
    main()
