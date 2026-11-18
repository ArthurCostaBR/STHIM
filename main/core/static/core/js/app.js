(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const normalize = (text) =>
    (text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const debounce = (fn, wait) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  };

  // ---------- Mensagens, senha e envio automático ----------
  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-dismiss]");
    if (close) close.closest(".message")?.remove();

    const toggle = event.target.closest("[data-toggle-password]");
    if (toggle) {
      const input = toggle.closest(".password-field").querySelector("input");
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      toggle.textContent = reveal ? "Ocultar" : "Mostrar";
      toggle.setAttribute("aria-pressed", String(reveal));
    }
  });

  document.addEventListener("change", (event) => {
    const field = event.target.closest("[data-autosubmit]");
    if (field && field.value && field.form) field.form.requestSubmit();
  });

  // ---------- Cadastro em etapas ----------
  function setupSteps() {
    const form = $("[data-steps]");
    if (!form) return;
    const steps = $$("[data-step]", form);
    let current = 0;

    const notes = $$("[data-step-note]");

    const show = (index, focus) => {
      current = index;
      steps.forEach((step, i) => { step.hidden = i !== index; });
      notes.forEach((note) => { note.hidden = Number(note.dataset.stepNote) !== index; });
      if (focus) $("input, select", steps[index])?.focus();
    };

    // Começa na primeira etapa com erro vindo do servidor
    const withError = steps.findIndex((step) => step.querySelector(".has-error"));
    show(withError >= 0 ? withError : 0, false);

    form.addEventListener("click", (event) => {
      if (event.target.closest("[data-step-prev]")) {
        show(current - 1, true);
      } else if (event.target.closest("[data-step-next]")) {
        const invalid = $$("input, select", steps[current]).find((f) => !f.checkValidity());
        if (invalid) invalid.reportValidity();
        else show(current + 1, true);
      }
    });

    // Enter numa etapa intermediária avança em vez de enviar
    form.addEventListener("submit", (event) => {
      if (current < steps.length - 1) {
        event.preventDefault();
        $("[data-step-next]", steps[current])?.click();
      }
    });
  }

  // ---------- Seletor de pacientes com busca ----------
  function initPicker(select) {
    const url = select.dataset.searchUrl;
    const multiple = select.multiple;
    select.required = false; // o servidor valida; um select oculto e obrigatório travaria o envio
    select.hidden = true;

    const wrapper = document.createElement("div");
    wrapper.className = "picker";

    const input = document.createElement("input");
    input.type = "search";
    input.id = `${select.id}_search`;
    input.placeholder = select.dataset.placeholder || "Pesquisar por nome, CPF ou SUS";
    input.autocomplete = "off";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", `${select.id}_results`);

    const results = document.createElement("ul");
    results.id = `${select.id}_results`;
    results.className = "picker__results";
    results.setAttribute("role", "listbox");
    results.hidden = true;

    const chips = document.createElement("ul");
    chips.className = "picker__chips";

    wrapper.append(input, results, chips);
    select.after(wrapper);

    const label = $(`label[for="${select.id}"]`);
    if (label) label.htmlFor = input.id;

    let sequence = 0;
    let active = -1;

    const options = () => $$(".picker__option", results);
    const closeResults = () => {
      results.hidden = true;
      results.replaceChildren();
      input.setAttribute("aria-expanded", "false");
      active = -1;
    };

    const renderChips = () => {
      chips.replaceChildren();
      Array.from(select.options)
        .filter((option) => option.selected && option.value)
        .forEach((option) => {
          const item = document.createElement("li");
          item.className = "chip";
          const text = document.createElement("span");
          text.textContent = option.textContent;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.textContent = "✕";
          remove.setAttribute("aria-label", `Remover ${option.textContent}`);
          remove.addEventListener("click", () => {
            option.selected = false;
            renderChips();
          });
          item.append(text, remove);
          chips.append(item);
        });
    };

    const choose = (item) => {
      let option = Array.from(select.options).find((o) => o.value === String(item.id));
      if (!option) {
        option = new Option(item.label, item.id);
        select.add(option);
      }
      if (!multiple) Array.from(select.options).forEach((o) => { o.selected = false; });
      option.selected = true;
      renderChips();
      input.value = "";
      closeResults();
    };

    const setActive = (index) => {
      options().forEach((el, i) => el.setAttribute("aria-selected", String(i === index)));
      active = index;
    };

    const showResults = (items, emptyText = "Nenhum paciente encontrado.") => {
      results.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("li");
        empty.className = "picker__empty";
        empty.textContent = emptyText;
        results.append(empty);
      }
      items.forEach((item) => {
        const li = document.createElement("li");
        li.className = "picker__option";
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.textContent = item.label;
        li._item = item;
        li.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(item);
        });
        results.append(li);
      });
      results.hidden = false;
      input.setAttribute("aria-expanded", "true");
      active = -1;
    };

    const search = debounce(async () => {
      const term = input.value.trim();
      const current = ++sequence;
      if (term.length < 2) { closeResults(); return; }
      try {
        const endpoint = new URL(url, window.location.origin);
        endpoint.searchParams.set("q", term);
        const response = await fetch(endpoint, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (current === sequence) showResults(data.results);
      } catch (error) {
        if (current === sequence) showResults([], "Não foi possível buscar agora.");
      }
    }, 250);

    input.addEventListener("input", search);
    input.addEventListener("blur", closeResults);
    input.addEventListener("keydown", (event) => {
      const items = options();
      if (event.key === "ArrowDown" && items.length) {
        event.preventDefault();
        setActive((active + 1) % items.length);
      } else if (event.key === "ArrowUp" && items.length) {
        event.preventDefault();
        setActive((active - 1 + items.length) % items.length);
      } else if (event.key === "Enter") {
        event.preventDefault(); // Enter na busca não envia o formulário
        const target = items[active >= 0 ? active : 0];
        if (target) choose(target._item);
      } else if (event.key === "Escape") {
        closeResults();
      }
    });

    renderChips();
  }

  // ---------- Contador da seleção de pacientes da rota ----------
  function setupSelectionCounter() {
    const counter = $("[data-selection-counter]");
    if (!counter) return;
    const list = $("[data-selection-list]");
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

    const update = () => {
      let appointments = Number(counter.dataset.baseAppointments || 0);
      let people = Number(counter.dataset.basePeople || 0);
      $$("input[name='appointments']:checked", list || document).forEach((box) => {
        appointments += 1;
        people += Number(box.closest("[data-people]").dataset.people);
      });
      counter.textContent =
        `${plural(appointments, "agendamento selecionado", "agendamentos selecionados")} | ` +
        `${plural(people, "pessoa", "pessoas")} (com acompanhantes)`;
    };

    list?.addEventListener("change", update);
    update();
  }

  setupSteps();
  $$("select[data-picker]").forEach(initPicker);
  setupSelectionCounter();
})();