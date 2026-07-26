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
  });

  document.addEventListener("click", (event) => {
    if (openRow && !openRow.contains(event.target)) {
      closeRow(openRow);
    }
  });
})();
