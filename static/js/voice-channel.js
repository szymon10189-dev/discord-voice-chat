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
      document.querySelectorAll('.user-avatar-wrap[data-user-id="' + userId + '"]').forEach(function (wrap) {
        var statusDot = wrap.querySelector(".user-status-dot");
        if (!statusDot) return;
        statusDot.classList.toggle("status-online", !!online);
        statusDot.classList.toggle("status-offline", !online);
        statusDot.title = online ? "Online" : "Offline";
      });
    }

    function renderPeerList(extraPeers) {
      if (!peersEl) return;
      peersEl.innerHTML = "";
      var list = extraPeers || [];
      if (!list.length) {
        var empty = document.createElement("p");
        empty.className = "small text-secondary mb-0";
        empty.textContent = joined ? "Nikogo więcej na kanale." : "Dołącz, aby zobaczyć uczestników.";
        peersEl.appendChild(empty);
        return;
      }
      list.forEach(function (p) {
        var row = document.createElement("div");
        row.className = "d-flex align-items-center gap-2 py-1";
        row.setAttribute("data-peer-id", String(p.user_id));

        var iconWrap = document.createElement("span");
        iconWrap.className = "user-avatar-wrap position-relative d-inline-block";
        iconWrap.setAttribute("data-user-id", String(p.user_id));

        var icon = document.createElement("span");
        icon.className = "rounded-circle bg-secondary d-inline-flex align-items-center justify-content-center text-uppercase fw-bold";
        icon.style.width = "32px";
        icon.style.height = "32px";
        icon.style.fontSize = "0.75rem";
        icon.textContent = (p.username || "?").charAt(0);
        iconWrap.appendChild(icon);

        var dot = document.createElement("span");
        dot.className = "user-status-dot user-status-dot-sm " + (p.is_online ? "status-online" : "status-offline");
        dot.title = p.is_online ? "Online" : "Offline";
        iconWrap.appendChild(dot);

        var name = document.createElement("span");
        name.className = "voice-peer-name";
        name.textContent = p.username || "Użytkownik";

        var audioWrap = document.createElement("div");
        audioWrap.className = "voice-remote-audio ms-auto";
        audioWrap.setAttribute("data-audio-for", String(p.user_id));

        row.appendChild(iconWrap);
        row.appendChild(name);
        row.appendChild(audioWrap);
        peersEl.appendChild(row);
      });
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
        var row = peersEl.querySelector('[data-peer-id="' + userId + '"]');
        if (row) row.remove();
        if (!peersEl.querySelector("[data-peer-id]")) renderPeerList([]);
      }
    }

    function createPeerConnection(remoteUserId, remoteUsername, isInitiator) {
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

    async function handleSignal(msg) {
      var fromId = msg.from_user_id;
      var signalType = msg.signal_type;
      var data = msg.data;
      if (!fromId || fromId === currentUserId) return;

      var pc = peers.get(fromId);
      if (!pc) {
        pc = createPeerConnection(fromId, msg.from_username, false);
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
      var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      var wsUrl = proto + "//" + window.location.host + "/ws/voice/" + channelId + "/";
      socket = new WebSocket(wsUrl);

      socket.onopen = function () {
        setStatus("Połączono z kanałem głosowym", true);
      };

      socket.onclose = function (ev) {
        var blocked = ev && ev.code === 4004;
        setStatus(blocked ? "Zablokowany — brak dostępu" : "Rozłączono", false);
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
          if (joined) renderPeerList(data.peers || []);
        } else if (data.type === "user_joined" && joined) {
          var peersOnPage = [];
          if (peersEl) {
            peersEl.querySelectorAll("[data-peer-id]").forEach(function (el) {
              peersOnPage.push({
                user_id: parseInt(el.getAttribute("data-peer-id"), 10),
                username: (el.querySelector(".voice-peer-name") || {}).textContent || "",
                is_online: !!(el.querySelector(".user-status-dot.status-online")),
              });
            });
          }
          peersOnPage.push(data.user);
          renderPeerList(peersOnPage);
          createPeerConnection(data.user.user_id, data.user.username, true);
        } else if (data.type === "user_left") {
          removePeer(data.user_id);
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
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        reportError("Przeglądarka nie obsługuje mikrofonu.");
        return;
      }
      try {
        localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        joined = true;
        if (joinBtn) joinBtn.classList.add("d-none");
        if (leaveBtn) leaveBtn.classList.remove("d-none");
        if (muteBtn) muteBtn.classList.remove("d-none");
        setStatus("Jesteś na kanale głosowym", true);
        connectSocket();
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
      if (joinBtn) joinBtn.classList.remove("d-none");
      if (leaveBtn) leaveBtn.classList.add("d-none");
      if (muteBtn) muteBtn.classList.add("d-none");
      muted = false;
      if (muteBtn) muteBtn.textContent = "Wycisz";
      renderPeerList([]);
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

    renderPeerList([]);
    setStatus("Kliknij „Dołącz”, aby wejść na kanał głosowy", undefined);

    return { leave: leaveVoice };
  }

  global.initVoiceChannel = initVoiceChannel;
})(window);
