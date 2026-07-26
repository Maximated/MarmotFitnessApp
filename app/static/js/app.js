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

(function () {
  let openRow = null;

  function closeRow(row) {
    const content = row.querySelector(".swipe-row-content");
    content.style.transform = "translateX(0)";
    row.classList.remove("swipe-open");
    if (openRow === row) openRow = null;
  }

  document.querySelectorAll(".swipe-row").forEach((row) => {
    const content = row.querySelector(".swipe-row-content");
    const actions = row.querySelector(".swipe-row-actions");
    if (!content || !actions) return;

    let startX = null;
    let startY = null;
    let baseX = 0;
    let dragging = false;
    let isHorizontal = null;

    content.addEventListener("touchstart", (event) => {
      if (openRow && openRow !== row) closeRow(openRow);
      startX = event.touches[0].clientX;
      startY = event.touches[0].clientY;
      baseX = row.classList.contains("swipe-open") ? -actions.offsetWidth : 0;
      dragging = true;
      isHorizontal = null;
      content.style.transition = "none";
    }, { passive: true });

    content.addEventListener("touchmove", (event) => {
      if (!dragging) return;
      const dx = event.touches[0].clientX - startX;
      const dy = event.touches[0].clientY - startY;
      if (isHorizontal === null) {
        isHorizontal = Math.abs(dx) > Math.abs(dy);
      }
      if (!isHorizontal) return;
      const actionsWidth = actions.offsetWidth;
      const next = Math.max(-actionsWidth, Math.min(0, baseX + dx));
      content.style.transform = `translateX(${next}px)`;
    }, { passive: true });

    content.addEventListener("touchend", (event) => {
      content.style.transition = "";
      if (!dragging || !isHorizontal) {
        dragging = false;
        return;
      }
      dragging = false;
      const dx = event.changedTouches[0].clientX - startX;
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
    });
  });

  document.addEventListener("click", (event) => {
    if (openRow && !openRow.contains(event.target)) {
      closeRow(openRow);
    }
  });
})();
