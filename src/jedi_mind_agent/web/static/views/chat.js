import { h, toggleInSet } from "./dom.js";

export function renderChat(root, { messages, pending, thinking, loadError, onRetry, openSources }) {
  const nodes = messages.map((message) => messageView(message, openSources));

  if (pending) {
    nodes.push(h("article", { class: "msg msg-user msg-pending" }, h("div", { class: "msg-body" }, pending)));
  }
  if (thinking) {
    nodes.push(
      h(
        "div",
        { class: "typing", role: "status" },
        h("span", { class: "dot" }),
        h("span", { class: "dot" }),
        h("span", { class: "dot" }),
        h("span", { class: "typing-label" }, "агент думает…"),
      ),
    );
  }

  if (!nodes.length) {
    nodes.push(
      loadError
        ? h(
            "div",
            { class: "chat-empty load-error" },
            h("p", {}, loadError),
            h("button", { type: "button", onclick: onRetry }, "Повторить"),
          )
        : h("p", { class: "chat-empty" }, "Расскажите, как вы себя сейчас чувствуете, — агент начнёт диагностику."),
    );
  }

  root.replaceChildren(...nodes);
}

function messageView(message, openSources) {
  return h(
    "article",
    { class: `msg msg-${message.role}` },
    h("div", { class: "msg-body" }, message.content),
    message.used_fallback && h("p", { class: "msg-warn" }, "LLM недоступен — это заглушка"),
    message.sources.length > 0 &&
      h(
        "details",
        {
          class: "sources",
          open: openSources.has(message.id),
          ontoggle: (event) => toggleInSet(openSources, message.id, event.currentTarget.open),
        },
        h("summary", {}, `Источники (${message.sources.length})`),
        h("ul", {}, message.sources.map((source) => h("li", {}, `${source.source_title}, стр. ${pages(source)}`))),
      ),
  );
}

function pages(source) {
  return source.page_start === source.page_end ? source.page_start : `${source.page_start}–${source.page_end}`;
}
