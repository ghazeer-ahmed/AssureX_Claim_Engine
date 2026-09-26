document.addEventListener("DOMContentLoaded", () => {

  document.querySelectorAll("form[data-confirm]").forEach(form => {

    form.addEventListener("submit", event => {

      if (!window.confirm(form.dataset.confirm)) event.preventDefault();

    });

  });

  const product = document.querySelector("#product_id");

  const warranty = document.querySelector("#warranty_id");

  if (product && warranty) {

    const update = () => {

      for (const option of warranty.options) {

        if (!option.value) continue;

        const match = option.dataset.product === product.value;

        option.hidden = !match;

        option.disabled = !match;

      }

      if (warranty.selectedOptions[0]?.disabled) warranty.value = "";

    };

    product.addEventListener("change", update);

    update();

  }

  const file = document.querySelector("#document");

  if (file) file.addEventListener("change", () => {

    const selected = file.files[0];

    file.setCustomValidity(selected && selected.size > 10 * 1024 * 1024 ? "Maximum file size is 10 MB." : "");

    const hint = document.querySelector("[data-file-hint]");

    if (hint && selected) hint.textContent = `${selected.name} · ${(selected.size / 1024 / 1024).toFixed(2)} MB`;

  });

  document.querySelectorAll("[data-list-search]").forEach(input => {

    input.addEventListener("input", () => {

      const query = input.value.toLowerCase().trim();

      document.querySelectorAll("[data-search-item]").forEach(item => {

        item.hidden = !item.textContent.toLowerCase().includes(query);

      });

    });

  });

});

