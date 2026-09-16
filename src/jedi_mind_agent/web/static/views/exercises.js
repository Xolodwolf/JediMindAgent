import { h, toggleInSet } from "./dom.js";

const STATUS_LABELS = {
  suggested: "предложено",
  accepted: "принято",
  in_progress: "выполняю",
  completed: "выполнено",
  skipped: "пропущено",
  not_suitable: "не подошло",
  cancelled: "отменено",
};

const ACTION_LABELS = {
  accepted: "Принять",
  in_progress: "Начать",
  completed: "Выполнено",
  skipped: "Пропустить",
  not_suitable: "Не подошло",
  cancelled: "Отменить",
};

export function renderExercises(root, { exercises, busyIds, openIds, closedOpen, onAction, onClosedToggle }) {
  if (!exercises) {
    root.replaceChildren(h("p", { class: "muted" }, "Загрузка…"));
    return;
  }

  // The server sends the allowed transitions; an exercise without any is closed.
  const active = exercises.filter((exercise) => exercise.actions.length > 0);
  const closed = exercises.filter((exercise) => exercise.actions.length === 0);
  const card = (exercise) => exerciseCard(exercise, { busy: busyIds.has(exercise.id), openIds, onAction });

  const nodes = active.length
    ? active.map(card)
    : [h("p", { class: "muted" }, "Пока нет упражнений. Агент предложит их после диагностики.")];

  if (closed.length) {
    nodes.push(
      h(
        "details",
        { class: "closed", open: closedOpen, ontoggle: (event) => onClosedToggle(event.currentTarget.open) },
        h("summary", {}, `Завершённые (${closed.length})`),
        closed.map(card),
      ),
    );
  }

  root.replaceChildren(...nodes);
}

function exerciseCard(exercise, { busy, openIds, onAction }) {
  return h(
    "article",
    { class: `ex ex-${exercise.status}`, "aria-busy": busy ? "true" : null },
    h(
      "details",
      { open: openIds.has(exercise.id), ontoggle: (event) => toggleInSet(openIds, exercise.id, event.currentTarget.open) },
      h("summary", {}, exercise.title),
      h("div", { class: "ex-desc" }, exercise.description),
    ),
    h(
      "div",
      { class: "ex-meta" },
      h("span", { class: `badge badge-${exercise.status}` }, STATUS_LABELS[exercise.status] ?? exercise.status),
      h("span", {}, `ур. ${exercise.level_rank}`),
      exercise.estimated_minutes && h("span", {}, `≈ ${exercise.estimated_minutes} мин`),
    ),
    exercise.actions.length > 0 &&
      h(
        "div",
        { class: "ex-actions" },
        exercise.actions.map((target) =>
          h(
            "button",
            { type: "button", class: `btn-${target}`, disabled: busy, onclick: () => onAction(exercise.id, target) },
            ACTION_LABELS[target] ?? target,
          ),
        ),
      ),
  );
}
