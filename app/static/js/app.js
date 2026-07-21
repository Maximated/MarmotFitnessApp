document.querySelectorAll("form.delete-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!confirm("¿Seguro que quieres eliminar esta serie?")) {
      event.preventDefault();
    }
  });
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}
