// Run offline with: node --test tests/test_browser_tts.cjs (no npm packages).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const assets = path.join(__dirname, "..", "static", "assets");
const features = fs.readFileSync(path.join(assets, "app-features.js"), "utf8");
const speechFeatures = features.slice(
  features.indexOf("window.chatSpeechSupported ="),
  features.indexOf("window.loadSelectedConversation ="),
);
const runtime = fs.readFileSync(path.join(assets, "tutor-runtime.js"), "utf8");
const voice = (name, lang = "de-DE") => ({ name, voiceURI: name, lang, localService: true });

function harness(initialVoices = [], { supported = true, eventListener = true } = {}) {
  let voices = initialVoices;
  let nextTimer = 0;
  let userGesture = false;
  const timers = new Map();
  const listeners = [];
  const spoken = [];
  const clickHandlers = new Map();
  const element = () => ({ textContent: "", value: "", disabled: false });
  const state = {
    config: { tutor_tts_fallback: "browser", tutor_local_tts_available: false },
    chatTtsEnabled: true,
    chatVoiceCatalog: [],
    chatVoiceGender: "female",
    chatVoiceVariant: "standard",
    chatVoiceRegion: "de-DE",
    chatLastAssistantReply: "Hallo! Ich wohne in Bern.",
    tutorAudio: {},
  };
  const els = {
    chatVoiceStatus: element(), chatVoiceSummary: element(), chatTtsBtn: element(),
    chatReplayBtn: { ...element(), addEventListener: (event, handler) => clickHandlers.set(event, handler) },
  };
  const synthesis = {
    getVoices: () => voices,
    cancel() {},
    paused: false,
    resume() { this.paused = false; this.resumed = true; },
    speak(utterance) { spoken.push({ utterance, userGesture }); },
    onvoiceschanged: null,
  };
  if (eventListener) synthesis.addEventListener = (event, handler) => {
    assert.equal(event, "voiceschanged");
    listeners.push(handler);
  };
  const context = {
    state, els,
    console: { info() {} },
    TUTOR_IDENTITY_VOICE_DEBUG: { enabled: false },
    setTimeout(fn, delay) { const id = ++nextTimer; timers.set(id, { fn, delay }); return id; },
    clearTimeout(id) { timers.delete(id); },
    updateChatComposerState() {},
    writeUiPreferences() {},
    escapeHtml: (text) => text,
    t: (key) => key,
  };
  if (supported) {
    context.speechSynthesis = synthesis;
    context.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  }
  context.window = context;
  vm.createContext(context);
  vm.runInContext(speechFeatures, context, { filename: "app-features.js:speech" });
  vm.runInContext(runtime, context, { filename: "tutor-runtime.js" });
  // Execute the production click binding, rather than calling a copied handler.
  const replayBinding = features.match(/els\.chatReplayBtn\?\.addEventListener\("click", repeatLastChatReply\);/);
  assert.ok(replayBinding, "The actual replay button must be bound directly");
  vm.runInContext(replayBinding[0], context);
  return {
    context, state, els, synthesis, spoken, timers, listeners,
    setVoices(newVoices) { voices = newVoices; },
    voicesChanged() {
      for (const listener of listeners) listener({ type: "voiceschanged" });
      synthesis.onvoiceschanged?.({ type: "voiceschanged" });
    },
    clickReplay() {
      userGesture = true;
      try { clickHandlers.get("click")(); } finally { userGesture = false; }
    },
    fireTimers(delay) {
      for (const [id, timer] of [...timers]) {
        if (timer.delay === delay) { timers.delete(id); timer.fn(); }
      }
    },
  };
}

test("preserves the exact Katja match ahead of other German voices", () => {
  const katja = voice("Microsoft Katja Online (Natural) - German (Germany)");
  const h = harness([voice("Anna"), katja]);
  const resolution = h.context.resolveTutorBrowserVoice("woman");
  assert.equal(resolution.voiceEntry.voice, katja);
  assert.equal(resolution.method, "exact-machine-match");
});

