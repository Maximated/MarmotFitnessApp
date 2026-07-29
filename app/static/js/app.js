document.querySelectorAll("form.delete-form, form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.dataset.confirm || "¿Seguro que quieres eliminar esto?";
    if (!confirm(message)) {
      event.preventDefault();
    }
  });
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Idempotent: safe to call on every page load. If a subscription already
// exists, pushManager.subscribe() just returns it -- re-sending it to the
// server is harmless and covers recovering from cleared browser storage.
async function subscribeToPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  try {
    const registration = await navigator.serviceWorker.ready;
    const keyResponse = await fetch("/push/public-key");
    const { key } = await keyResponse.json();
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    await fetch("/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(subscription.toJSON()),
    });
  } catch (err) {
    /* notification permission denied, or push not supported here */
  }
}

if ("Notification" in window && Notification.permission === "granted") {
  subscribeToPush();
}

(function () {
  let openRow = null;

  function closeRow(row) {
    const content = row.querySelector(".swipe-row-content");
    content.style.transform = "translateX(0)";
    row.classList.remove("swipe-open");
    if (openRow === row) openRow = null;
  }

  // Enganchado tanto a las filas presentes al cargar la página como a
  // cualquier fila insertada después por fetch() (el guardado optimista de
  // una serie, por ejemplo) -- de ahí que viva en su propia función en vez
  // de inline en el forEach de abajo.
  function wireSwipeRow(row) {
    const content = row.querySelector(".swipe-row-content");
    const actions = row.querySelector(".swipe-row-actions");
    if (!content || !actions) return;

    let pointerId = null;
    let startX = null;
    let startY = null;
    let baseX = 0;
    let dragging = false;
    let isHorizontal = null;
    let moved = false;

    content.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      if (openRow && openRow !== row) closeRow(openRow);
      pointerId = event.pointerId;
      startX = event.clientX;
      startY = event.clientY;
      baseX = row.classList.contains("swipe-open") ? -actions.offsetWidth : 0;
      dragging = true;
      isHorizontal = null;
      moved = false;
      content.style.transition = "none";
    });

    content.addEventListener("pointermove", (event) => {
      if (!dragging || event.pointerId !== pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (isHorizontal === null && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
        isHorizontal = Math.abs(dx) > Math.abs(dy);
        if (isHorizontal) content.setPointerCapture(pointerId);
      }
      if (!isHorizontal) return;
      moved = true;
      const actionsWidth = actions.offsetWidth;
      const next = Math.max(-actionsWidth, Math.min(0, baseX + dx));
      content.style.transform = `translateX(${next}px)`;
    });

    function finishDrag(event) {
      if (!dragging || event.pointerId !== pointerId) return;
      content.style.transition = "";
      dragging = false;
      if (content.hasPointerCapture(pointerId)) {
        content.releasePointerCapture(pointerId);
      }
      if (!isHorizontal || !moved) return;
      const dx = event.clientX - startX;
      const actionsWidth = actions.offsetWidth;
      const shouldOpen = baseX + dx < -actionsWidth / 2;
      if (shouldOpen) {
        content.style.transform = `translateX(${-actionsWidth}px)`;
        row.classList.add("swipe-open");
        openRow = row;
      } else {
        content.style.transform = "translateX(0)";
        row.classList.remove("swipe-open");
        if (openRow === row) openRow = null;
      }
    }

    content.addEventListener("pointerup", finishDrag);
    content.addEventListener("pointercancel", finishDrag);
  }

  window.wireSwipeRow = wireSwipeRow;
  document.querySelectorAll(".swipe-row").forEach(wireSwipeRow);

  document.addEventListener("click", (event) => {
    if (openRow && !openRow.contains(event.target)) {
      closeRow(openRow);
    }
  });
})();

(function () {
  // position:fixed se calcula contra el viewport de layout, que en iOS
  // Safari NO se encoge cuando aparece el teclado (solo el viewport
  // visual sí) -- sin esto, el panel inferior se queda "flotando" a
  // mitad de pantalla, tapando las casillas de registro, hasta que el
  // teclado se cierra. Se corrige compensando con la diferencia real
  // entre ambos viewports en cada resize/scroll del teclado.
  const nav = document.querySelector(".bottom-nav");
  if (!nav || !window.visualViewport) return;

  function reposition() {
    const vv = window.visualViewport;
    const offsetBottom = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
    nav.style.transform = `translate(-50%, -${offsetBottom}px)`;
  }

  window.visualViewport.addEventListener("resize", reposition);
  window.visualViewport.addEventListener("scroll", reposition);
  reposition();
})();

// Casillas de solo lectura que se editan con prompt() en vez de foco directo
// -- un input/textarea normal hace que el móvil abra teclado y haga zoom a
// la casilla, molesto para escribir algo puntual como el peso o una nota.
// prompt() es un diálogo nativo, no forma parte del layout de la página, así
// que no hay zoom ni scroll raro.
document.querySelectorAll(".prompt-input").forEach((field) => {
  field.addEventListener("click", () => {
    field.blur();
    const label = field.dataset.promptLabel || "Valor";
    const value = prompt(label + ":", field.value);
    if (value === null) return;
    field.value = value;
  });
});
