(function (global) {
  "use strict";

  function initVoiceChannel(options) {
    var channelId = options.channelId;
    var currentUserId = options.currentUserId;
    var statusEl = options.statusEl;
    var peersEl = options.peersEl;
    var joinBtn = options.joinBtn;
    var muteBtn = options.muteBtn;
    var leaveBtn = options.leaveBtn;
    var onError = options.onError;

    var socket = null;
    var localStream = null;
    var peers = new Map();
    var joined = false;
    var muted = false;
    var inChannel = false;
    var lastMembers = [];

    function setStatus(text, ok) {
      if (!statusEl) return;
      statusEl.textContent = text;
      statusEl.classList.toggle("text-success", ok === true);
      statusEl.classList.toggle("text-danger", ok === false);
      statusEl.classList.toggle("text-secondary", ok === undefined);
    }

    function reportError(msg) {
      if (typeof onError === "function") onError(msg);
      else setStatus(msg, false);
    }

    function updatePresenceDot(userId, online) {
      if (typeof global.updateUserPresenceDot === "function") {
        global.updateUserPresenceDot(userId, online);
      }
    }

    function renderSidebarRoster(members) {
      var box = document.querySelector(
        '[data-voice-roster-channel="' + channelId + '"]',
      );
      if (!box) return;
      box.innerHTML = "";
      if (!members || !members.length) {
        var empty = document.createElement("div");
        empty.className = "voice-roster-user text-secondary opacity-75 ps-1";
        empty.textContent = "— pusto —";
        box.appendChild(empty);
        return;
      }
      members.forEach(function (m) {
        var row = document.createElement("div");
        row.className = "voice-roster-user";
        row.setAttribute("data-sidebar-search", (m.username || "").toLowerCase());

        var dot = document.createElement("span");
        dot.className =
          "user-status-dot " + (m.is_online ? "status-online" : "status-offline");

        var name = document.createElement("span");
        name.className = "text-truncate";
        name.textContent = m.username || "Użytkownik";

        row.appendChild(dot);
        row.appendChild(name);
        box.appendChild(row);
      });
    }

    function renderMemberList(members, youUserId) {
      if (!peersEl) return;
      peersEl.innerHTML = "";
      var list = members || [];
      if (!list.length) {
        var empty = document.createElement("p");
        empty.className = "small text-secondary mb-0";
        empty.textContent = inChannel
          ? "Na kanale nikogo jeszcze nie ma."
          : "Łączenie z kanałem…";
        peersEl.appendChild(empty);
        return;
      }

      list.forEach(function (m) {
        var isYou = m.user_id === youUserId || m.user_id === currentUserId;
        var row = document.createElement("div");
        row.className =
          "voice-member-row d-flex align-items-center gap-2 py-2" +
          (isYou ? " voice-member-you" : "");
        row.setAttribute("data-peer-id", String(m.user_id));

        var iconWrap = document.createElement("span");
        iconWrap.className = "user-avatar-wrap position-relative d-inline-block";
        iconWrap.setAttribute("data-user-id", String(m.user_id));

        var icon = document.createElement("span");
        icon.className =
          "rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center text-uppercase fw-bold";
        icon.style.width = "32px";
        icon.style.height = "32px";
        icon.style.fontSize = "0.75rem";
        icon.textContent = (m.username || "?").charAt(0);
        iconWrap.appendChild(icon);

        var dot = document.createElement("span");
        dot.className =
          "user-status-dot user-status-dot-sm " +
          (m.is_online ? "status-online" : "status-offline");
        dot.title = m.is_online ? "Online" : "Offline";
        iconWrap.appendChild(dot);

        var nameWrap = document.createElement("div");
        nameWrap.className = "flex-grow-1 min-width-0";
        var name = document.createElement("div");
        name.className = "voice-peer-name fw-semibold text-truncate";
        name.textContent = (m.username || "Użytkownik") + (isYou ? " (Ty)" : "");
        nameWrap.appendChild(name);

        var badge = document.createElement("span");
        badge.className = "small text-secondary";
        badge.textContent = joined && isYou ? "Mówisz" : "Na kanale";

        var audioWrap = document.createElement("div");
        audioWrap.className = "voice-remote-audio";
        audioWrap.setAttribute("data-audio-for", String(m.user_id));

        row.appendChild(iconWrap);
        row.appendChild(nameWrap);
        row.appendChild(badge);
        if (!isYou) row.appendChild(audioWrap);
        peersEl.appendChild(row);
      });
    }

    function applyPeerList(data) {
      lastMembers = data.members || [];
      var youId = data.you_user_id != null ? data.you_user_id : currentUserId;
      renderMemberList(lastMembers, youId);
      renderSidebarRoster(lastMembers);
    }

    function sendSignal(targetUserId, signalType, data) {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      socket.send(
        JSON.stringify({
          type: "signal",
          target_user_id: targetUserId,
          signal_type: signalType,
          data: data,
        }),
      );
    }

    function attachRemoteAudio(userId, stream) {
      if (!peersEl) return;
      var wrap = peersEl.querySelector('[data-audio-for="' + userId + '"]');
      if (!wrap) return;
      wrap.innerHTML = "";
      var aud = document.createElement("audio");
      aud.autoplay = true;
      aud.playsInline = true;
      aud.srcObject = stream;
      wrap.appendChild(aud);
    }

    function removePeer(userId) {
      var pc = peers.get(userId);
      if (pc) {
        pc.close();
        peers.delete(userId);
      }
      if (peersEl) {
        var audio = peersEl.querySelector('[data-audio-for="' + userId + '"]');
        if (audio) audio.innerHTML = "";
      }
    }

    function createPeerConnection(remoteUserId, isInitiator) {
      if (peers.has(remoteUserId)) return peers.get(remoteUserId);

      var pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      peers.set(remoteUserId, pc);

      if (localStream) {
        localStream.getTracks().forEach(function (track) {
          pc.addTrack(track, localStream);
        });
      }

      pc.onicecandidate = function (ev) {
        if (ev.candidate) {
          sendSignal(remoteUserId, "ice", ev.candidate);
        }
      };

      pc.ontrack = function (ev) {
        attachRemoteAudio(remoteUserId, ev.streams[0]);
      };

      pc.onconnectionstatechange = function () {
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          removePeer(remoteUserId);
        }
      };

      if (isInitiator) {
        pc.createOffer()
          .then(function (offer) {
            return pc.setLocalDescription(offer);
          })
          .then(function () {
            sendSignal(remoteUserId, "offer", pc.localDescription);
          })
          .catch(function () {
            reportError("Nie udało się nawiązać połączenia głosowego.");
          });
      }

      return pc;
    }

    function startCallsWithOthers(members) {
      if (!joined || !localStream) return;
      (members || []).forEach(function (m) {
        if (m.user_id === currentUserId) return;
        createPeerConnection(m.user_id, true);
      });
    }

    async function handleSignal(msg) {
      var fromId = msg.from_user_id;
      var signalType = msg.signal_type;
      var data = msg.data;
      if (!fromId || fromId === currentUserId || !joined) return;

      var pc = peers.get(fromId);
      if (!pc) {
        pc = createPeerConnection(fromId, false);
      }

      try {
        if (signalType === "offer") {
          await pc.setRemoteDescription(new RTCSessionDescription(data));
          var answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          sendSignal(fromId, "answer", pc.localDescription);
        } else if (signalType === "answer") {
          await pc.setRemoteDescription(new RTCSessionDescription(data));
        } else if (signalType === "ice" && data) {
          await pc.addIceCandidate(new RTCIceCandidate(data));
        }
      } catch (e) {
        reportError("Błąd sygnalizacji WebRTC.");
      }
    }

    function connectSocket() {
      if (socket && socket.readyState === WebSocket.OPEN) return;

      var proto = global.location.protocol === "https:" ? "wss:" : "ws:";
      var wsUrl = proto + "//" + global.location.host + "/ws/voice/" + channelId + "/";
      socket = new WebSocket(wsUrl);

      socket.onopen = function () {
        inChannel = true;
        setStatus(
          joined
            ? "Połączono — mikrofon aktywny"
            : "Na kanale głosowym (bez mikrofonu)",
          true,
        );
      };

      socket.onclose = function (ev) {
        inChannel = false;
        var blocked = ev && ev.code === 4004;
        setStatus(blocked ? "Zablokowany — brak dostępu" : "Opuszczono kanał", false);
        renderMemberList([], currentUserId);
        renderSidebarRoster([]);
      };

      socket.onerror = function () {
        setStatus("Błąd połączenia", false);
      };

      socket.onmessage = function (event) {
        var data;
        try {
          data = JSON.parse(event.data);
        } catch (e) {
          return;
        }
        if (data.type === "peer_list") {
          applyPeerList(data);
          if (joined) startCallsWithOthers(data.members);
        } else if (data.type === "presence_update" && data.user_id != null) {
          updatePresenceDot(data.user_id, !!data.online);
        } else if (data.type === "signal") {
          handleSignal(data);
        } else if (data.type === "error") {
          reportError(data.message || "Błąd");
        }
      };
    }

    async function joinVoice() {
      if (joined) return;
      if (!inChannel) {
        reportError("Poczekaj na połączenie z kanałem.");
        return;
      }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        reportError("Przeglądarka nie obsługuje mikrofonu.");
        return;
      }
      try {
        localStream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: false,
        });
        joined = true;
        if (joinBtn) joinBtn.classList.add("d-none");
        if (leaveBtn) leaveBtn.classList.remove("d-none");
        if (muteBtn) muteBtn.classList.remove("d-none");
        setStatus("Mówisz na kanale głosowym", true);
        startCallsWithOthers(lastMembers);
      } catch (e) {
        reportError("Nie udało się uzyskać dostępu do mikrofonu.");
      }
    }

    function leaveVoice() {
      joined = false;
      peers.forEach(function (pc) {
        pc.close();
      });
      peers.clear();
      if (localStream) {
        localStream.getTracks().forEach(function (t) {
          t.stop();
        });
        localStream = null;
      }
      if (socket) {
        socket.close();
        socket = null;
      }
      inChannel = false;
      if (joinBtn) joinBtn.classList.remove("d-none");
      if (leaveBtn) leaveBtn.classList.add("d-none");
      if (muteBtn) muteBtn.classList.add("d-none");
      muted = false;
      if (muteBtn) muteBtn.textContent = "Wycisz";
      renderMemberList([], currentUserId);
      setStatus("Opuszczono kanał głosowy", undefined);
    }

    function toggleMute() {
      if (!localStream) return;
      muted = !muted;
      localStream.getAudioTracks().forEach(function (t) {
        t.enabled = !muted;
      });
      if (muteBtn) muteBtn.textContent = muted ? "Włącz mikrofon" : "Wycisz";
    }

    if (joinBtn) joinBtn.addEventListener("click", joinVoice);
    if (leaveBtn) leaveBtn.addEventListener("click", leaveVoice);
    if (muteBtn) muteBtn.addEventListener("click", toggleMute);

    renderMemberList([], currentUserId);
    setStatus("Łączenie z kanałem głosowym…", undefined);
    connectSocket();

    return { leave: leaveVoice };
  }

  global.initVoiceChannel = initVoiceChannel;
})(window);
