// Le mur de l'enquêteur · les petites animations du jeu (aucune bibliothèque).

const calme = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// L'horloge : les aiguilles tournent du temps d'avant l'action jusqu'au temps d'après.
function horloge() {
  const h = document.querySelector("[data-horloge]");
  if (!h) return;
  const debut = Number(h.dataset.debut);          // minutes depuis minuit au début de l'enquête
  const avant = Number(h.dataset.avant ?? h.dataset.utilise);
  const apres = Number(h.dataset.utilise);
  const aigM = h.querySelector(".minutes"), aigH = h.querySelector(".heures");
  const poser = (m) => {
    const t = debut + m;
    aigM.style.transform = `rotate(${t * 6}deg)`;
    aigH.style.transform = `rotate(${t * 0.5}deg)`;
  };
  if (calme || avant === apres) { poser(apres); return; }
  aigM.style.transition = aigH.style.transition = "none";
  poser(avant);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    aigM.style.transition = aigH.style.transition = "";
    poser(apres);
  }));
  const jauge = document.querySelector(".jauge-plein");
  if (jauge) {
    const fin = jauge.style.width;
    jauge.style.transition = "none";
    jauge.style.width = jauge.dataset.avant + "%";
    requestAnimationFrame(() => requestAnimationFrame(() => { jauge.style.transition = ""; jauge.style.width = fin; }));
  }
}

// La machine à écrire : le procès-verbal qu'on vient d'obtenir s'écrit lettre par lettre.
function machine() {
  document.querySelectorAll("[data-machine]").forEach((el) => {
    if (calme) return;
    const texte = el.textContent;
    el.textContent = "";
    el.classList.add("curseur");
    let i = 0;
    const pas = () => {
      el.textContent = texte.slice(0, ++i);
      if (i < texte.length) setTimeout(pas, 14 + Math.random() * 22);
      else el.classList.remove("curseur");
    };
    setTimeout(pas, 500);
  });
}

// L'accusation : une confirmation dans la page, l'accusation est définitive.
function accusation() {
  const form = document.querySelector("#form-accuser");
  const dlg = document.querySelector("#confirmer");
  if (!form || !dlg) return;
  form.addEventListener("submit", (e) => {
    if (form.dataset.ok) return;
    e.preventDefault();
    const choix = form.querySelector("input[name=suspect]:checked");
    if (!choix) return;
    dlg.querySelector("[data-nom]").textContent = choix.dataset.nom;
    dlg.showModal();
  });
  dlg.querySelector("[data-annuler]").addEventListener("click", () => dlg.close());
  dlg.querySelector("[data-valider]").addEventListener("click", () => { form.dataset.ok = "1"; form.submit(); });
}

// Le mur : survoler une personne ou une ligne de la fiche fait ressortir ses fils, le reste s'efface.
function murInteractif() {
  const svg = document.querySelector(".liege svg");
  if (!svg) return;
  const eclairer = (test) => {
    svg.classList.add("focus");
    const ids = new Set();
    svg.querySelectorAll(".fil, .etiq").forEach((el) => {
      const ok = test(el.dataset.a, el.dataset.b);
      el.classList.toggle("actif", ok);
      if (ok) { ids.add(el.dataset.a); ids.add(el.dataset.b); }
    });
    svg.querySelectorAll(".pola").forEach((p) => p.classList.toggle("actif", ids.has(p.dataset.id)));
  };
  const eteindre = () => { svg.classList.remove("focus"); svg.querySelectorAll(".actif").forEach((el) => el.classList.remove("actif")); };
  svg.querySelectorAll(".pola").forEach((p) => {
    p.addEventListener("mouseenter", () => eclairer((a, b) => a === p.dataset.id || b === p.dataset.id));
    p.addEventListener("mouseleave", eteindre);
  });
  document.querySelectorAll(".fiche-liens li").forEach((li) => {
    const on = () => { eclairer((a, b) => a === li.dataset.a && b === li.dataset.b); svg.closest(".liege").scrollIntoView({ block: "nearest", behavior: calme ? "auto" : "smooth" }); };
    li.addEventListener("mouseenter", () => eclairer((a, b) => a === li.dataset.a && b === li.dataset.b));
    li.addEventListener("focus", on);
    li.addEventListener("click", on);
    li.addEventListener("mouseleave", eteindre);
    li.addEventListener("blur", eteindre);
  });
}

// Le compte rendu d'action : ses liens emmènent à l'info obtenue, qui s'éclaire ; la croix le range.
function compteRendu() {
  const cr = document.querySelector("[data-compte-rendu]");
  if (!cr) return;
  const fermer = () => cr.classList.add("ferme");
  cr.querySelector("[data-fermer]").addEventListener("click", fermer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermer(); });
  cr.querySelectorAll(".cr-liens a").forEach((a) => a.addEventListener("click", () => {
    const cible = document.querySelector(a.getAttribute("href"));
    if (!cible) return;
    cible.classList.remove("vu"); void cible.offsetWidth; cible.classList.add("vu");
  }));
}

horloge();
murInteractif();
compteRendu();
machine();
accusation();
