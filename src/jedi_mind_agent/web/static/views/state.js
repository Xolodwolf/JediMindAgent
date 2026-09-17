import { h } from "./dom.js";

export function renderState(root, { state, busy, onRetest }) {
  if (!state) {
    root.replaceChildren(h("p", { class: "muted" }, "Загрузка…"));
    return;
  }

  const known = state.level_rank > 0;
  const nodes = [
    stat("Уровень", h("div", { class: "stat-value" }, known ? `${state.level_rank} · ${state.level_title}` : state.level_title)),
    scaleStat("Мыслетопливо", state.energy_level),
    scaleStat("Фокус", state.focus_level),
    state.main_problem && stat("Главная проблема", h("div", {}, state.main_problem)),
    state.time_limit_minutes && stat("Время на практику", h("div", {}, `${state.time_limit_minutes} мин в день`)),
    h(
      "div",
      { class: "retest" },
      h("button", { type: "button", disabled: busy, onclick: onRetest }, known ? "Пройти тест заново" : "Начать тест заново"),
      h("p", { class: "muted" }, "Уровень определяется тестом в чате."),
    ),
  ];
  root.replaceChildren(...nodes.filter(Boolean));
}

function stat(label, ...values) {
  return h("div", { class: "stat" }, h("div", { class: "stat-label" }, label), ...values);
}

function scaleStat(label, value) {
  if (!value) return stat(label, h("div", { class: "stat-value muted" }, "—"));
  return stat(
    label,
    h("meter", { min: 1, max: 10, low: 4, high: 7, optimum: 10, value }),
    h("div", { class: "stat-value" }, `${value}/10`),
  );
}
