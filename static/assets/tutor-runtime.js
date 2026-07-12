(() => {
  const STREAM_ENDPOINT = "/api/tutor/chat/stream";
  const STREAM_COMMIT_ENDPOINT = "/api/tutor/chat/commit";
  const TTS_ENDPOINT = "/api/tutor/tts";
  const TTS_SENTENCE_SOFT_LIMIT = 220;
  const TTS_SENTENCE_START_THRESHOLD_CHARS = 20;
  const TTS_SENTENCE_START_THRESHOLD_WORDS = 4;

  const idleSessionPatch = {
    transport: "none",
    activeTurnId: null,
    hasReceivedContent: false,
    lastError: "",
  };

  const idleTutorAudioState = {
    mode: "idle",
    turnId: null,
    queueDepth: 0,
    localPlaybackStarted: false,
    fallbackInUse: false,
  };

  const nowMs = () => (typeof window.performance?.now === "function" ? window.performance.now() : Date.now());

  const createTurnId = () => `stream-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const browserSpeechSupported = () => (
    typeof window.chatBrowserSpeechSupported === "function"
      ? window.chatBrowserSpeechSupported()
      : (typeof window.speechSynthesis !== "undefined" && typeof window.SpeechSynthesisUtterance !== "undefined")
  );
  const localTutorTtsAvailable = () => Boolean(state.config?.tutor_local_tts_available);
  const browserTutorFallbackAllowed = () => {
    const fallbackPolicy = String(state.config?.tutor_tts_fallback || "browser").trim().toLowerCase();
    return fallbackPolicy !== "none" && browserSpeechSupported();
  };
  const normalizeTextForSegmentation = (text) => String(text || "").replace(/\s+/g, " ").trim();
  const countWords = (text) => normalizeTextForSegmentation(text).split(" ").filter(Boolean).length;
  let activeAudioRuntime = null;
  const tutorAudioElement = typeof Audio !== "undefined" ? new Audio() : null;
  if (tutorAudioElement) tutorAudioElement.preload = "auto";
  const AudioContextCtor = typeof window !== "undefined"
    ? (window.AudioContext || window.webkitAudioContext || null)
    : null;
  let tutorAudioContext = null;
  let tutorAudioSourceNode = null;
  let tutorAudioAnalyser = null;
  let tutorAudioMeterData = null;
  let tutorAudioMeterFrame = 0;
  let lastTutorAudioDebugMode = idleTutorAudioState.mode;
  window.TUTOR_IDENTITY_VOICE_DEBUG = window.TUTOR_IDENTITY_VOICE_DEBUG || { enabled: true };
  const tutorVoiceDebugEnabled = () => Boolean(window.TUTOR_IDENTITY_VOICE_DEBUG?.enabled);
  const logTutorVoiceDebug = (eventName, payload = {}) => {
    if (!tutorVoiceDebugEnabled() || typeof console === "undefined" || typeof console.info !== "function") return;
    console.info("[TutorVoiceDebug]", eventName, payload);
  };
  const portraitDebugEnabled = () => Boolean(window.TUTOR_PORTRAIT_DEBUG?.enabled);
  const logTutorAudioDebug = (eventName, payload = {}) => {
    if (!portraitDebugEnabled() || typeof console === "undefined" || typeof console.info !== "function") return;
    console.info("[TutorPortraitDebug]", eventName, payload);
  };

  const renderBubble = (bubble, role, text, extraClass = "", note = "") => {
    if (!bubble) return;
    bubble.className = ["bubble", role, extraClass].filter(Boolean).join(" ");
    const safeText = window.escapeHtml(String(text || "")).replace(/\n/g, "<br />");
    const noteMarkup = note ? `<div class="bubble-stream-note">${window.escapeHtml(note)}</div>` : "";
    bubble.innerHTML = `${safeText}${noteMarkup}`;
    if (bubble.parentElement) bubble.parentElement.scrollTop = bubble.parentElement.scrollHeight;
  };

  const clearActiveRequestRefs = (controller, bubble, { keepPendingBubble = false } = {}) => {
    const ownsChatRequest = state.chatRequestController === controller;
    const ownsTutorStream = state.tutorStreamController === controller;
    if (state.chatRequestController === controller) state.chatRequestController = null;
    if (state.tutorStreamController === controller) state.tutorStreamController = null;
    if (ownsChatRequest || ownsTutorStream || !controller) state.chatRequestInFlight = false;
    if (!keepPendingBubble && state.chatPendingBubble === bubble) state.chatPendingBubble = null;
    if (typeof window.refreshChatTtsUi === "function") window.refreshChatTtsUi();
    if (typeof window.updateChatComposerState === "function") window.updateChatComposerState();
  };

  const buildApiErrorMessage = async (response) => {
    try {
      const raw = await response.text();
      if (!raw) return `Tutor-Streaming fehlgeschlagen (${response.status}).`;
      try {
        const parsed = JSON.parse(raw);
        const detail = typeof parsed?.detail === "string" ? parsed.detail : "";
        return detail || raw;
      } catch {
        return raw;
      }
    } catch {
      return `Tutor-Streaming fehlgeschlagen (${response.status}).`;
    }
  };

  const buildFallbackError = (message) => {
    const error = new Error(message || "Tutor-Antworten sind gerade nicht verfügbar.");
    error.canFallback = true;
    return error;
  };

  const commitStreamedTurn = async ({ conversationId, message, reply, level }) => {
    const response = await window.fetch(STREAM_COMMIT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
        reply,
        level,
      }),
    });
    if (!response.ok) {
      const detail = await buildApiErrorMessage(response);
      throw new Error(detail || "Tutor-Antwort konnte nicht gespeichert werden.");
    }
  };

  const setTutorAudioState = (patch = {}) => {
    const current = state.tutorAudio && typeof state.tutorAudio === "object"
      ? state.tutorAudio
      : { ...idleTutorAudioState };
    state.tutorAudio = { ...current, ...patch };
    if (typeof window.refreshChatTtsUi === "function") window.refreshChatTtsUi();
    if (typeof window.updateChatComposerState === "function") window.updateChatComposerState();
    window.syncTutorAvatarPresentation?.();
    return state.tutorAudio;
  };

  const resetTutorAudioState = () => setTutorAudioState({ ...idleTutorAudioState });

  const syncTutorAudioRuntimeState = (runtime) => {
    if (!runtime || runtime.stopped) {
      if (portraitDebugEnabled() && lastTutorAudioDebugMode !== "idle") {
        logTutorAudioDebug("audio-mode", {
          previousMode: lastTutorAudioDebugMode,
          nextMode: "idle",
          turnId: runtime?.turnId || null,
          source: runtime?.source || null,
          visibleIdentity: runtime?.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar,
        });
      }
      lastTutorAudioDebugMode = "idle";
      resetTutorAudioState();
      return;
    }
    const queueDepth = runtime.pendingSentenceJobs.length + runtime.readyAudioQueue.length + (runtime.fetchInFlight ? 1 : 0);
    let mode = "idle";
    if (runtime.fallbackInUse) mode = "fallback";
    else if (runtime.playing) mode = "speaking";
    else if (queueDepth > 0) mode = "queueing";
    if (portraitDebugEnabled() && lastTutorAudioDebugMode !== mode) {
      logTutorAudioDebug("audio-mode", {
        previousMode: lastTutorAudioDebugMode,
        nextMode: mode,
        turnId: runtime.turnId,
        source: runtime.source,
        visibleIdentity: runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar,
        localPlaybackStarted: runtime.localPlaybackStarted,
        fallbackInUse: runtime.fallbackInUse,
      });
    }
    lastTutorAudioDebugMode = mode;
    setTutorAudioState({
      mode,
      turnId: runtime.turnId,
      queueDepth,
      localPlaybackStarted: runtime.localPlaybackStarted,
      fallbackInUse: runtime.fallbackInUse,
    });
  };

  const setChatVoiceStatus = (message) => {
    if (els.chatVoiceStatus) els.chatVoiceStatus.textContent = message;
  };

  const revokeRuntimeAudioUrls = (runtime) => {
    if (!runtime) return;
    if (runtime.activeObjectUrl) {
      try {
        URL.revokeObjectURL(runtime.activeObjectUrl);
      } catch {
        // Ignore browser cleanup failures.
      }
      runtime.activeObjectUrl = null;
    }
    runtime.readyAudioQueue.forEach((item) => {
      if (!item?.url) return;
      try {
        URL.revokeObjectURL(item.url);
      } catch {
        // Ignore browser cleanup failures.
      }
    });
    runtime.readyAudioQueue = [];
  };

  const stopAudioElementPlayback = () => {
    if (!tutorAudioElement) return;
    try {
      tutorAudioElement.pause();
      tutorAudioElement.removeAttribute("src");
      tutorAudioElement.load();
    } catch {
      // Best effort only.
    }
  };

  const stopTutorAudioMeter = () => {
    if (tutorAudioMeterFrame) {
      window.cancelAnimationFrame(tutorAudioMeterFrame);
      tutorAudioMeterFrame = 0;
    }
    window.setTutorAvatarSpeakingLevel?.(0);
  };

  const ensureTutorAudioAnalyser = async () => {
    if (!AudioContextCtor || !tutorAudioElement) return null;
    if (!tutorAudioContext) tutorAudioContext = new AudioContextCtor();
    if (!tutorAudioSourceNode) {
      tutorAudioSourceNode = tutorAudioContext.createMediaElementSource(tutorAudioElement);
      tutorAudioAnalyser = tutorAudioContext.createAnalyser();
      tutorAudioAnalyser.fftSize = 256;
      tutorAudioAnalyser.smoothingTimeConstant = 0.78;
      tutorAudioSourceNode.connect(tutorAudioAnalyser);
      tutorAudioAnalyser.connect(tutorAudioContext.destination);
      tutorAudioMeterData = new Uint8Array(tutorAudioAnalyser.fftSize);
    }
    if (tutorAudioContext.state === "suspended") {
      try {
        await tutorAudioContext.resume();
      } catch {
        return null;
      }
    }
    return tutorAudioAnalyser;
  };

  const sampleTutorAudioLevel = () => {
    if (!tutorAudioAnalyser || !tutorAudioMeterData) return 0;
    tutorAudioAnalyser.getByteTimeDomainData(tutorAudioMeterData);
    let sum = 0;
    for (const value of tutorAudioMeterData) {
      const sample = (value - 128) / 128;
      sum += sample * sample;
    }
    const rms = Math.sqrt(sum / tutorAudioMeterData.length);
    return Math.max(0, Math.min(1, (rms - 0.015) * 7.5));
  };

  const startTutorAudioMeter = async (runtime) => {
    if (!runtime || runtime.stopped) return;
    stopTutorAudioMeter();
    const analyser = await ensureTutorAudioAnalyser();
    if (!analyser || runtime.stopped || activeAudioRuntime !== runtime) {
      window.setTutorAvatarSpeakingLevel?.(0.42);
      return;
    }
    const tick = () => {
      if (!runtime || runtime.stopped || activeAudioRuntime !== runtime || !runtime.playing) {
        stopTutorAudioMeter();
        return;
      }
      window.setTutorAvatarSpeakingLevel?.(sampleTutorAudioLevel());
      tutorAudioMeterFrame = window.requestAnimationFrame(tick);
    };
    tick();
  };

  const ensureAudioRuntime = ({ turnId, source = "stream" } = {}) => {
    const runtimeTurnId = String(turnId || `tts-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
    if (activeAudioRuntime?.turnId === runtimeTurnId) return activeAudioRuntime;
    window.stopTutorAudio?.({ cancelBrowser: false, silent: true });
    activeAudioRuntime = {
      turnId: runtimeTurnId,
      source,
      personaKey: typeof window.getTutorVoicePersonaKey === "function"
        ? window.getTutorVoicePersonaKey()
        : state.tutorAvatar,
      committedSegments: [],
      sentenceBuffer: "",
      pendingSentenceJobs: [],
      readyAudioQueue: [],
      sentenceIndex: 0,
      fetchInFlight: false,
      ttsController: null,
      playing: false,
      activeObjectUrl: null,
      stopped: false,
      localEligible: localTutorTtsAvailable(),
      localPlaybackStarted: false,
      localTurnFailed: false,
      fallbackInUse: false,
      finalText: "",
      doneReceived: false,
    };
    syncTutorAudioRuntimeState(activeAudioRuntime);
    return activeAudioRuntime;
  };

  const hasStableSentenceShape = (text) => {
    const normalized = normalizeTextForSegmentation(text);
    if (!normalized) return false;
    return normalized.length >= TTS_SENTENCE_START_THRESHOLD_CHARS
      || countWords(normalized) >= TTS_SENTENCE_START_THRESHOLD_WORDS;
  };

  const isNumericPeriodBoundary = (text, boundaryIndex) => {
    const punctuationChar = text[boundaryIndex - 1] || "";
    const previousChar = text[boundaryIndex - 2] || "";
    const nextChar = text[boundaryIndex] || "";
    return punctuationChar === "." && /\d/.test(previousChar) && /\d/.test(nextChar);
  };

  const findSentenceBoundaryIndex = (text) => {
    const matches = text.matchAll(/[.!?]+(?:["')\]]+)?/g);
    for (const match of matches) {
      const index = Number(match.index);
      if (!Number.isFinite(index) || index < 0) continue;
      const matchText = String(match[0] || "");
      const boundaryIndex = index + matchText.length;
      if (isNumericPeriodBoundary(text, boundaryIndex)) continue;

      const candidate = text.slice(0, boundaryIndex);
      const trailingText = text.slice(boundaryIndex);
      const nextVisibleMatch = trailingText.match(/[^\s]/);
      const nextVisibleChar = nextVisibleMatch ? String(nextVisibleMatch[0] || "") : "";

      if (!nextVisibleChar) return boundaryIndex;
      if (/^\s/.test(trailingText)) return boundaryIndex;
      if (/^[A-Z0-9"'([{]/.test(nextVisibleChar)) {
        if (/[!?]/.test(matchText) || hasStableSentenceShape(candidate)) return boundaryIndex;
      }
      if (/[!?]/.test(matchText) && hasStableSentenceShape(candidate)) return boundaryIndex;
    }
    return -1;
  };

  const bestSoftSplitIndex = (text, limit = TTS_SENTENCE_SOFT_LIMIT) => {
    const capped = Math.min(limit, text.length);
    const checkpoints = [
      text.lastIndexOf(", ", capped),
      text.lastIndexOf("; ", capped),
      text.lastIndexOf(": ", capped),
      text.lastIndexOf(" - ", capped),
      text.lastIndexOf(" ", capped),
    ];
    const splitIndex = checkpoints.find((value) => value >= Math.floor(limit * 0.55));
    if (splitIndex && splitIndex > 0) return splitIndex + 1;
    return capped;
  };

  const extractSpeechChunks = (buffer, { flush = false } = {}) => {
    let rest = String(buffer || "");
    const chunks = [];

    while (rest.trim()) {
      rest = rest.trimStart();
      const boundaryIndex = findSentenceBoundaryIndex(rest);
      if (boundaryIndex > 0) {
        const sentence = rest.slice(0, boundaryIndex).trim();
        rest = rest.slice(boundaryIndex).trimStart();
        if (sentence) chunks.push(sentence);
        continue;
      }
      if (rest.length > TTS_SENTENCE_SOFT_LIMIT) {
        const splitIndex = bestSoftSplitIndex(rest, TTS_SENTENCE_SOFT_LIMIT);
        const chunk = rest.slice(0, splitIndex).trim();
        rest = rest.slice(splitIndex).trimStart();
        if (chunk) chunks.push(chunk);
        continue;
      }
      break;
    }

    if (flush) {
      const tail = rest.trim();
      if (tail) chunks.push(tail);
      rest = "";
    }

    return { chunks, rest };
  };

  const finalizeTutorAudioRuntimeIfIdle = (runtime) => {
    if (!runtime || runtime.stopped || activeAudioRuntime !== runtime) return;
    const nothingPending = !runtime.fetchInFlight && !runtime.playing && !runtime.pendingSentenceJobs.length && !runtime.readyAudioQueue.length;
    if (!runtime.doneReceived || !nothingPending) {
      syncTutorAudioRuntimeState(runtime);
      return;
    }
    if (!runtime.localPlaybackStarted && runtime.localTurnFailed && browserTutorFallbackAllowed() && runtime.finalText && state.chatTtsEnabled) {
      runtime.fallbackInUse = true;
      syncTutorAudioRuntimeState(runtime);
      activeAudioRuntime = null;
      window.speakChatReply?.(runtime.finalText);
      return;
    }
    activeAudioRuntime = null;
    resetTutorAudioState();
    if (state.chatTtsEnabled && !runtime.fallbackInUse) setChatVoiceStatus("Wiedergabe bereit.");
  };

  const playNextTutorAudioChunk = async (runtime) => {
    if (!runtime || runtime.stopped || activeAudioRuntime !== runtime || runtime.playing || !tutorAudioElement) {
      return;
    }
    const nextItem = runtime.readyAudioQueue.shift();
    syncTutorAudioRuntimeState(runtime);
    if (!nextItem) {
      finalizeTutorAudioRuntimeIfIdle(runtime);
      return;
    }

    runtime.playing = true;
    runtime.localPlaybackStarted = true;
    runtime.activeObjectUrl = nextItem.url;
    syncTutorAudioRuntimeState(runtime);
    logTutorAudioDebug("tts-playback-start", {
      turnId: runtime.turnId,
      source: runtime.source,
      visibleIdentity: runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar,
      queueDepth: runtime.pendingSentenceJobs.length + runtime.readyAudioQueue.length,
    });
    logTutorVoiceDebug("tts-playback-start", {
      visibleIdentity: typeof window.normalizeTutorIdentityKey === "function"
        ? window.normalizeTutorIdentityKey(state.tutorAvatar)
        : state.tutorAvatar,
      outgoingTtsPersonaKey: runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar,
      resolvedLocalVoiceName: nextItem.voiceLabel || null,
      resolvedLocalVoiceId: nextItem.voiceLabel || null,
      resolvedLocalVoiceSource: nextItem.voiceSource || null,
      finalPlaybackPath: "local",
    });
    void startTutorAudioMeter(runtime);

    try {
      await new Promise((resolve, reject) => {
        const cleanup = () => {
          tutorAudioElement.onended = null;
          tutorAudioElement.onerror = null;
        };

        tutorAudioElement.onended = () => {
          cleanup();
          resolve();
        };
        tutorAudioElement.onerror = () => {
          cleanup();
          reject(new Error("Wiedergabe konnte nicht abgespielt werden."));
        };

        tutorAudioElement.src = nextItem.url;
        tutorAudioElement.currentTime = 0;
        const playPromise = tutorAudioElement.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch((error) => {
            cleanup();
            reject(error instanceof Error ? error : new Error("Wiedergabe konnte nicht gestartet werden."));
          });
        }
      });
    } catch (error) {
      if (!runtime.stopped) setChatVoiceStatus(error?.message || "Wiedergabe fehlgeschlagen.");
    } finally {
      runtime.playing = false;
      stopTutorAudioMeter();
      if (runtime.activeObjectUrl) {
        try {
          URL.revokeObjectURL(runtime.activeObjectUrl);
        } catch {
          // Ignore browser cleanup failures.
        }
        runtime.activeObjectUrl = null;
      }
      stopAudioElementPlayback();
      syncTutorAudioRuntimeState(runtime);
      logTutorAudioDebug("tts-playback-stop", {
        turnId: runtime.turnId,
        source: runtime.source,
        visibleIdentity: runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar,
        queueDepth: runtime.pendingSentenceJobs.length + runtime.readyAudioQueue.length,
      });
      if (!runtime.stopped) {
        window.setTimeout(() => {
          playNextTutorAudioChunk(runtime);
          finalizeTutorAudioRuntimeIfIdle(runtime);
        }, 0);
      }
    }
  };

  const markTutorAudioLocalFailure = (runtime, errorMessage) => {
    if (!runtime || runtime.stopped) return;
    runtime.localEligible = false;
    runtime.localTurnFailed = true;
    runtime.pendingSentenceJobs = [];
    revokeRuntimeAudioUrls(runtime);
    if (!runtime.localPlaybackStarted && browserTutorFallbackAllowed()) {
      setChatVoiceStatus("Vorbereitete Stimme nicht verfügbar. Systemstimme wird vorbereitet.");
    } else {
      setChatVoiceStatus(errorMessage || "Wiedergabe für diese Antwort nicht verfügbar.");
    }
    syncTutorAudioRuntimeState(runtime);
    finalizeTutorAudioRuntimeIfIdle(runtime);
  };

  const requestTutorSpeechChunk = async (runtime, text, sentenceIndex) => {
    const controller = new AbortController();
    runtime.ttsController = controller;
    runtime.fetchInFlight = true;
    syncTutorAudioRuntimeState(runtime);
    const outgoingPersonaKey = runtime.personaKey || window.getTutorVoicePersonaKey?.() || state.tutorAvatar;
    logTutorVoiceDebug("tts-request", {
      visibleIdentity: typeof window.normalizeTutorIdentityKey === "function"
        ? window.normalizeTutorIdentityKey(state.tutorAvatar)
        : state.tutorAvatar,
      outgoingTtsPersonaKey: outgoingPersonaKey,
      browserFallbackGender: typeof window.getTutorPersonaVoiceGender === "function"
        ? window.getTutorPersonaVoiceGender()
        : state.chatVoiceGender,
    });

    try {
      const response = await window.fetch(TTS_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          turn_id: runtime.turnId,
          sentence_index: sentenceIndex,
          persona_key: outgoingPersonaKey,
        }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(await buildApiErrorMessage(response));

      const blob = await response.blob();
      if (!blob || !blob.size) throw new Error("Die vorbereitete Stimme hat keine Audiodaten geliefert.");

      const voiceLabel = String(response.headers.get("X-Tutor-Tts-Voice") || state.config?.tutor_tts_voice_label || "lokale Stimme").trim();
      const voiceSource = String(response.headers.get("X-Tutor-Tts-Voice-Source") || "").trim() || null;
      logTutorVoiceDebug("tts-response", {
        visibleIdentity: typeof window.normalizeTutorIdentityKey === "function"
          ? window.normalizeTutorIdentityKey(state.tutorAvatar)
          : state.tutorAvatar,
        outgoingTtsPersonaKey: outgoingPersonaKey,
        resolvedLocalVoiceName: voiceLabel || null,
        resolvedLocalVoiceId: voiceLabel || null,
        resolvedLocalVoiceSource: voiceSource,
      });
      const url = URL.createObjectURL(blob);
      runtime.readyAudioQueue.push({ url, voiceLabel, voiceSource });
      syncTutorAudioRuntimeState(runtime);
      if (!runtime.localPlaybackStarted) setChatVoiceStatus(`Wiedergabe: ${voiceLabel}.`);
      playNextTutorAudioChunk(runtime);
    } catch (error) {
      if (controller.signal.aborted || runtime.stopped) return;
      logTutorVoiceDebug("tts-response", {
        visibleIdentity: typeof window.normalizeTutorIdentityKey === "function"
          ? window.normalizeTutorIdentityKey(state.tutorAvatar)
          : state.tutorAvatar,
        outgoingTtsPersonaKey: outgoingPersonaKey,
        resolvedLocalVoiceName: null,
        error: error?.message || "Local Tutor TTS request failed.",
      });
      markTutorAudioLocalFailure(runtime, error?.message || "Die vorbereitete Stimme konnte nicht erzeugt werden.");
    } finally {
      if (runtime.ttsController === controller) runtime.ttsController = null;
      runtime.fetchInFlight = false;
      syncTutorAudioRuntimeState(runtime);
    }
  };

  const pumpTutorSpeechQueue = async (runtime) => {
    if (!runtime || runtime.stopped || activeAudioRuntime !== runtime || runtime.fetchInFlight || !runtime.localEligible) {
      syncTutorAudioRuntimeState(runtime);
      return;
    }
    const nextJob = runtime.pendingSentenceJobs.shift();
    syncTutorAudioRuntimeState(runtime);
    if (!nextJob) {
      finalizeTutorAudioRuntimeIfIdle(runtime);
      return;
    }
    await requestTutorSpeechChunk(runtime, nextJob.text, nextJob.sentenceIndex);
    if (!runtime.stopped) {
      window.setTimeout(() => {
        pumpTutorSpeechQueue(runtime);
      }, 0);
    }
  };

  const queueTutorSpeechChunks = (runtime, chunks) => {
    if (!runtime || runtime.stopped || !Array.isArray(chunks) || !chunks.length || !state.chatTtsEnabled) return;
    chunks.forEach((chunk) => {
      const text = normalizeTextForSegmentation(chunk);
      if (!text) return;
      runtime.committedSegments.push(text);
      if (!runtime.localEligible) return;
      runtime.pendingSentenceJobs.push({
        sentenceIndex: runtime.sentenceIndex,
        text,
      });
      runtime.sentenceIndex += 1;
    });
    syncTutorAudioRuntimeState(runtime);
    if (runtime.localEligible) pumpTutorSpeechQueue(runtime);
  };

  const appendTutorSpeechText = (runtime, text, { flush = false } = {}) => {
    if (!runtime || runtime.stopped || !state.chatTtsEnabled) return;
    runtime.sentenceBuffer = `${runtime.sentenceBuffer || ""}${String(text || "")}`;
    const { chunks, rest } = extractSpeechChunks(runtime.sentenceBuffer, { flush });
    runtime.sentenceBuffer = rest;
    queueTutorSpeechChunks(runtime, chunks);
  };

  const reconcilePendingSpeechWithFinalText = (runtime, finalText) => {
    if (!runtime) return;
    runtime.finalText = normalizeTextForSegmentation(finalText);
    if (!runtime.finalText || !state.chatTtsEnabled) return;

    const committedPrefix = normalizeTextForSegmentation(runtime.committedSegments.join(" "));
    if (!committedPrefix) {
      runtime.sentenceBuffer = runtime.finalText;
      appendTutorSpeechText(runtime, "", { flush: true });
      return;
    }
    if (runtime.finalText === committedPrefix) {
      runtime.sentenceBuffer = "";
      return;
    }
    if (runtime.finalText.startsWith(`${committedPrefix} `)) {
      runtime.sentenceBuffer = runtime.finalText.slice(committedPrefix.length).trim();
      appendTutorSpeechText(runtime, "", { flush: true });
      return;
    }
    if (!runtime.localPlaybackStarted && !runtime.fetchInFlight && !runtime.pendingSentenceJobs.length && !runtime.readyAudioQueue.length) {
      runtime.committedSegments = [];
      runtime.sentenceBuffer = runtime.finalText;
      runtime.sentenceIndex = 0;
      appendTutorSpeechText(runtime, "", { flush: true });
    }
  };

  const completeTutorSpeechTurn = (runtime, finalText) => {
    if (!runtime || runtime.stopped) return;
    runtime.doneReceived = true;
    if (finalText) reconcilePendingSpeechWithFinalText(runtime, finalText);
    if (!state.chatTtsEnabled) {
      activeAudioRuntime = null;
      resetTutorAudioState();
      return;
    }
    if (!runtime.localEligible && !runtime.localPlaybackStarted && browserTutorFallbackAllowed() && runtime.finalText) {
      runtime.fallbackInUse = true;
      syncTutorAudioRuntimeState(runtime);
      activeAudioRuntime = null;
      window.speakChatReply?.(runtime.finalText);
      return;
    }
    finalizeTutorAudioRuntimeIfIdle(runtime);
  };

  window.tutorStreamingSupported = function tutorStreamingSupported() {
    return typeof window.fetch === "function"
      && typeof window.TextDecoder !== "undefined"
      && typeof window.AbortController !== "undefined"
      && typeof window.ReadableStream !== "undefined";
  };

  window.tutorAudioSupported = function tutorAudioSupported() {
    return localTutorTtsAvailable() || browserTutorFallbackAllowed();
  };

  window.stopTutorAudio = function stopTutorAudio(options = {}) {
    const { cancelBrowser = true, silent = false } = options;
    const runtime = activeAudioRuntime;
    stopTutorAudioMeter();
    if (runtime) {
      runtime.stopped = true;
      if (runtime.ttsController) {
        try {
          runtime.ttsController.abort();
        } catch {
          // Best effort only.
        }
      }
      runtime.ttsController = null;
      runtime.pendingSentenceJobs = [];
      runtime.fetchInFlight = false;
      revokeRuntimeAudioUrls(runtime);
    }
    activeAudioRuntime = null;
    stopAudioElementPlayback();
    if (cancelBrowser && browserSpeechSupported()) {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // Best effort only.
      }
    }
    resetTutorAudioState();
    window.resetTutorAvatarActivity?.();
    if (!silent && state.chatTtsEnabled) setChatVoiceStatus("Wiedergabe bereit.");
  };

  window.playTutorReplyAudio = function playTutorReplyAudio(text, options = {}) {
    const replyText = normalizeTextForSegmentation(text);
    if (!state.chatTtsEnabled || !replyText) return false;

    const runtime = ensureAudioRuntime({
      turnId: options.turnId || `reply-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      source: options.source || "manual",
    });
    runtime.finalText = replyText;
    runtime.doneReceived = true;

    if (!runtime.localEligible) {
      if (browserTutorFallbackAllowed()) {
        runtime.fallbackInUse = true;
        syncTutorAudioRuntimeState(runtime);
        activeAudioRuntime = null;
        window.speakChatReply?.(replyText);
        return true;
      }
      setChatVoiceStatus("Wiedergabe nicht verfügbar.");
      activeAudioRuntime = null;
      resetTutorAudioState();
      return false;
    }

    runtime.sentenceBuffer = replyText;
    appendTutorSpeechText(runtime, "", { flush: true });
    finalizeTutorAudioRuntimeIfIdle(runtime);
    return true;
  };

  window.interruptTutorStream = function interruptTutorStream(options = {}) {
    const { silent = false, suppressStatus = false } = options;
    const controller = state.tutorStreamController;
    const canInterrupt = typeof window.canInterruptTutorSession === "function" ? window.canInterruptTutorSession() : false;
    if (!controller && !canInterrupt) return false;
    const bubble = state.chatPendingBubble;
    const currentText = bubble?.textContent?.trim() || "";

    window.stopTutorAudio({ cancelBrowser: true, silent: true });

    if (controller) {
      controller.__tutorAbortReason = "interrupted";
      try {
        controller.abort();
      } catch {
        // Best effort only.
      }
    }

    if (bubble) {
      if (currentText && currentText !== "Der Tutor denkt nach ...") {
        renderBubble(bubble, "assistant", currentText, "interrupted", "Unterbrochen.");
      } else {
        renderBubble(bubble, "system", "Antwort unterbrochen.", "interrupted");
      }
    }

    window.setTutorSessionState?.("interrupted", {
      transport: "none",
      activeTurnId: null,
      hasReceivedContent: false,
      lastError: "interrupted",
    });
    state.chatPendingBubble = null;
    clearActiveRequestRefs(controller, bubble, { keepPendingBubble: false });
    if (!silent && !suppressStatus && typeof window.setChatStatus === "function") {
      window.setChatStatus("Antwort unterbrochen.", "error");
    }
    return true;
  };

  window.sendTutorStreamMessage = async function sendTutorStreamMessage(message) {
    const trimmedMessage = String(message || "").trim();
    if (!trimmedMessage) return;
    if (!window.tutorStreamingSupported()) throw buildFallbackError("Streaming wird in diesem Browser nicht unterstuetzt.");

    const controller = new AbortController();
    controller.__tutorAbortReason = "";
    const timeoutMs = state.config?.chat_timeout_ms || 45000;
    const timeoutId = window.setTimeout(() => {
      controller.__tutorAbortReason = "timeout";
      controller.abort();
    }, timeoutMs);

    const turnId = createTurnId();
    const requestStartedAt = nowMs();

    if (typeof window.stopBrowserDictation === "function") window.stopBrowserDictation("chat");
    if (typeof window.stopChatSpeech === "function") window.stopChatSpeech();

    const userBubble = window.appendBubble(els.chatMessages, "user", trimmedMessage);
    els.chatInput.value = "";
    els.chatCorrection.textContent = "Noch keine Korrektur.";
    window.renderTips(els.chatTips, []);

    const assistantBubble = window.appendBubble(els.chatMessages, "assistant", "Der Tutor denkt nach ...", "pending");
    state.chatRequestInFlight = true;
    state.chatRequestController = controller;
    state.tutorStreamController = controller;
    state.chatPendingBubble = assistantBubble;
    window.setTutorSessionState?.("thinking", {
      transport: "stream",
      activeTurnId: turnId,
      hasReceivedContent: false,
      lastError: "",
    });
    window.setChatStatus?.("Tutor antwortet ...", "busy");
    window.updateChatComposerState?.();
    const audioRuntime = ensureAudioRuntime({ turnId, source: "stream" });
    if (state.chatTtsEnabled) {
      if (audioRuntime.localEligible) setChatVoiceStatus("Wiedergabe wird vorbereitet.");
      else if (browserTutorFallbackAllowed()) setChatVoiceStatus("Systemstimme bereit.");
      else setChatVoiceStatus("Wiedergabe nicht verfügbar.");
    }

    let assistantText = "";
    let finalText = "";
    let hasReceivedContent = false;
    let completed = false;
    let refreshHistoryAfterDone = false;
    let reloadTranscriptConversationId = "";

    const promotePendingBubble = () => {
      renderBubble(assistantBubble, "assistant", assistantText || "Der Tutor denkt nach ...");
      state.chatPendingBubble = assistantBubble;
    };

    try {
      const response = await window.fetch(STREAM_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmedMessage,
          conversation_id: state.conversationId,
          level: els.globalLevel.value,
          mode: typeof window.getMainTutorMode === "function" ? window.getMainTutorMode() : "fluidez",
          persona_key: typeof window.getTutorConversationPersonaKey === "function"
            ? window.getTutorConversationPersonaKey()
            : "studio",
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errorMessage = await buildApiErrorMessage(response);
        throw buildFallbackError(errorMessage);
      }
      if (!response.body || typeof response.body.getReader !== "function") {
        throw buildFallbackError("Streaming-Antwort konnte im Browser nicht gelesen werden.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const handleEvent = async (event) => {
        if (state.tutorSession?.activeTurnId !== turnId) return;
        const type = String(event?.type || "");
        if (type === "session") {
          if (typeof event.conversation_id === "string" && event.conversation_id.trim()) {
            state.conversationId = event.conversation_id;
          }
          return;
        }
        if (type === "state") {
          if (event.state === "thinking") {
            window.setTutorSessionState?.("thinking", {
              transport: "stream",
              activeTurnId: turnId,
              hasReceivedContent,
              lastError: "",
            });
          }
          if (event.state === "streaming") {
            window.setTutorSessionState?.("streaming", {
              transport: "stream",
              activeTurnId: turnId,
              hasReceivedContent: true,
              lastError: "",
            });
          }
          return;
        }
        if (type === "delta") {
          const chunkText = String(event.text || "");
          if (!chunkText) return;
          hasReceivedContent = true;
          assistantText += chunkText;
          promotePendingBubble();
          window.setTutorSessionState?.("streaming", {
            transport: "stream",
            activeTurnId: turnId,
            hasReceivedContent: true,
            lastError: "",
          });
          return;
        }
        if (type === "sentence") {
          const sentenceText = normalizeTextForSegmentation(event.text);
          const sentenceIndex = Number.isInteger(event.sentence_index) ? event.sentence_index : -1;
          if (!sentenceText) return;
          if (sentenceIndex >= 0 && sentenceIndex < audioRuntime.sentenceIndex) return;
          queueTutorSpeechChunks(audioRuntime, [sentenceText]);
          return;
        }
        if (type === "final") {
          finalText = String(event.text || "").trim();
          if (finalText) {
            assistantText = finalText;
            hasReceivedContent = true;
            renderBubble(assistantBubble, "assistant", finalText);
            state.chatLastAssistantReply = finalText;
            window.setTutorSessionState?.("streaming", {
              transport: "stream",
              activeTurnId: turnId,
              hasReceivedContent: true,
              lastError: "",
            });
            reconcilePendingSpeechWithFinalText(audioRuntime, finalText);
          }
          return;
        }
        if (type === "correction") {
          els.chatCorrection.textContent = String(event.text || "").trim() || "Keine unmittelbare Korrektur.";
          return;
        }
        if (type === "tips") {
          window.renderTips(els.chatTips, Array.isArray(event.items) ? event.items : []);
          return;
        }
        if (type === "done") {
          completed = true;
          const latencyMs = Math.round(nowMs() - requestStartedAt);
          if (!finalText && assistantText.trim()) {
            finalText = assistantText.trim();
            renderBubble(assistantBubble, "assistant", finalText);
            state.chatLastAssistantReply = finalText;
          }
          const committedReply = finalText || assistantText.trim();
          const committedConversationId = String(event.conversation_id || state.conversationId || "").trim();
          try {
            await commitStreamedTurn({
              conversationId: committedConversationId,
              message: trimmedMessage,
              reply: committedReply,
              level: els.globalLevel.value,
            });
          } catch (commitError) {
            clearActiveRequestRefs(controller, assistantBubble, { keepPendingBubble: false });
            window.setTutorSessionState?.("error", {
              transport: "none",
              activeTurnId: null,
              hasReceivedContent: Boolean(committedReply),
              lastError: commitError?.message || "Tutor-Antwort konnte nicht gespeichert werden.",
            });
            window.setChatStatus?.(
              `Antwort empfangen, aber Verlauf konnte nicht gespeichert werden: ${commitError?.message || "unbekannter Fehler"}`,
              "error",
            );
            window.stopTutorAudio({ cancelBrowser: true, silent: true });
            return;
          }
          refreshHistoryAfterDone = true;
          reloadTranscriptConversationId = committedConversationId;
          if (finalText || assistantText.trim()) state.chatHasCompletedAssistantTurn = true;
          clearActiveRequestRefs(controller, assistantBubble, { keepPendingBubble: false });
          window.setTutorSessionState?.("idle", { ...idleSessionPatch });
          window.setChatStatus?.(
            `Antwort erhalten (${(latencyMs / 1000).toFixed(latencyMs >= 10000 ? 0 : 1)} s).`,
            "success",
          );
          completeTutorSpeechTurn(audioRuntime, finalText || assistantText.trim());
          return;
        }
        if (type === "error") {
          throw new Error(String(event.detail || "Chat-Streaming fehlgeschlagen."));
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          await handleEvent(JSON.parse(trimmed));
        }
      }

      buffer += decoder.decode();
      if (buffer.trim()) await handleEvent(JSON.parse(buffer.trim()));

      if (!completed) {
        throw new Error("Tutor-Streaming wurde unerwartet beendet.");
      }
    } catch (error) {
      const abortReason = controller.__tutorAbortReason || "";
      window.clearTimeout(timeoutId);

      if (abortReason === "interrupted") {
        return;
      }

      const errorMessage = error?.message || "Tutor-Streaming fehlgeschlagen.";
      if (!hasReceivedContent && !completed) {
        if (userBubble?.isConnected) userBubble.remove();
        if (assistantBubble?.isConnected) assistantBubble.remove();
        els.chatInput.value = trimmedMessage;
        clearActiveRequestRefs(controller, assistantBubble, { keepPendingBubble: false });
        window.setTutorSessionState?.("idle", { ...idleSessionPatch });
        window.stopTutorAudio({ cancelBrowser: true, silent: true });
        throw buildFallbackError(errorMessage);
      }

      const partialText = finalText || assistantText || "Antwort konnte nicht abgeschlossen werden.";
      renderBubble(assistantBubble, partialText === "Antwort konnte nicht abgeschlossen werden." ? "system" : "assistant", partialText, "stream-error", "Verbindung verloren.");
      clearActiveRequestRefs(controller, assistantBubble, { keepPendingBubble: false });
      window.setTutorSessionState?.("error", {
        transport: "none",
        activeTurnId: null,
        hasReceivedContent,
        lastError: errorMessage,
      });
      window.stopTutorAudio({ cancelBrowser: true, silent: true });
      window.setChatStatus?.(errorMessage, "error");
      return;
    } finally {
      window.clearTimeout(timeoutId);
      if (refreshHistoryAfterDone) {
        window.refreshChatHistory?.().catch((historyError) => {
          window.setStatus?.(`Chatverlauf konnte nicht aktualisiert werden: ${historyError.message}`);
        });
        if (reloadTranscriptConversationId) {
          window.reloadActiveChatTranscript?.({
            silent: true,
            conversationId: reloadTranscriptConversationId,
            applyIfConversationChanged: false,
          }).catch((transcriptError) => {
            window.setStatus?.(`Aktiver Verlauf konnte nicht aktualisiert werden: ${transcriptError.message}`);
          });
        }
      }
    }
  };
})();
