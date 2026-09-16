import { formatDate, h } from "./dom.js";

const READINESS_LABELS = {
  ready: "готов",
  partially_ready: "частично готов",
  not_ready: "пока не готов",
};

export function renderState(root, { state, lastCheck, busy, onReadiness }) {
  if (!state) {
    root.replaceChildren(h("p", { class: "muted" }, "Загрузка…"));
    return;
  }

  const level = state.level_rank ? `${state.level_rank} · ${state.level_title}` : state.level_title;
  const nodes = [
    stat("Уровень", h("div", { class: "stat-value" }, level)),
    scaleStat("Мыслетопливо", state.energy_level),
    scaleStat("Фокус", state.focus_level),
    state.main_problem && stat("Главная проблема", h("div", {}, state.main_problem)),
    state.time_limit_minutes && stat("Время на практику", h("div", {}, `${state.time_limit_minutes} мин в день`)),
    h(
      "div",
      { class: "readiness" },
      h("button", { type: "button", disabled: busy, onclick: onReadiness }, "Проверить готовность"),
      lastCheck &&
        h(
          "p",
          { class: "muted" },
          `Последняя проверка ${formatDate(lastCheck.created_at)}: `,
          h("strong", { class: `result-${lastCheck.result}` }, READINESS_LABELS[lastCheck.result] ?? lastCheck.result),
        ),
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
