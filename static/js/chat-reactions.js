(function (global) {
  "use strict";

  var QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🔥", "👏", "🎉", "✅", "❌", "⭐", "💯"];

  var activePicker = null;

  function closeQuickPicker() {
    if (activePicker && activePicker.parentNode) {
      activePicker.parentNode.removeChild(activePicker);
    }
    activePicker = null;
  }

  function buildPill(messageId, reaction) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chat-reaction-pill" + (reaction.reacted_by_me ? " is-mine" : "");
    btn.setAttribute("data-message-id", String(messageId));
    btn.setAttribute("data-emoji", reaction.emoji);
    btn.title = "Kliknij, aby przełączyć reakcję";

    var emojiSpan = document.createElement("span");
    emojiSpan.className = "chat-reaction-emoji";
    emojiSpan.textContent = reaction.emoji;

    var countSpan = document.createElement("span");
    countSpan.className = "chat-reaction-count";
    countSpan.textContent = String(reaction.count);

    btn.appendChild(emojiSpan);
    btn.appendChild(countSpan);
    return btn;
  }

  function buildReactionsBar(messageId, reactions) {
    var bar = document.createElement("div");
    bar.className = "chat-reactions d-flex flex-wrap align-items-center gap-1 mt-1";
    bar.setAttribute("data-message-id", String(messageId));

    (reactions || []).forEach(function (r) {
      bar.appendChild(buildPill(messageId, r));
    });

    var addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "chat-reaction-add btn btn-sm btn-outline-secondary";
    addBtn.title = "Dodaj reakcję";
    addBtn.setAttribute("aria-label", "Dodaj reakcję");
    addBtn.textContent = "+";
    bar.appendChild(addBtn);

    return bar;
  }

  function updateChatMessageReactions(scrollEl, messageId, reactions) {
    if (!scrollEl) return;
    var row = scrollEl.querySelector(
      '.chat-message-row[data-message-id="' + String(messageId) + '"]',
    );
    if (!row) return;
    var body = row.querySelector(".chat-message-body");
    if (!body) return;
    var old = body.querySelector(".chat-reactions");
    var bar = buildReactionsBar(messageId, reactions);
    if (old) {
      old.replaceWith(bar);
    } else {
      body.appendChild(bar);
    }
  }

  function showQuickPicker(anchorBtn, messageId, onPick) {
    closeQuickPicker();
    var bar = anchorBtn.closest(".chat-reactions");
    if (!bar) return;

    var panel = document.createElement("div");
    panel.className = "chat-reaction-quick-picker";
    panel.setAttribute("role", "menu");

    QUICK_REACTIONS.forEach(function (emoji) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "chat-reaction-quick-item";
      item.textContent = emoji;
      item.setAttribute("aria-label", "Reakcja " + emoji);
      item.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeQuickPicker();
        onPick(messageId, emoji);
      });
      panel.appendChild(item);
    });

    bar.appendChild(panel);
    activePicker = panel;
  }

  function initChatReactions(options) {
    var scrollEl = options && options.scrollEl;
    var reactionUrl = options && options.reactionUrl;
    var getCsrfToken = options && options.getCsrfToken;
    var onError = options && options.onError;

    if (!scrollEl || typeof reactionUrl !== "function") return;

    function reportError(msg) {
      if (typeof onError === "function") onError(msg);
    }

    function toggleReaction(messageId, emoji) {
      var url = reactionUrl(messageId);
      return fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken ? getCsrfToken() : "",
        },
        body: JSON.stringify({ emoji: emoji }),
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.json().then(function (data) {
            if (!r.ok) {
              throw new Error(data.error || "Nie udało się dodać reakcji.");
            }
            if (data.reactions) {
              updateChatMessageReactions(scrollEl, messageId, data.reactions);
            }
            return data;
          });
        })
        .catch(function (err) {
          reportError(err.message || "Błąd reakcji.");
        });
    }

    scrollEl.addEventListener("click", function (ev) {
      var pill = ev.target.closest(".chat-reaction-pill");
      if (pill) {
        ev.preventDefault();
        var mid = pill.getAttribute("data-message-id");
        var emoji = pill.getAttribute("data-emoji");
        if (mid && emoji) toggleReaction(mid, emoji);
        return;
      }

      var addBtn = ev.target.closest(".chat-reaction-add");
      if (addBtn) {
        ev.preventDefault();
        ev.stopPropagation();
        var row = addBtn.closest(".chat-message-row");
        var messageId = row && row.getAttribute("data-message-id");
        if (!messageId) return;
        if (activePicker && addBtn.closest(".chat-reactions").contains(activePicker)) {
          closeQuickPicker();
          return;
        }
        showQuickPicker(addBtn, messageId, toggleReaction);
      }
    });

    document.addEventListener("click", function (e) {
      if (!activePicker) return;
      if (activePicker.contains(e.target) || e.target.closest(".chat-reaction-add")) return;
      closeQuickPicker();
    });

    return {
      toggle: toggleReaction,
      update: function (messageId, reactions) {
        updateChatMessageReactions(scrollEl, messageId, reactions);
      },
      closePicker: closeQuickPicker,
    };
  }

  global.QUICK_REACTION_EMOJIS = QUICK_REACTIONS;
  global.buildChatReactionsBar = buildReactionsBar;
  global.updateChatMessageReactions = updateChatMessageReactions;
  global.initChatReactions = initChatReactions;
})(window);
