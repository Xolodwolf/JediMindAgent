import { h, toggleInSet } from "./dom.js";

const ACTION_LABELS = {
  suitable: "Подходит",
  not_suitable: "Не подходит",
};

const SECTIONS = [
  { status: "suggested", title: "Новые" },
  { status: "suitable", title: "Подходят" },
  { status: "not_suitable", title: "Не подходят" },
];

export function renderExercises(root, props) {
  const { exercises, openSections, onSectionToggle } = props;
  if (!exercises) {
    root.replaceChildren(h("p", { class: "muted" }, "Загрузка…"));
    return;
  }
  if (!exercises.length) {
    root.replaceChildren(h("p", { class: "muted" }, "Пока нет упражнений. Агент предложит их после диагностики."));
    return;
  }

  const nodes = SECTIONS.map((section) => {
    const items = exercises.filter((exercise) => exercise.status === section.status);
    if (!items.length) return null;
    return h(
      "details",
      {
        class: `ex-section ex-section-${section.status}`,
        open: openSections.has(section.status),
        ontoggle: (event) => onSectionToggle(section.status, event.currentTarget.open),
      },
      h("summary", {}, `${section.title} (${items.length})`),
      items.map((exercise) => exerciseCard(exercise, props)),
    );
  });

  root.replaceChildren(...nodes.filter(Boolean));
}

function exerciseCard(exercise, { busyIds, openIds, confirmDeleteId, onAction, onDelete }) {
  const busy = busyIds.has(exercise.id);
  const confirming = confirmDeleteId === exercise.id;

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
      h("span", {}, `ур. ${exercise.level_rank}`),
      exercise.estimated_minutes && h("span", {}, `≈ ${exercise.estimated_minutes} мин`),
    ),
    h(
      "div",
      { class: "ex-actions" },
      // The server sends the allowed evaluations; the UI only renders them.
      exercise.actions.map((target) =>
        h(
          "button",
          { type: "button", class: `btn-${target}`, disabled: busy, onclick: () => onAction(exercise.id, target) },
          ACTION_LABELS[target] ?? target,
        ),
      ),
      h(
        "button",
        {
          type: "button",
          class: confirming ? "btn-delete confirm" : "btn-delete",
          disabled: busy,
          onclick: () => onDelete(exercise.id),
        },
        confirming ? "Точно удалить?" : "Удалить",
      ),
    ),
  );
}
