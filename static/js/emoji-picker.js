(function (global) {
  "use strict";

  var GROUPS = [
    {
      icon: "😀",
      emojis: [
        "😀", "😃", "😄", "😁", "😆", "😅", "🤣", "😂",
        "🙂", "🙃", "😉", "😊", "😇", "🥰", "😍", "🤩",
        "😘", "😗", "😚", "😙", "🥲", "😋", "😛", "😜",
        "🤪", "😝", "🤑", "🤗", "🤭", "🤫", "🤔", "🤐",
        "😐", "😑", "😶", "😏", "😒", "🙄", "😬", "😌",
        "😔", "😪", "🤤", "😴", "😷", "🤒", "🤕", "🤢",
        "🥵", "🥶", "🥴", "😵", "🤯", "🤠", "🥳", "😎",
        "🥺", "😢", "😭", "😤", "😡", "🤬", "😱", "😨",
      ],
    },
    {
      icon: "👋",
      emojis: [
        "👋", "🤚", "🖐️", "✋", "🖖", "👌", "🤌", "🤏",
        "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉", "👆",
        "👇", "☝️", "👍", "👎", "✊", "👊", "🤛", "🤜",
        "👏", "🙌", "👐", "🤲", "🤝", "🙏", "💪", "🦾",
      ],
    },
    {
      icon: "❤️",
      emojis: [
        "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍",
        "🤎", "💔", "❤️‍🔥", "❤️‍🩹", "💕", "💞", "💓", "💗",
        "💖", "💘", "💝", "💟", "♥️", "💋", "💌", "💐",
        "🌹", "🥀", "🌸", "🌺", "🌻", "🌼", "✨", "⭐",
      ],
    },
    {
      icon: "🐶",
      emojis: [
        "🐶", "🐱", "🐭", "🐹", "🐰", "🦊", "🐻", "🐼",
        "🐨", "🐯", "🦁", "🐮", "🐷", "🐸", "🐵", "🐔",
        "🐧", "🐦", "🐤", "🦆", "🦅", "🦉", "🦇", "🐺",
        "🐴", "🦄", "🐝", "🦋", "🐌", "🐞", "🐢", "🐍",
      ],
    },
    {
      icon: "🍕",
      emojis: [
        "🍎", "🍊", "🍋", "🍌", "🍉", "🍇", "🍓", "🫐",
        "🍕", "🍔", "🍟", "🌭", "🍿", "🧁", "🍰", "🎂",
        "☕", "🍵", "🧃", "🍺", "🍻", "🥂", "🍷", "🥤",
        "🍳", "🥐", "🧀", "🥗", "🍣", "🍜", "🌮", "🍩",
      ],
    },
    {
      icon: "⚽",
      emojis: [
        "⚽", "🏀", "🏈", "⚾", "🎾", "🏐", "🎱", "🏓",
        "🎮", "🕹️", "🎲", "🎯", "🎳", "🎸", "🎹", "🎤",
        "🎧", "🎬", "🎨", "📷", "💻", "📱", "⌨️", "🖥️",
        "🔔", "🔕", "📢", "💡", "🔥", "💯", "✅", "❌",
      ],
    },
  ];

  function resolveEl(target) {
    if (!target) return null;
    if (typeof target === "string") return document.querySelector(target);
    return target;
  }

  function insertAtCursor(input, text) {
    if (!input) return;
    var start = input.selectionStart;
    var end = input.selectionEnd;
    if (start == null) {
      input.value += text;
      input.focus();
      return;
    }
    var val = input.value || "";
    input.value = val.slice(0, start) + text + val.slice(end);
    var pos = start + text.length;
    input.setSelectionRange(pos, pos);
    input.focus();
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function buildGrid(emojis, onPick) {
    var grid = document.createElement("div");
    grid.className = "emoji-picker-grid";
    emojis.forEach(function (emoji) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "emoji-picker-item";
      btn.textContent = emoji;
      btn.setAttribute("aria-label", emoji);
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        onPick(emoji);
      });
      grid.appendChild(btn);
    });
    return grid;
  }

  function initEmojiPicker(options) {
    var input = resolveEl(options && options.input);
    var button = resolveEl(options && options.button);
    if (!input || !button) return null;

    var anchor = button.closest(".emoji-picker-anchor");
    if (!anchor) {
      anchor = document.createElement("div");
      anchor.className = "emoji-picker-anchor";
      button.parentNode.insertBefore(anchor, button);
      anchor.appendChild(button);
    }

    var panel = document.createElement("div");
    panel.className = "emoji-picker-panel";
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Wybierz emoji");

    var tabs = document.createElement("div");
    tabs.className = "emoji-picker-tabs";
    var gridWrap = document.createElement("div");
    gridWrap.className = "emoji-picker-grid-wrap";

    var activeGrid = null;

    function showGroup(index) {
      gridWrap.innerHTML = "";
      activeGrid = buildGrid(GROUPS[index].emojis, function (emoji) {
        insertAtCursor(input, emoji);
        panel.hidden = true;
      });
      gridWrap.appendChild(activeGrid);
      tabs.querySelectorAll(".emoji-picker-tab").forEach(function (tab, i) {
        tab.classList.toggle("is-active", i === index);
      });
    }

    GROUPS.forEach(function (group, index) {
      var tab = document.createElement("button");
      tab.type = "button";
      tab.className = "emoji-picker-tab";
      tab.textContent = group.icon;
      tab.setAttribute("aria-label", "Kategoria emoji");
      tab.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        showGroup(index);
      });
      tabs.appendChild(tab);
    });

    panel.appendChild(tabs);
    panel.appendChild(gridWrap);
    anchor.appendChild(panel);
    showGroup(0);

    function togglePanel(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      panel.hidden = !panel.hidden;
    }

    function closePanel() {
      panel.hidden = true;
    }

    button.addEventListener("click", togglePanel);

    function onDocClick(e) {
      if (panel.hidden) return;
      if (panel.contains(e.target) || button.contains(e.target)) return;
      closePanel();
    }

    document.addEventListener("click", onDocClick);

    return {
      close: closePanel,
      destroy: function () {
        document.removeEventListener("click", onDocClick);
        panel.remove();
      },
    };
  }

  global.initEmojiPicker = initEmojiPicker;
})(window);
