(() => {
  window.TUTOR_PORTRAIT_DEBUG = window.TUTOR_PORTRAIT_DEBUG || {
    enabled: true,
  };
  const PORTRAIT_DEBUG = window.TUTOR_PORTRAIT_DEBUG;
  const PERSONA_PRESETS = {
    woman: {
      title: "Woman portrait",
      copy: "Portrait assets for the woman tutor are not installed yet.",
      accent: "#72ddd3",
      accentSoft: "rgba(114, 221, 211, 0.28)",
      driftOffset: 0.35,
      presenceBase: 0.36,
    },
    man: {
      title: "Man portrait",
      copy: "Portrait assets for the man tutor are not installed yet.",
      accent: "#d7ba84",
      accentSoft: "rgba(215, 186, 132, 0.24)",
      driftOffset: 1.55,
      presenceBase: 0.38,
    },
  };
  const PERSONA_ALIASES = {
    studio: "woman",
    coach: "man",
    examiner: "man",
    woman: "woman",
    female: "woman",
    man: "man",
    male: "man",
  };
  const PORTRAIT_ASSET_SETS = {
    woman: {
      base: "/static/assets/tutor-portraits/woman-base.webp",
      blink: "/static/assets/tutor-portraits/woman-blink.webp",
      mouths: [
        "/static/assets/tutor-portraits/woman-mouth-1.webp",
        "/static/assets/tutor-portraits/woman-mouth-2.webp",
        "/static/assets/tutor-portraits/woman-mouth-3.webp",
        "/static/assets/tutor-portraits/woman-mouth-4.webp",
      ],
    },
    man: {
      base: "/static/assets/tutor-portraits/man-base.webp",
      blink: "/static/assets/tutor-portraits/man-blink.webp",
      mouths: [
        "/static/assets/tutor-portraits/man-mouth-1.webp",
        "/static/assets/tutor-portraits/man-mouth-2.webp",
        "/static/assets/tutor-portraits/man-mouth-3.webp",
        "/static/assets/tutor-portraits/man-mouth-4.webp",
      ],
    },
  };
  const PERSONAS = new Set(Object.keys(PERSONA_PRESETS));
  const STATES = new Set(["idle", "listening", "speaking"]);

  let animationFrame = 0;
  let nextBlinkAt = 0;
  let blinkStartedAt = 0;
  let blinkDurationMs = 160;
  let fallbackPulseActive = false;
  let fallbackPhase = 0;
  let targetSpeakingLevel = 0;
  let smoothedSpeakingLevel = 0;
  let debugLastAvatarState = "idle";
  let debugLastMouthFrame = 0;

  const assetResultCache = new Map();
  const assetPromiseCache = new Map();
  const assetDebugComparisonCache = new Map();
  const assetDebugComparisonPromiseCache = new Map();

  const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, Number(value) || 0));
  const portraitDebugEnabled = () => Boolean(PORTRAIT_DEBUG?.enabled);
  const logPortraitDebug = (eventName, payload = {}) => {
    if (!portraitDebugEnabled() || typeof console === "undefined" || typeof console.info !== "function") return;
    console.info("[TutorPortraitDebug]", eventName, payload);
  };
  const buffersMatch = (left, right) => {
    if (!(left instanceof Uint8Array) || !(right instanceof Uint8Array) || left.length !== right.length) return false;
    for (let index = 0; index < left.length; index += 1) {
      if (left[index] !== right[index]) return false;
    }
    return true;
  };
  const fetchAssetBytes = async (url) => {
    if (!url || typeof window.fetch !== "function") return null;
    try {
      const response = await window.fetch(url, { cache: "no-store" });
      if (!response.ok) return null;
      return new Uint8Array(await response.arrayBuffer());
    } catch {
      return null;
    }
  };

  const normalizePersona = (value) => {
    const key = String(value || "").trim().toLowerCase();
    const normalized = PERSONA_ALIASES[key] || "woman";
    return PERSONAS.has(normalized) ? normalized : "woman";
  };

  const normalizeState = (value) => {
    const key = String(value || "").trim().toLowerCase();
    return STATES.has(key) ? key : "idle";
  };
  const resolvePortraitAssetSetKey = (personaKey) => normalizePersona(personaKey);

  const getAvatarStage = () => document.getElementById("tutorAvatarStage");

  const getPersonaPreset = (personaKey) => PERSONA_PRESETS[normalizePersona(personaKey)] || PERSONA_PRESETS.woman;

  const scheduleNextBlink = (now, { followup = false } = {}) => {
    blinkDurationMs = 135 + (Math.random() * 55);
    nextBlinkAt = now + (followup ? 120 + (Math.random() * 170) : 2600 + (Math.random() * 3400));
  };

  const computeBlinkAmount = (now) => {
    if (!nextBlinkAt) scheduleNextBlink(now);
    if (!blinkStartedAt && now >= nextBlinkAt) {
      blinkStartedAt = now;
    }
    if (!blinkStartedAt) return 0;
    const elapsed = now - blinkStartedAt;
    if (elapsed >= blinkDurationMs) {
      blinkStartedAt = 0;
      scheduleNextBlink(now, { followup: Math.random() < 0.16 });
      return 0;
    }
    return Math.sin((elapsed / blinkDurationMs) * Math.PI);
  };

  const loadImage = (url) => new Promise((resolve) => {
    if (!url) {
      resolve("");
      return;
    }
    const image = new Image();
    image.decoding = "async";
    image.onload = () => resolve(url);
    image.onerror = () => resolve("");
    image.src = url;
  });

  const ensureDebugAssetComparison = (assetSetKey, assetSet) => {
    if (!portraitDebugEnabled()) return Promise.resolve(null);
    if (assetDebugComparisonCache.has(assetSetKey)) return Promise.resolve(assetDebugComparisonCache.get(assetSetKey));
    if (assetDebugComparisonPromiseCache.has(assetSetKey)) return assetDebugComparisonPromiseCache.get(assetSetKey);

    const promise = Promise.all([
      fetchAssetBytes(assetSet?.base),
      ...((assetSet?.mouths || []).map((url) => fetchAssetBytes(url))),
    ]).then(([baseBytes, ...mouthBytes]) => {
      const mouthsDifferFromBase = mouthBytes.map((bytes) => {
        if (!bytes || !baseBytes) return null;
        return !buffersMatch(baseBytes, bytes);
      });
      const result = {
        portraitPack: assetSetKey,
        mouthsDifferFromBase,
        anyMouthDiffersFromBase: mouthsDifferFromBase.some((value) => value === true),
      };
      assetDebugComparisonCache.set(assetSetKey, result);
      assetDebugComparisonPromiseCache.delete(assetSetKey);
      logPortraitDebug("asset-compare", result);
      return result;
    });

    assetDebugComparisonPromiseCache.set(assetSetKey, promise);
    return promise;
  };

  const ensurePortraitAssets = (personaKey) => {
    const resolvedPersona = normalizePersona(personaKey);
    const assetSetKey = resolvePortraitAssetSetKey(resolvedPersona);
    if (assetResultCache.has(assetSetKey)) return Promise.resolve(assetResultCache.get(assetSetKey));
    if (assetPromiseCache.has(assetSetKey)) return assetPromiseCache.get(assetSetKey);

    const assetSet = PORTRAIT_ASSET_SETS[assetSetKey] || PORTRAIT_ASSET_SETS.woman;
    const promise = Promise.all([
      loadImage(assetSet.base),
      loadImage(assetSet.blink),
      ...((assetSet.mouths || []).map((url) => loadImage(url))),
    ]).then(([base, blink, ...mouths]) => {
      const resolvedMouths = mouths.filter(Boolean);
      const result = {
        base,
        blink,
        mouths,
        hasBase: Boolean(base),
        hasBlink: Boolean(blink),
        hasMouth: resolvedMouths.length > 0,
        mouthCount: resolvedMouths.length,
        debugAssetComparison: assetDebugComparisonCache.get(assetSetKey) || null,
      };
      assetResultCache.set(assetSetKey, result);
      assetPromiseCache.delete(assetSetKey);
      if (portraitDebugEnabled()) {
        void ensureDebugAssetComparison(assetSetKey, assetSet).then((comparison) => {
          result.debugAssetComparison = comparison;
        });
      }
      return result;
    });

    assetPromiseCache.set(assetSetKey, promise);
    return promise;
  };

  const getStageParts = (stage) => ({
    base: stage.querySelector("[data-portrait-layer='base']"),
    blink: stage.querySelector("[data-portrait-layer='blink']"),
    mouth: stage.querySelector("[data-portrait-layer='mouth']"),
    placeholderTitle: stage.querySelector("[data-portrait-placeholder='title']"),
    placeholderCopy: stage.querySelector("[data-portrait-placeholder='copy']"),
    placeholderStatus: stage.querySelector("[data-portrait-placeholder='status']"),
  });

  const renderAvatarStage = () => {
    const stage = getAvatarStage();
    if (!stage || stage.dataset.avatarMounted === "true") return stage;
    stage.innerHTML = `
      <div class="tutor-portrait-scene">
        <div class="tutor-portrait-backdrop"></div>
        <div class="tutor-portrait-presence"></div>
        <div class="tutor-portrait-frame">
          <div class="tutor-portrait-layer tutor-portrait-layer-base" data-portrait-layer="base"></div>
          <div class="tutor-portrait-layer tutor-portrait-layer-blink" data-portrait-layer="blink"></div>
          <div class="tutor-portrait-layer tutor-portrait-layer-mouth" data-portrait-layer="mouth"></div>
          <div class="tutor-portrait-placeholder">
            <p class="tutor-portrait-placeholder-kicker">Portrait stage</p>
            <strong class="tutor-portrait-placeholder-title" data-portrait-placeholder="title">Woman portrait</strong>
            <p class="tutor-portrait-placeholder-copy" data-portrait-placeholder="copy">
              Portrait assets for the woman tutor are not installed yet.
            </p>
            <span class="tutor-portrait-placeholder-status" data-portrait-placeholder="status">Waiting for portrait assets.</span>
          </div>
        </div>
      </div>
    `;
    stage.dataset.avatarMounted = "true";
    stage.dataset.portraitStatus = "loading";
    return stage;
  };

  const applyPersonaPlaceholderCopy = (stage, personaKey) => {
    const preset = getPersonaPreset(personaKey);
    const parts = getStageParts(stage);
    if (parts.placeholderTitle) parts.placeholderTitle.textContent = preset.title;
    if (parts.placeholderCopy) parts.placeholderCopy.textContent = preset.copy;
  };

  const resolveMouthFrameUrl = (assetState, frameNumber) => {
    if (!assetState?.hasMouth) return "";
    const mouths = Array.isArray(assetState.mouths) ? assetState.mouths : [];
    const preferredIndex = Math.max(0, Math.min(3, Number(frameNumber || 1) - 1));
    if (mouths[preferredIndex]) return mouths[preferredIndex];
    for (let offset = 1; offset < mouths.length; offset += 1) {
      const lowerIndex = preferredIndex - offset;
      const upperIndex = preferredIndex + offset;
      if (lowerIndex >= 0 && mouths[lowerIndex]) return mouths[lowerIndex];
      if (upperIndex < mouths.length && mouths[upperIndex]) return mouths[upperIndex];
    }
    return "";
  };

  const applyPortraitMouthFrame = (stage, assetState, frameNumber) => {
    if (!stage) return;
    const parts = getStageParts(stage);
    if (!parts.mouth) return;
    const resolvedFrame = Math.max(0, Math.min(4, Number(frameNumber) || 0));
    if (resolvedFrame <= 0 || !assetState?.hasMouth) {
      if (parts.mouth.dataset.activeUrl) {
        parts.mouth.style.backgroundImage = "none";
        parts.mouth.dataset.activeUrl = "";
      }
      stage.dataset.portraitActiveMouthFrame = "0";
      return;
    }

    const nextUrl = resolveMouthFrameUrl(assetState, resolvedFrame);
    if (!nextUrl) {
      if (parts.mouth.dataset.activeUrl) {
        parts.mouth.style.backgroundImage = "none";
        parts.mouth.dataset.activeUrl = "";
      }
      stage.dataset.portraitActiveMouthFrame = "0";
      return;
    }

    if (parts.mouth.dataset.activeUrl !== nextUrl) {
      parts.mouth.style.backgroundImage = `url("${nextUrl}")`;
      parts.mouth.dataset.activeUrl = nextUrl;
    }
    stage.dataset.portraitActiveMouthFrame = String(resolvedFrame);
  };

  const applyPortraitAssetState = (stage, personaKey, assetState) => {
    if (!stage) return;
    const parts = getStageParts(stage);
    const resolvedPersona = normalizePersona(personaKey);
    const assetSetKey = resolvePortraitAssetSetKey(resolvedPersona);
    const status = assetState?.hasBase
      ? (assetState.hasBlink || assetState.hasMouth ? "ready" : "base-only")
      : "missing";

    stage.dataset.avatarPersona = resolvedPersona;
    stage.dataset.portraitAssetSet = assetSetKey;
    stage.dataset.portraitStatus = status;
    stage.dataset.portraitBaseReady = assetState?.hasBase ? "true" : "false";
    stage.dataset.portraitBlinkReady = assetState?.hasBlink ? "true" : "false";
    stage.dataset.portraitMouthReady = assetState?.hasMouth ? "true" : "false";
    stage.__portraitAssetState = assetState || null;
    stage.__portraitAssetComparison = assetState?.debugAssetComparison || null;

    if (parts.base) parts.base.style.backgroundImage = assetState?.base ? `url("${assetState.base}")` : "none";
    if (parts.blink) parts.blink.style.backgroundImage = assetState?.blink ? `url("${assetState.blink}")` : "none";
    if (parts.mouth) {
      parts.mouth.style.backgroundImage = "none";
      parts.mouth.dataset.activeUrl = "";
    }

    applyPersonaPlaceholderCopy(stage, resolvedPersona);
    if (parts.placeholderStatus) {
      if (status === "loading") parts.placeholderStatus.textContent = "Loading portrait assets.";
      else if (status === "ready") parts.placeholderStatus.textContent = "Portrait assets ready.";
      else if (status === "base-only") parts.placeholderStatus.textContent = "Base portrait ready.";
      else parts.placeholderStatus.textContent = "Portrait assets not installed yet.";
    }
  };

  const syncPortraitAssets = (stage, personaKey) => {
    if (!stage) return;
    const resolvedPersona = normalizePersona(personaKey);
    const assetSetKey = resolvePortraitAssetSetKey(resolvedPersona);
    const cached = assetResultCache.get(assetSetKey);
    if (cached) {
      applyPortraitAssetState(stage, resolvedPersona, cached);
      return;
    }

    stage.dataset.avatarPersona = resolvedPersona;
    stage.dataset.portraitAssetSet = assetSetKey;
    stage.dataset.portraitStatus = "loading";
    stage.dataset.portraitBaseReady = "false";
    stage.dataset.portraitBlinkReady = "false";
    stage.dataset.portraitMouthReady = "false";
    stage.__portraitAssetState = null;
    applyPersonaPlaceholderCopy(stage, resolvedPersona);

    ensurePortraitAssets(resolvedPersona).then((assetState) => {
      const liveStage = getAvatarStage();
      if (!liveStage) return;
      const livePersona = normalizePersona(window.state?.tutorAvatar);
      if (livePersona !== resolvedPersona) return;
      applyPortraitAssetState(liveStage, resolvedPersona, assetState);
      window.syncTutorAvatarPresentation?.();
    });
  };

  const isSpeaking = () => {
    const audioMode = String(window.state?.tutorAudio?.mode || "").trim().toLowerCase();
    return audioMode === "speaking" || (audioMode === "fallback" && window.state?.tutorAudio?.fallbackInUse);
  };

  const computeAvatarState = () => {
    if (isSpeaking()) return "speaking";
    const tutorState = String(window.state?.tutorSession?.state || "").trim().toLowerCase();
    if (tutorState === "listening" || tutorState === "transcribing") return "listening";
    return "idle";
  };

  const getEffectiveSpeakingLevel = () => {
    if (fallbackPulseActive) {
      fallbackPhase += 0.18;
      return 0.32 + (((Math.sin(fallbackPhase) + 1) / 2) * 0.46);
    }
    return clamp(targetSpeakingLevel);
  };

  const getMouthFrame = (now, level, avatarState) => {
    if (avatarState !== "speaking") return 0;
    const speakingLevel = clamp(level);
    if (speakingLevel <= 0.08) return 0;
    const rhythmicFrames = [1, 2, 3, 2, 4, 3, 2, 1];
    const cadenceFrame = rhythmicFrames[Math.floor((Number(now) || 0) / 88) % rhythmicFrames.length];
    const amplitudeFrame = speakingLevel <= 0.24
      ? 1
      : speakingLevel <= 0.44
        ? 2
        : speakingLevel <= 0.68
          ? 3
          : 4;
    return Math.max(1, Math.min(4, Math.round((cadenceFrame + amplitudeFrame) / 2)));
  };

  const getSpeakingMotion = (now, level, avatarState, assetComparison = null) => {
    if (avatarState !== "speaking" || assetComparison?.anyMouthDiffersFromBase !== true) {
      return {
        frame: 0,
        shiftY: 0,
        scaleX: 1,
        scaleY: 1,
        opacity: 0,
      };
    }
    const speakingLevel = Math.max(clamp(level), 0.14);
    const rhythmicLift = ((Math.sin((Number(now) || 0) * 0.022) + 1) / 2) * 0.34;
    return {
      frame: getMouthFrame(now, speakingLevel, avatarState),
      shiftY: 1.2 + (speakingLevel * 4.8) + rhythmicLift,
      scaleX: 1 - (speakingLevel * 0.08),
      scaleY: 1 + (speakingLevel * 0.2) + (rhythmicLift * 0.06),
      opacity: 0.42 + (speakingLevel * 0.56),
    };
  };

  const applyAvatarFrame = (now) => {
    const stage = renderAvatarStage();
    if (!stage) return;

    const personaKey = normalizePersona(window.state?.tutorAvatar);
    const assetSetKey = resolvePortraitAssetSetKey(personaKey);
    const preset = getPersonaPreset(personaKey);
    const avatarState = normalizeState(computeAvatarState());
    syncPortraitAssets(stage, personaKey);

    const blinkAmount = computeBlinkAmount(now);
    const targetLevel = avatarState === "speaking" ? Math.max(getEffectiveSpeakingLevel(), 0.14) : 0;
    const smoothing = targetLevel > smoothedSpeakingLevel ? 0.26 : 0.18;
    smoothedSpeakingLevel += (targetLevel - smoothedSpeakingLevel) * smoothing;
    if (avatarState !== "speaking" && smoothedSpeakingLevel < 0.01) smoothedSpeakingLevel = 0;

    const breath = Math.sin((now * 0.00115) + preset.driftOffset);
    const drift = Math.sin((now * 0.00065) + preset.driftOffset);
    const driftSecondary = Math.cos((now * 0.00092) + preset.driftOffset);
    const listeningWeight = avatarState === "listening" ? 1 : 0;
    const speakingWeight = avatarState === "speaking" ? 1 : 0;

    const headX = (drift * 1.1) + (driftSecondary * 0.35);
    const headY = (-1.1 - (breath * 1.2)) - (listeningWeight * 0.9);
    const headTilt = (drift * 0.9) + (listeningWeight * -0.45) + (speakingWeight * 0.1);
    const breathScale = 1 + (breath * 0.012) + (speakingWeight * 0.008);
    const presence = clamp(
      preset.presenceBase + (listeningWeight * 0.2) + (speakingWeight * 0.34),
      0.2,
      1,
    );
    const assetComparison = stage.__portraitAssetComparison || stage.__portraitAssetState?.debugAssetComparison || null;
    const speakingMotion = getSpeakingMotion(now, smoothedSpeakingLevel, avatarState, assetComparison);

    stage.dataset.avatarPersona = personaKey;
    stage.dataset.avatarState = avatarState;
    stage.style.setProperty("--portrait-accent", preset.accent);
    stage.style.setProperty("--portrait-accent-soft", preset.accentSoft);
    stage.style.setProperty("--portrait-drift-x", `${headX.toFixed(2)}px`);
    stage.style.setProperty("--portrait-drift-y", `${headY.toFixed(2)}px`);
    stage.style.setProperty("--portrait-tilt", `${headTilt.toFixed(2)}deg`);
    stage.style.setProperty("--portrait-breath-scale", breathScale.toFixed(4));
    stage.style.setProperty("--portrait-presence", presence.toFixed(3));
    stage.style.setProperty("--portrait-blink-opacity", blinkAmount.toFixed(3));
    stage.style.setProperty("--portrait-blink-veil", (blinkAmount * 0.72).toFixed(3));
    stage.style.setProperty("--portrait-listening-focus", (listeningWeight + (speakingWeight * 0.34)).toFixed(3));
    stage.style.setProperty("--portrait-mouth-open", smoothedSpeakingLevel.toFixed(3));
    stage.style.setProperty("--portrait-mouth-shift-y", `${speakingMotion.shiftY.toFixed(2)}px`);
    stage.style.setProperty("--portrait-mouth-scale-x", speakingMotion.scaleX.toFixed(3));
    stage.style.setProperty("--portrait-mouth-scale-y", speakingMotion.scaleY.toFixed(3));
    stage.style.setProperty("--portrait-mouth-opacity", speakingMotion.opacity.toFixed(3));
    stage.style.setProperty("--portrait-mouth-frame", String(speakingMotion.frame));
    applyPortraitMouthFrame(stage, stage.__portraitAssetState, speakingMotion.frame);

    if (portraitDebugEnabled()) {
      if (avatarState !== debugLastAvatarState) {
        if (avatarState === "speaking" || debugLastAvatarState === "speaking") {
          logPortraitDebug(avatarState === "speaking" ? "speaking-on" : "speaking-off", {
            avatarState,
            audioMode: String(window.state?.tutorAudio?.mode || "").trim().toLowerCase(),
            visibleIdentity: personaKey,
            portraitPack: assetSetKey,
            mouthFrame: speakingMotion.frame,
            mouthsDifferFromBase: assetComparison?.mouthsDifferFromBase || null,
            anyMouthDiffersFromBase: assetComparison?.anyMouthDiffersFromBase ?? null,
          });
        }
        debugLastAvatarState = avatarState;
        if (avatarState !== "speaking") debugLastMouthFrame = 0;
      }
      if (avatarState === "speaking" && speakingMotion.frame !== debugLastMouthFrame) {
        debugLastMouthFrame = speakingMotion.frame;
        logPortraitDebug("mouth-frame", {
          visibleIdentity: personaKey,
          portraitPack: assetSetKey,
          mouthFrame: speakingMotion.frame,
          speakingLevel: Number(smoothedSpeakingLevel.toFixed(3)),
          mouthsDifferFromBase: assetComparison?.mouthsDifferFromBase || null,
          anyMouthDiffersFromBase: assetComparison?.anyMouthDiffersFromBase ?? null,
        });
      }
    }
  };

  const tick = (timestamp) => {
    applyAvatarFrame(Number(timestamp) || performance.now());
    animationFrame = window.requestAnimationFrame(tick);
  };

  window.initTutorAvatarStage = function initTutorAvatarStage() {
    const stage = renderAvatarStage();
    if (!stage) return;
    if (!animationFrame) animationFrame = window.requestAnimationFrame(tick);
  };

  window.syncTutorAvatarPresentation = function syncTutorAvatarPresentation() {
    const stage = renderAvatarStage();
    if (!stage) return;
    if (!animationFrame) animationFrame = window.requestAnimationFrame(tick);
    applyAvatarFrame(performance.now());
  };

  window.setTutorAvatarSpeakingLevel = function setTutorAvatarSpeakingLevel(level) {
    targetSpeakingLevel = clamp(level);
  };

  window.setTutorAvatarPersona = function setTutorAvatarPersona(personaKey) {
    if (window.state) window.state.tutorAvatar = normalizePersona(personaKey);
    window.syncTutorAvatarPresentation?.();
  };

  window.startTutorAvatarFallbackPulse = function startTutorAvatarFallbackPulse() {
    fallbackPulseActive = true;
    fallbackPhase = 0;
  };

  window.stopTutorAvatarFallbackPulse = function stopTutorAvatarFallbackPulse() {
    fallbackPulseActive = false;
    targetSpeakingLevel = 0;
  };

  window.resetTutorAvatarActivity = function resetTutorAvatarActivity() {
    fallbackPulseActive = false;
    targetSpeakingLevel = 0;
    smoothedSpeakingLevel = 0;
    blinkStartedAt = 0;
    scheduleNextBlink(performance.now());
    window.syncTutorAvatarPresentation?.();
  };

  const init = () => {
    const stage = renderAvatarStage();
    if (!stage) return;
    scheduleNextBlink(performance.now());
    const chatPanel = document.getElementById("tab-chat");
    if (chatPanel && typeof MutationObserver !== "undefined") {
      const observer = new MutationObserver(() => {
        window.syncTutorAvatarPresentation?.();
      });
      observer.observe(chatPanel, {
        attributes: true,
        attributeFilter: ["data-tutor-session-state"],
      });
    }
    window.initTutorAvatarStage?.();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