for (const lang of ["de-DE", "de-CH", "de-AT", "de-LI", "de", "DE-de"]) {
  test(`speaks with an unknown-gender system voice in ${lang}`, () => {
    const german = voice("System voice", lang);
    const h = harness([voice("English", "en-US"), german]);
    h.clickReplay();
    assert.equal(h.spoken.length, 1);
    assert.equal(h.spoken[0].utterance.voice, german);
    assert.equal(h.spoken[0].utterance.lang, lang);
    assert.equal(h.spoken[0].userGesture, true);
  });
}

for (const [identity, expected] of [["woman", "Anna"], ["man", "Markus"], ["male", "Markus"]]) {
  test(`prefers an identifiable voice for ${identity}`, () => {
    const h = harness([voice("System voice"), voice("Anna"), voice("Markus")]);
    assert.equal(h.context.resolveTutorBrowserVoice(identity).voiceEntry.name, expected);
  });
}

test("male persona still speaks when only a female German voice is available", () => {
  const h = harness([voice("Anna")]);
  h.state.chatVoiceGender = "male";
  h.clickReplay();
  assert.equal(h.spoken[0].utterance.voice.name, "Anna");
});

test("never selects a non-German locale based on a misleading name", () => {
  const h = harness([voice("Germany Austria Swiss voice", "en-US")]);
  h.clickReplay();
  assert.equal(h.spoken.length, 0);
  assert.match(h.els.chatVoiceStatus.textContent, /Keine deutsche.*Spracheinstellungen/);
  assert.match(h.els.chatVoiceSummary.textContent, /Keine deutsche/);
});

test("refreshes stale voice inventories on replay", () => {
  const h = harness([voice("Old voice")]);
  h.context.bindChatTtsVoices();
  const replacement = voice("New voice", "de-CH");
  h.setVoices([replacement]);
  h.clickReplay();
  assert.equal(h.spoken[0].utterance.voice, replacement);
});

test("voiceschanged resumes pending speech without replacing other listeners", () => {
  const h = harness();
  let existingCalls = 0;
  h.synthesis.onvoiceschanged = () => { existingCalls += 1; };
  h.clickReplay();
  assert.equal(h.spoken.length, 0);
  assert.match(h.els.chatVoiceStatus.textContent, /geladen/);
  h.setVoices([voice("Android system voice")]);
  h.voicesChanged();
  assert.equal(h.spoken.length, 1);
  assert.equal(h.spoken[0].utterance.text, h.state.chatLastAssistantReply);
  assert.equal(existingCalls, 1);
  assert.equal(h.listeners.length, 1);
  h.voicesChanged();
  assert.equal(h.spoken.length, 1, "voice updates must not replay an already spoken response");
});

test("supports the older onvoiceschanged API and preserves its existing handler", () => {
  const h = harness([], { eventListener: false });
  let existingCalls = 0;
  h.synthesis.onvoiceschanged = () => { existingCalls += 1; };
  h.clickReplay();
  h.setVoices([voice("iOS system voice")]);
  h.voicesChanged();
  assert.equal(existingCalls, 1);
  assert.equal(h.spoken.length, 1);
});

test("only the newest reply is retained while voices are loading", () => {
  const h = harness();
  h.context.playTutorReplyAudio("Erste Antwort.");
  h.context.playTutorReplyAudio("Zweite Antwort.");
  h.setVoices([voice("System voice")]);
  h.voicesChanged();
  assert.equal(h.spoken.length, 1);
  assert.equal(h.spoken[0].utterance.text, "Zweite Antwort.");
});

test("bounded polling recovers if voices load without a voiceschanged event", () => {
  const h = harness();
  h.clickReplay();
  h.setVoices([voice("System voice")]);
  h.fireTimers(3000);
  assert.equal(h.spoken.length, 1);
});

