/**
 * Globalny status online: WebSocket /ws/presence/ + aktualizacja kropek w UI.
 */
(function (global) {
  "use strict";

  function updateUserPresenceDot(userId, online) {
    var id = String(userId);
    document
      .querySelectorAll('.user-avatar-wrap[data-user-id="' + id + '"]')
      .forEach(function (wrap) {
        var dot = wrap.querySelector(".user-status-dot");
        if (!dot) return;
        dot.classList.toggle("status-online", !!online);
        dot.classList.toggle("status-offline", !online);
        dot.title = online ? "Online" : "Offline";
      });

    document.querySelectorAll('[data-presence-user-id="' + id + '"]').forEach(function (block) {
      var inline = block.querySelector(".user-status-inline");
      if (inline) {
        inline.classList.toggle("status-online", !!online);
        inline.classList.toggle("status-offline", !online);
      }
      var label = block.querySelector(".presence-label-text");
      if (label) {
        label.textContent = online ? "Online" : "Offline";
      }
    });
  }

  function initSitePresence(config) {
    var userId = config && config.userId;
    if (!userId) return;

    var proto = global.location.protocol === "https:" ? "wss:" : "ws:";
    var wsUrl = proto + "//" + global.location.host + "/ws/presence/";
    var socket = null;
    var closed = false;
    var reconnectDelay = 2500;

    function connect() {
      if (closed) return;
      socket = new WebSocket(wsUrl);

      socket.onopen = function () {
        updateUserPresenceDot(userId, true);
      };

      socket.onmessage = function (ev) {
        try {
          var data = JSON.parse(ev.data);
          if (data.type === "presence_update" && data.user_id != null) {
            updateUserPresenceDot(data.user_id, !!data.online);
          }
        } catch (e) {
          /* ignore */
        }
      };

      socket.onclose = function () {
        if (closed) return;
        setTimeout(connect, reconnectDelay);
      };
    }

    connect();

    global.addEventListener("beforeunload", function () {
      closed = true;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
    });
  }

  global.updateUserPresenceDot = updateUserPresenceDot;
  global.initSitePresence = initSitePresence;
})(window);
