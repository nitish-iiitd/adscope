// Client-side validation + loading state for the campaign form.
// The server re-validates everything; this is only for immediate feedback.
(function () {
  "use strict";

  const form = document.getElementById("campaign-form");
  if (!form) return;

  const submitBtn = document.getElementById("submit-btn");
  const loading = document.getElementById("loading-state");

  form.addEventListener("submit", function (event) {
    const briefing = form.querySelector("#briefing");
    let valid = form.checkValidity();

    if (briefing && briefing.value.trim().length < 20) {
      briefing.setCustomValidity("Please provide a briefing of at least 20 characters.");
      valid = false;
    } else if (briefing) {
      briefing.setCustomValidity("");
    }

    if (!valid) {
      event.preventDefault();
      event.stopPropagation();
      form.classList.add("was-validated");
      form.reportValidity();
      return;
    }

    // Providers are queried during this request, so show progress and block resubmits.
    submitBtn.disabled = true;
    submitBtn.innerHTML =
      '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Analysing...';
    if (loading) loading.classList.remove("d-none");
  });

  const briefingField = document.getElementById("briefing");
  if (briefingField) {
    briefingField.addEventListener("input", function () {
      briefingField.setCustomValidity("");
    });
  }
})();