test("missing voices produce an actionable diagnostic after a bounded wait", () => {
  const h = harness();
  h.clickReplay();
  h.fireTimers(3000);
  assert.equal(h.spoken.length, 0);
  assert.match(h.els.chatVoiceStatus.textContent, /Keine deutsche.*Spracheinstellungen/);
  assert.match(h.els.chatVoiceSummary.textContent, /Keine deutsche/);
  assert.equal(h.timers.size, 0);
});

test("late voices remain usable after the initial loading timeout", () => {
  const h = harness();
  h.clickReplay();
  h.fireTimers(3000);
  h.setVoices([voice("System voice")]);
  h.voicesChanged();
  h.clickReplay();
  assert.equal(h.spoken.length, 1);
  assert.equal(h.spoken[0].userGesture, true);
});

test("unsupported browser reports a diagnostic rather than silently returning", () => {
  const h = harness([], { supported: false });
  h.context.speakChatReply("Hallo!");
  assert.match(h.els.chatVoiceStatus.textContent, /Browser.*keine Sprachausgabe.*Versuche/);
  assert.match(h.els.chatVoiceSummary.textContent, /Browser.*keine Sprachausgabe/);
});

test("subsequent completed replies also reach browser speech when audio is enabled", () => {
  const h = harness([voice("System voice")]);
  for (const text of ["Hallo, ich heiße Mia.", "Ich wohne in Bern.", "Du heißt Mia."]) {
    assert.equal(h.context.playTutorReplyAudio(text, { source: "blocking" }), true);
    const utterance = h.spoken.at(-1).utterance;
    assert.equal(utterance.text, text);
    assert.equal(h.state.chatSpeechUtterance, utterance);
    utterance.onstart();
    assert.equal(h.state.tutorAudio.mode, "fallback");
    utterance.onend();
    assert.equal(h.state.tutorAudio.mode, "idle");
    assert.equal(h.state.chatSpeechUtterance, null);
  }
  assert.equal(h.spoken.length, 3);
  assert.equal(h.state.chatLastAssistantReply, "Du heißt Mia.");
});

test("streamed replies are spoken once after the final text is committed", async () => {
  const h = harness([voice("System voice")]);
  const commits = [];
  const replies = ["Hallo, Mia!", "Du wohnst in Bern."];
  Object.assign(h.els, {
    chatInput: { value: "" }, chatCorrection: { textContent: "" },
    chatTips: {}, chatMessages: {}, globalLevel: { value: "A1" },
  });
  Object.assign(h.context, {
    AbortController, TextDecoder, ReadableStream,
    appendBubble: () => ({ innerHTML: "", className: "" }),
    renderTips() {},
    setTutorSessionState: (name, patch) => { h.state.tutorSession = { name, ...patch }; },
    fetch: async (url, options) => {
      if (url === "/api/tutor/chat/commit") {
        assert.equal(h.spoken.length, commits.length, "speech must follow the commit");
        commits.push(JSON.parse(options.body));
        return { ok: true };
      }
      assert.equal(url, "/api/tutor/chat/stream");
      const text = replies[commits.length];
      const events = [
        { type: "session", conversation_id: "synthetic-conversation" },
        { type: "delta", text: text.slice(0, 5) },
        { type: "delta", text: text.slice(5) },
        { type: "final", text },
        { type: "done", conversation_id: "synthetic-conversation", finish_reason: "stop" },
      ];
      const bytes = Buffer.from(events.map((event) => JSON.stringify(event) + "\n").join(""));
      let read = false;
      return { ok: true, body: { getReader: () => ({ read: async () => {
        if (read) return { done: true };
        read = true;
        return { done: false, value: bytes };
      } }) } };
    },
  });
  for (const reply of replies) {
    await h.context.sendTutorStreamMessage("Ich übe Deutsch.");
    assert.equal(h.spoken.length, commits.length);
    assert.equal(commits.at(-1).reply, reply);
    const utterance = h.spoken.at(-1).utterance;
    assert.equal(utterance.text, reply);
    utterance.onstart();
    utterance.onend();
  }
  assert.equal(commits.length, 2);
  assert.equal(h.state.chatLastAssistantReply, replies[1]);
});

