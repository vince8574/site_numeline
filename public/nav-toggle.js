/**
 * nav-toggle — menu hamburger animé de la barre de navigation.
 *
 * POURQUOI CE FICHIER EXISTE : les styles du hamburger étaient déjà présents
 * (`.nav-toggle`, `.topbar.nav-open .nav`), mais AUCUNE page ne contenait le
 * bouton, et aucun script n'ajoutait la classe `nav-open`. En dessous de 600 px,
 * `.nav` était donc masqué sans aucun moyen de le rouvrir : la navigation était
 * purement et simplement inaccessible sur téléphone — dix liens sur l'accueil.
 *
 * Le bouton est INJECTÉ ici plutôt qu'écrit dans chaque page : il n'existait
 * dans aucun des 51 fichiers HTML, et le dupliquer partout aurait garanti des
 * divergences à la première évolution.
 *
 * Dégradation : la classe `has-toggle`, posée ci-dessous, conditionne le
 * masquage du menu en CSS. Sans JavaScript, elle n'est jamais posée et le menu
 * reste visible — jamais de navigation inatteignable.
 */
(function () {
  'use strict';

  function setup(topbar) {
    if (topbar.querySelector('.nav-toggle')) return;
    var nav = topbar.querySelector('.nav');
    if (!nav) return;

    if (!nav.id) nav.id = 'site-nav';

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nav-toggle';
    btn.setAttribute('aria-label', 'Menu');
    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('aria-controls', nav.id);
    btn.innerHTML = '<span></span><span></span><span></span>';

    // Après le menu dans le DOM : en mobile le menu passe en `order: 5` et
    // occupe toute la largeur sous la barre, le bouton reste donc en haut à
    // droite sans qu'on ait à réordonner quoi que ce soit.
    topbar.appendChild(btn);
    // `has-toggle` n'est PAS posée ici : c'est measure(), plus bas, qui décide
    // si ce menu a besoin d'être replié.

    function setOpen(open) {
      topbar.classList.toggle('nav-open', open);
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!topbar.classList.contains('nav-open'));
    });

    // Refermer après le choix d'un lien : sur une ancre de la même page, la
    // navigation ne recharge rien et le menu resterait ouvert par-dessus la
    // section visée.
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a')) setOpen(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && topbar.classList.contains('nav-open')) {
        setOpen(false);
        btn.focus();
      }
    });

    document.addEventListener('click', function (e) {
      if (!topbar.contains(e.target)) setOpen(false);
    });

    /**
     * Le hamburger s'active quand le menu NE TIENT PAS, pas à une largeur
     * arbitraire. Un seuil fixe ne pouvait pas convenir aux deux barres du
     * site : l'accueil porte dix liens plus deux badges, qui débordent même
     * en 1120 px — la largeur maximale du conteneur — tandis qu'un article
     * n'en a que trois, qu'il serait absurde de cacher derrière un bouton.
     *
     * On mesure donc le retour à la ligne réel. La mesure se fait menu
     * déplié : on retire les classes le temps de lire les positions, puis on
     * les repose dans la même tâche, donc sans affichage intermédiaire.
     */
    function navWraps() {
      var kids = nav.children;
      if (kids.length < 2) return false;
      var top = kids[0].offsetTop;
      for (var i = 1; i < kids.length; i++) {
        if (Math.abs(kids[i].offsetTop - top) > 2) return true;
      }
      return topbar.scrollWidth > topbar.clientWidth + 1;
    }

    var applied = null;

    function measure() {
      // La barre est fixe (sticky) : les ancres doivent s'arrêter sous elle,
      // à sa hauteur réelle (une ligne, deux lignes, menu replié ou non).
      if (!topbar.classList.contains('nav-open')) {
        document.documentElement.style.scrollPaddingTop = (topbar.offsetHeight + 12) + 'px';
      }
      // Sous 600 px, toujours replier : sur un téléphone, un menu déroulant
      // vaut mieux qu'une liste qui pousse le contenu vers le bas, même
      // lorsqu'elle tient techniquement sur une ligne.
      var needed = window.innerWidth <= 600;

      if (!needed) {
        var wasToggle = topbar.classList.contains('has-toggle');
        var wasOpen = topbar.classList.contains('nav-open');
        topbar.classList.remove('has-toggle', 'nav-open');
        needed = navWraps();
        if (wasToggle) topbar.classList.add('has-toggle');
        if (wasOpen) topbar.classList.add('nav-open');
      }

      // Garde-fou anti-boucle : replier le menu change la taille de la barre,
      // ce que l'observateur ci-dessous détecte. Sans cette sortie, chaque
      // décision en déclencherait une autre. On n'écrit donc dans le DOM que
      // si le verdict a réellement changé.
      if (needed === applied) return;
      applied = needed;

      topbar.classList.toggle('has-toggle', needed);
      btn.hidden = !needed;
      if (!needed) setOpen(false);
    }

    var timer;
    function remeasure() {
      clearTimeout(timer);
      timer = setTimeout(measure, 100);
    }

    window.addEventListener('resize', remeasure);
    // La mise en page n'est pas définitive au DOMContentLoaded : les polices
    // web arrivent après et élargissent les liens, les images de la barre
    // aussi. Mesuré une seule fois à ce moment, le menu tenait encore sur une
    // ligne et le hamburger restait masqué alors qu'il débordait ensuite —
    // c'était le défaut constaté en production.
    window.addEventListener('load', remeasure);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(remeasure).catch(function () {});
    }
    // Filet le plus sûr : on observe la barre elle-même. Toute variation de
    // taille, quelle qu'en soit la cause, relance la décision.
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(remeasure);
      ro.observe(topbar);
      if (topbar.parentNode) ro.observe(topbar.parentNode);
    }
    measure();
  }

  function init() {
    var bars = document.querySelectorAll('.topbar');
    for (var i = 0; i < bars.length; i++) setup(bars[i]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
