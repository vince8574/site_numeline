// Formulaires du site (contact, suppression de compte).
// Envoi en JSON vers la fonction Firebase submitWebForm, qui vérifie la demande,
// la transmet à l'équipe et envoie un accusé de réception.
(function () {
  var ENDPOINT = 'https://europe-west1-eatsok-6d19f.cloudfunctions.net/submitWebForm';
  // Clé PUBLIQUE du widget Cloudflare Turnstile (Cloudflare → Turnstile → numeline.com).
  // La clé secrète, elle, est stockée côté serveur (secret Firebase TURNSTILE_SECRET_KEY).
  var TURNSTILE_SITE_KEY = '0x4AAAAAAFZYO8Vwn4IcKGte';
  var started = Date.now();
  var widgets = [];

  // Tant que la clé n'est pas configurée, le formulaire est remplacé par l'adresse
  // e-mail : mieux vaut un repli clair qu'un captcha en erreur.
  if (TURNSTILE_SITE_KEY.indexOf('__') === 0) {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-web-form]'), function (form) {
      var en = form.getAttribute('data-lang') === 'en';
      var kind = form.getAttribute('data-web-form');
      var note = document.createElement('div');
      note.className = 'note';
      note.innerHTML = en
        ? '<p>Our form is being set up. In the meantime, email <a href="mailto:contact@numeline.com' + (kind === 'deletion' ? '?subject=Account%20deletion%20request' : '') + '">contact@numeline.com</a>' + (kind === 'deletion' ? ' from the address you use in the app.' : '.') + '</p>'
        : '<p>Notre formulaire est en cours de mise en service. En attendant, écrivez à <a href="mailto:contact@numeline.com' + (kind === 'deletion' ? '?subject=Demande%20de%20suppression%20de%20compte' : '') + '">contact@numeline.com</a>' + (kind === 'deletion' ? ' depuis l’adresse utilisée dans l’application.' : '.') + '</p>';
      form.parentNode.replaceChild(note, form);
    });
    return;
  }

  // Affichage du captcha dans chaque formulaire, une fois le script Cloudflare chargé.
  window.numelineTurnstileReady = function () {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-web-form] .wf-captcha'), function (box) {
      var lang = box.closest('form').getAttribute('data-lang') === 'en' ? 'en' : 'fr';
      widgets.push(window.turnstile.render(box, { sitekey: TURNSTILE_SITE_KEY, language: lang, theme: 'auto' }));
    });
  };
  var cf = document.createElement('script');
  cf.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=numelineTurnstileReady';
  cf.async = true;
  cf.defer = true;
  document.head.appendChild(cf);

  var MSG = {
    fr: {
      sending: 'Envoi en cours…',
      ok: {
        contact: 'Merci, votre message est bien envoyé. Un accusé de réception vient de partir vers votre adresse e-mail.',
        deletion: 'Votre demande est enregistrée. Un accusé de réception vient de partir vers votre adresse e-mail ; la suppression sera effectuée sous 30 jours au plus.'
      },
      err: {
        email: 'Adresse e-mail invalide.',
        captcha: 'La vérification anti-robot a échoué ou n’est pas terminée. Patientez un instant, puis réessayez.',
        consent: 'Merci de cocher la case de confirmation.',
        message: 'Votre message est trop court.',
        rate: 'Trop d\'envois depuis votre connexion. Réessayez dans une heure, ou écrivez à contact@numeline.com.',
        send: 'L\'envoi a échoué. Réessayez, ou écrivez directement à contact@numeline.com.'
      }
    },
    en: {
      sending: 'Sending…',
      ok: {
        contact: 'Thank you, your message has been sent. A confirmation is on its way to your email address.',
        deletion: 'Your request has been recorded. A confirmation is on its way to your email address; the deletion will be completed within 30 days at most.'
      },
      err: {
        email: 'Invalid email address.',
        captcha: 'The anti-bot check failed or is not finished yet. Wait a moment, then try again.',
        consent: 'Please tick the confirmation box.',
        message: 'Your message is too short.',
        rate: 'Too many submissions from your connection. Try again in an hour, or email contact@numeline.com.',
        send: 'Sending failed. Please try again, or email contact@numeline.com directly.'
      }
    }
  };

  var forms = document.querySelectorAll('form[data-web-form]');
  Array.prototype.forEach.call(forms, function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var lang = form.getAttribute('data-lang') === 'en' ? 'en' : 'fr';
      var kind = form.getAttribute('data-web-form');
      var T = MSG[lang];
      var status = form.querySelector('.wf-status');
      var button = form.querySelector('button[type="submit"]');
      if (!form.checkValidity()) { form.reportValidity(); return; }

      var get = function (n) { var el = form.elements[n]; return el ? el.value : ''; };
      var tokenEl = form.querySelector('[name="cf-turnstile-response"]');
      var token = tokenEl ? tokenEl.value : '';
      if (!token) {
        status.className = 'wf-status err';
        status.textContent = T.err.captcha;
        return;
      }
      var consentEl = form.elements.consent;
      var payload = {
        form: kind,
        lang: lang,
        name: get('name'),
        email: get('email'),
        subject: get('subject'),
        message: get('message'),
        consent: !!(consentEl && consentEl.checked),
        website: get('website'),
        turnstile: token,
        elapsed: Date.now() - started
      };

      button.disabled = true;
      status.className = 'wf-status';
      status.textContent = T.sending;

      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (res.ok && res.j.ok) {
            status.className = 'wf-status ok';
            status.textContent = T.ok[kind];
            form.reset();
            Array.prototype.forEach.call(form.querySelectorAll('input, select, textarea, button'), function (el) { el.disabled = true; });
          } else {
            status.className = 'wf-status err';
            status.textContent = T.err[res.j.error] || T.err.send;
            button.disabled = false;
            if (window.turnstile) widgets.forEach(function (w) { window.turnstile.reset(w); });
          }
          status.focus();
        })
        .catch(function () {
          status.className = 'wf-status err';
          status.textContent = T.err.send;
          button.disabled = false;
        });
    });
  });
})();