test("text, quotes and Unicode pass unchanged to the speech engine", () => {
  const h = harness([voice("System voice")]);
  const text = '„Grüezi!“ Ich übe Deutsch. Wie heißt du?';
  h.context.speakChatReply(text);
  assert.equal(h.spoken[0].utterance.text, text);
});

test("audio off cancels pending voice loading and prevents later automatic speech", () => {
  const h = harness();
  h.clickReplay();
  h.context.toggleChatTts();
  h.setVoices([voice("System voice")]);
  h.voicesChanged();
  h.context.playTutorReplyAudio("Nicht sprechen.");
  assert.equal(h.spoken.length, 0);
  assert.equal(h.timers.size, 0);
});

test("runtime cancellation also cancels speech queued for delayed voices", () => {
  const h = harness();
  h.clickReplay();
  h.context.stopTutorAudio({ cancelBrowser: true, silent: true });
  h.setVoices([voice("System voice")]);
  h.voicesChanged();
  assert.equal(h.spoken.length, 0);
  assert.equal(h.timers.size, 0);
});

test("cancelled utterance callbacks cannot overwrite a newer reply's state", () => {
  const h = harness([voice("System voice")]);
  h.context.speakChatReply("Erste Antwort.");
  const first = h.spoken[0].utterance;
  h.context.speakChatReply("Zweite Antwort.");
  const second = h.spoken[1].utterance;
  second.onstart();
  first.onerror({ error: "canceled" });
  first.onend();
  assert.equal(h.state.chatSpeechUtterance, second);
  assert.equal(h.state.tutorAudio.mode, "fallback");
});

test("browser autoplay rejection asks for a real replay tap", () => {
  const h = harness([voice("System voice")]);
  h.context.speakChatReply("Hallo!");
  h.spoken[0].utterance.onerror({ error: "not-allowed" });
  assert.match(h.els.chatVoiceStatus.textContent, /blockiert.*Letzte Antwort.*erlaube/);
  assert.equal(h.state.chatSpeechUtterance, null);
  h.clickReplay();
  assert.equal(h.spoken[1].userGesture, true);
});

test("voice and language errors include an actionable diagnostic", () => {
  const h = harness([voice("System voice")]);
  h.clickReplay();
  h.spoken[0].utterance.onerror({ error: "voice-unavailable" });
  assert.match(h.els.chatVoiceStatus.textContent, /voice-unavailable.*Systemstimme.*Letzte Antwort/);
});

test("a paused synthesis engine is resumed during the replay click", () => {
  const h = harness([voice("System voice")]);
  h.synthesis.paused = true;
  h.clickReplay();
  assert.equal(h.synthesis.resumed, true);
  assert.equal(h.spoken[0].userGesture, true);
});

test("synchronous synthesis exceptions are reported without escaping the click handler", () => {
  const h = harness([voice("System voice")]);
  h.synthesis.speak = () => { const error = new Error("Blocked"); error.name = "NotAllowedError"; throw error; };
  assert.doesNotThrow(() => h.clickReplay());
  assert.match(h.els.chatVoiceStatus.textContent, /NotAllowedError.*Letzte Antwort/);
  assert.equal(h.state.chatSpeechUtterance, null);
  assert.equal(h.timers.size, 0);
});

test("a browser that never starts speech gets a bounded diagnostic", () => {
  const h = harness([voice("System voice")]);
  h.clickReplay();
  h.fireTimers(5000);
  assert.match(h.els.chatVoiceStatus.textContent, /noch nicht gestartet.*Letzte Antwort.*Medienlautstärke/);
});

test("successful playback cancels the start diagnostic timer", () => {
  const h = harness([voice("System voice")]);
  h.clickReplay();
  h.spoken[0].utterance.onstart();
  h.fireTimers(5000);
  assert.match(h.els.chatVoiceStatus.textContent, /^Wiedergabe:/);
  h.spoken[0].utterance.onend();
  assert.equal(h.timers.size, 0);
});
