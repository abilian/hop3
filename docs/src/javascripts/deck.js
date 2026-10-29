// Slide decks, shown a slide at a time the way SpeakerDeck does it.
//
// A page asks for one with <div class="deck" data-pdf="…">, holding a plain
// link to the PDF. That link is what a reader without JavaScript gets, and
// what comes back if pdf.js cannot load.
//
// pdf.js comes from jsDelivr, and only on a page that has a deck: every other
// page makes no request for it. The version is pinned because pdf.js has
// moved its entry points between majors.
(function () {
  var PDFJS = "https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/";
  var library;

  function pdfjs() {
    if (!library) {
      library = import(PDFJS + "pdf.min.mjs").then(function (lib) {
        lib.GlobalWorkerOptions.workerSrc = PDFJS + "pdf.worker.min.mjs";
        return lib;
      });
    }
    return library;
  }

  function button(label, text) {
    var b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", label);
    b.title = label;
    b.textContent = text;
    return b;
  }

  function mount(deck) {
    var url = deck.getAttribute("data-pdf");
    var fallback = deck.innerHTML;
    deck.setAttribute("data-ready", "");

    var canvas = document.createElement("canvas");
    var bar = document.createElement("div");
    var prev = button("Previous slide", "‹");
    var next = button("Next slide", "›");
    var count = document.createElement("span");
    var full = button("Full screen", "⛶");
    var download = document.createElement("a");
    bar.className = "deck__bar";
    count.className = "deck__count";
    count.setAttribute("aria-live", "polite");
    download.href = url;
    download.textContent = "PDF";
    download.setAttribute("download", "");
    bar.append(prev, count, next, download, full);
    canvas.setAttribute("role", "img");
    deck.tabIndex = 0;
    deck.replaceChildren(canvas, bar);

    var pdf, page = 1, task, queued = false;

    function render() {
      queued = false;
      pdf.getPage(page).then(function (p) {
        var natural = p.getViewport({ scale: 1 });
        var ratio = natural.height / natural.width;
        var width = deck.clientWidth;
        if (document.fullscreenElement === deck) {
          width = Math.min(width, (window.innerHeight - bar.offsetHeight) / ratio);
        }
        var dpr = window.devicePixelRatio || 1;
        var viewport = p.getViewport({ scale: (width * dpr) / natural.width });
        if (task) task.cancel();
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = width + "px";
        canvas.style.height = width * ratio + "px";
        canvas.setAttribute("aria-label", "Slide " + page + " of " + pdf.numPages);
        count.textContent = page + " / " + pdf.numPages;
        prev.disabled = page === 1;
        next.disabled = page === pdf.numPages;
        task = p.render({ canvas: canvas, viewport: viewport });
        task.promise.catch(function () {}); // a cancelled render rejects
      });
    }

    function schedule() {
      if (pdf && !queued) {
        queued = true;
        requestAnimationFrame(render);
      }
    }

    function go(n) {
      if (!pdf) return;
      n = Math.max(1, Math.min(pdf.numPages, n));
      if (n !== page) {
        page = n;
        schedule();
      }
    }

    prev.addEventListener("click", function () { go(page - 1); });
    next.addEventListener("click", function () { go(page + 1); });
    canvas.addEventListener("click", function (event) {
      var box = canvas.getBoundingClientRect();
      go(event.clientX - box.left < box.width / 3 ? page - 1 : page + 1);
    });
    deck.addEventListener("keydown", function (event) {
      var to = {
        ArrowLeft: page - 1, PageUp: page - 1,
        ArrowRight: page + 1, PageDown: page + 1, " ": page + 1,
        Home: 1, End: pdf ? pdf.numPages : 1,
      }[event.key];
      if (to !== undefined) {
        event.preventDefault();
        go(to);
      }
    });
    full.addEventListener("click", function () {
      if (document.fullscreenElement === deck) document.exitFullscreen();
      else deck.requestFullscreen();
    });
    document.addEventListener("fullscreenchange", schedule);
    new ResizeObserver(schedule).observe(deck);

    pdfjs()
      .then(function (lib) {
        return lib.getDocument({ url: new URL(url, location.href).href }).promise;
      })
      .then(function (doc) {
        pdf = doc;
        schedule();
      })
      .catch(function (error) {
        console.warn("deck: showing a link to " + url + " instead:", error);
        deck.removeAttribute("data-ready");
        deck.innerHTML = fallback;
      });
  }

  function mountAll() {
    document.querySelectorAll(".deck:not([data-ready])").forEach(mount);
  }

  mountAll();
  // navigation.instant swaps pages without a reload, so a deck on a page
  // reached that way is mounted after the swap.
  if (window.document$ && window.document$.subscribe) {
    window.document$.subscribe(mountAll);
  }
})();
