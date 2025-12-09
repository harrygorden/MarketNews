document.addEventListener("DOMContentLoaded", () => {
  // Auto-submit select/date controls when marked.
  document.querySelectorAll("[data-auto-submit]").forEach((el) => {
    el.addEventListener("change", () => {
      if (el.form) {
        el.form.submit();
      }
    });
  });

  // Toggle filters panel on mobile.
  const toggle = document.querySelector("[data-toggle-filters]");
  const panel = document.getElementById("filters-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      panel.classList.toggle("open");
      toggle.setAttribute(
        "aria-expanded",
        toggle.getAttribute("aria-expanded") === "true" ? "false" : "true",
      );
    });
  }
});

