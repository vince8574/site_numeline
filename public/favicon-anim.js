/* Favicon animé Numeline : le logo (main + cœur-pomme) « respire » façon
   battement de cœur. Rendu via canvas → data URL (les GIF animés en favicon
   ne sont plus supportés par Chrome/Safari). Léger, throttlé ~18 fps, en pause
   quand l'onglet est caché, et désactivé si l'utilisateur préfère moins
   d'animations. Se dégrade silencieusement : le favicon statique reste. */
(function () {
  try {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!document.head || !window.requestAnimationFrame) return;

    var SIZE = 64;
    var canvas = document.createElement('canvas');
    canvas.width = canvas.height = SIZE;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;

    var img = new Image();
    var bg = '#2f3d2b';        // repli ; remplacé par la vraie couleur de fond
    var t = 0, last = 0, running = false, started = false;

    // Courbe de battement : deux « thumps » rapprochés puis léger repos.
    function beat(p) {
      function bump(x, c, w) { return Math.exp(-Math.pow((x - c) / w, 2)); }
      return bump(p, 0.14, 0.06) + 0.6 * bump(p, 0.30, 0.06);
    }

    // On REMPLACE le <link rel="icon"> à chaque frame : certains navigateurs ne
    // repeignent pas le favicon sur un simple changement de href, mais le font
    // sur un nouveau nœud. DOM négligeable (petit élément, ~20 fps).
    function setIcon(href) {
      var olds = document.querySelectorAll('link[rel~="icon"]');
      for (var i = 0; i < olds.length; i++) olds[i].parentNode.removeChild(olds[i]);
      var l = document.createElement('link');
      l.rel = 'icon';
      l.type = 'image/png';
      l.setAttribute('data-anim', '1');
      l.href = href;
      document.head.appendChild(l);
    }

    function draw(ts) {
      if (document.hidden) { running = false; return; }
      running = true;
      if (ts - last >= 50) {           // ~20 fps
        last = ts;
        t = (t + 0.045) % 1;           // cycle ~1,1 s : battements réguliers
        var s = 0.78 + 0.20 * beat(t); // échelle 0.78 → ~0.98
        var d = SIZE * s, o = (SIZE - d) / 2;
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, SIZE, SIZE);
        ctx.drawImage(img, o, o, d, d);
        setIcon(canvas.toDataURL('image/png'));
      }
      window.requestAnimationFrame(draw);
    }

    function start() {
      if (running || !img.complete || !img.naturalWidth) return;
      if (!started) {
        started = true;
        // Couleur de fond = pixel du coin du logo (fond vert plein).
        try {
          ctx.drawImage(img, 0, 0, SIZE, SIZE);
          var px = ctx.getImageData(1, 1, 1, 1).data;
          bg = 'rgb(' + px[0] + ',' + px[1] + ',' + px[2] + ')';
        } catch (e) { /* lecture impossible : on garde le repli */ }
      }
      window.requestAnimationFrame(draw);
    }

    img.onload = start;
    img.src = '/icon.png';
    if (img.complete) start();
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) start();
    });
  } catch (e) { /* pas d'animation → favicon statique */ }
})();

/* Le menu hamburger vivait ICI. Il a été déplacé dans /nav-toggle.js, qui gère
   en plus la décision d'affichage (le menu ne se replie que s'il ne tient pas),
   les attributs ARIA complets, la fermeture par Échap et par clic extérieur.
   Les deux ne pouvaient pas coexister : ce fichier étant chargé en premier, il
   injectait son bouton, et nav-toggle.js — qui abandonne si un bouton existe
   déjà — ne s'exécutait jamais. Symptôme observé : bouton présent, mais aucun
   effet au clic. Ne pas réintroduire de hamburger ici. */
