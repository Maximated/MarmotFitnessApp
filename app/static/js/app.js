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
