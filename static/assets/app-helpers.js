window.state = {
  activeTab: "home",
  lastWorkspaceTab: "exams",
  conversationId: null,
  exam: null,
  examMode: "official",
  officialExam: null,
  mockExamHealth: null,
  selectedPracticeSetKey: null,
  selectedPracticeResourceType: null,
  lastExamModuleUsed: "lesen",
  mockVariantCounter: 1,
  mockVariantSignature: null,
  mockDraftKey: null,
  mockDraftAnswers: {},
  mockExamPageIndex: 0,
  mockEvaluation: null,
  mockReviewFilter: "all",
  mockExamFullscreen: false,
  mockMediaSpeechPartKey: null,
  mockMediaSpeechRemainingPlays: 0,
  examRequestInFlight: false,
  examSubmitInFlight: false,
  examWorkspaceScrollY: 0,
  examFocusedAnswerId: null,
  restoreExamViewport: false,
  grammar: null,
  grammarCatalog: [],
  writingPrompt: null,
  speakingSessionId: null,
  placement: null,
  roadmap: null,
  progressOverview: null,
  progressMistakes: [],
  chatHistoryItems: [],
  chatTranscriptEntries: [],
  chatEditingEntryId: null,
  chatVersionsEntryId: null,
  chatVersionsCache: {},
  settings: null,
  config: null,
  vocabItems: [],
  selectedVocabIds: new Set(),
  decks: [],
  starterDecks: [],
  reviewCard: null,
  reviewBackVisible: false,
  recorder: null,
  recorderChunks: [],
  recordTarget: null,
  speechRecognition: null,
  speechRecognitionTarget: null,
  speechRecognitionActive: false,
  chatRequestInFlight: false,
  chatRequestController: null,
  tutorStreamController: null,
  chatPendingBubble: null,
  chatTranscribeInFlight: false,
  chatTtsEnabled: true,
  chatTtsVoicesBound: false,
  chatVoiceCatalog: [],
  chatVoiceGender: "female",
  chatVoiceVariant: "standard",
  chatVoiceRegion: "de-DE",
  chatLastAssistantReply: "",
  chatHasCompletedAssistantTurn: false,
  tutorAudio: {
    mode: "idle",
    turnId: null,
    queueDepth: 0,
    localPlaybackStarted: false,
    fallbackInUse: false,
  },
  tutorSession: {
    state: "idle",
    transport: "none",
    activeTurnId: null,
    hasReceivedContent: false,
    lastError: "",
  },
  mockAudioVoiceGender: "auto",
  tutorAvatar: "woman",
  examTimerId: null,
  examEndsAt: null,
  examRemainingMs: 0,
  examTimerPaused: false,
  examTimerContextKey: null,
  pausedExamSession: null,
  restoreExamWorkspace: false,
  examWorkspaceActive: false,
  examRailWidth: 150,
};

window.els = {};

const compatTemplate = document.getElementById("legacyCompatTemplate");
const compatRuntimeRoot = compatTemplate instanceof HTMLTemplateElement
  ? document.createElement("div")
  : null;

if (compatRuntimeRoot) {
  compatRuntimeRoot.setAttribute("hidden", "");
  compatRuntimeRoot.setAttribute("aria-hidden", "true");
  compatRuntimeRoot.inert = true;
  compatRuntimeRoot.appendChild(compatTemplate.content.cloneNode(true));
  window.__legacyCompatRuntimeRoot = compatRuntimeRoot;
}

const registerElsFromRoot = (root) => {
  root?.querySelectorAll?.("[id]").forEach((el) => {
    window.els[el.id] = el;
  });
};

registerElsFromRoot(document);
registerElsFromRoot(compatRuntimeRoot);
els.primaryNavButtons = Array.from(document.querySelectorAll("[data-primary-tab]"));
els.tabs = Array.from(document.querySelectorAll(".tab-btn"));
els.panels = Array.from(document.querySelectorAll(".tab-panel"));
els.rateButtons = [
  ...Array.from(document.querySelectorAll(".rate-btn")),
  ...Array.from(compatRuntimeRoot?.querySelectorAll?.(".rate-btn") || []),
];

const UI_PREFERENCES_STORAGE_KEY = "deutschlernstudio:ui:v1";
const EXAM_RAIL_WIDTH_DEFAULT = 150;
const EXAM_RAIL_WIDTH_MIN = 144;
const EXAM_RAIL_WIDTH_MAX = 312;
const EXAM_RAIL_WIDTH_RESTORE_MAX = 180;
let examViewportPersistTimer = null;
let confirmModalResolver = null;
let confirmModalPreviousFocus = null;
let confirmModalBound = false;
let toastCounter = 0;
let examRailResizeBound = false;

window.readUiPreferences = function readUiPreferences() {
  try {
    const raw = window.localStorage?.getItem(UI_PREFERENCES_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
};

window.writeUiPreferences = function writeUiPreferences(patch = {}) {
  const next = { ...readUiPreferences(), ...patch };
  try {
    window.localStorage?.setItem(UI_PREFERENCES_STORAGE_KEY, JSON.stringify(next));
  } catch {
    return next;
  }
  return next;
};

window.getExamRailWidthBounds = function getExamRailWidthBounds() {
  const shellWidth = Number(els.examPrepShell?.clientWidth || 0);
  const maxByShell = shellWidth > 0 ? Math.floor(shellWidth * 0.42) : EXAM_RAIL_WIDTH_MAX;
  return {
    min: EXAM_RAIL_WIDTH_MIN,
    max: Math.max(EXAM_RAIL_WIDTH_MIN + 24, Math.min(EXAM_RAIL_WIDTH_MAX, maxByShell || EXAM_RAIL_WIDTH_MAX)),
  };
};

window.getExamRailRestoreWidth = function getExamRailRestoreWidth(nextWidth = state.examRailWidth) {
  const { min, max } = getExamRailWidthBounds();
  const shellWidth = Number(els.examPrepShell?.clientWidth || 0);
  const viewportSoftMax = shellWidth > 0 ? Math.floor(shellWidth * 0.2) : EXAM_RAIL_WIDTH_RESTORE_MAX;
  const restoreMax = Math.max(
    EXAM_RAIL_WIDTH_DEFAULT + 12,
    Math.min(max, EXAM_RAIL_WIDTH_RESTORE_MAX, viewportSoftMax || EXAM_RAIL_WIDTH_RESTORE_MAX),
  );
  return Math.round(Math.max(min, Math.min(restoreMax, Number(nextWidth) || EXAM_RAIL_WIDTH_DEFAULT)));
};

window.applyExamRailWidth = function applyExamRailWidth(nextWidth = state.examRailWidth) {
  if (!els.examPrepShell) return EXAM_RAIL_WIDTH_DEFAULT;
  if (window.matchMedia("(max-width: 1180px)").matches) {
    els.examPrepShell.style.removeProperty("--exam-rail-width");
    if (els.examRailResizeHandle) {
      els.examRailResizeHandle.setAttribute("aria-hidden", "true");
      els.examRailResizeHandle.classList.remove("is-active");
    }
    return EXAM_RAIL_WIDTH_DEFAULT;
  }
  const { min, max } = getExamRailWidthBounds();
  const fallbackWidth = Number(state.examRailWidth) || EXAM_RAIL_WIDTH_DEFAULT;
  const safeWidth = Math.round(Math.max(min, Math.min(max, Number(nextWidth) || fallbackWidth)));
  state.examRailWidth = safeWidth;
  els.examPrepShell.style.setProperty("--exam-rail-width", `${safeWidth}px`);
  if (els.examRailResizeHandle) {
    els.examRailResizeHandle.removeAttribute("aria-hidden");
    els.examRailResizeHandle.setAttribute("aria-valuemin", String(min));
    els.examRailResizeHandle.setAttribute("aria-valuemax", String(max));
    els.examRailResizeHandle.setAttribute("aria-valuenow", String(safeWidth));
  }
  return safeWidth;
};

window.bindExamRailResize = function bindExamRailResize() {
  if (!els.examRailResizeHandle || !els.examPrepShell || !els.examHub) {
    return applyExamRailWidth(state.examRailWidth);
  }
  if (examRailResizeBound) {
    return applyExamRailWidth(state.examRailWidth);
  }
  examRailResizeBound = true;

  const handle = els.examRailResizeHandle;
  const applyAndPersist = (nextWidth) => {
    applyExamRailWidth(nextWidth);
    persistExamUiPreferences();
  };

  handle.addEventListener("pointerdown", (event) => {
    if (window.matchMedia("(max-width: 1180px)").matches) return;
    event.preventDefault();
    const railWidth = els.examHub.getBoundingClientRect().width || state.examRailWidth || EXAM_RAIL_WIDTH_DEFAULT;
    const startX = event.clientX;
    const pointerId = event.pointerId;
    const onMove = (moveEvent) => {
      applyExamRailWidth(railWidth + (moveEvent.clientX - startX));
    };
    const finish = () => {
      document.body.classList.remove("is-exam-rail-resizing");
      handle.classList.remove("is-active");
      handle.releasePointerCapture?.(pointerId);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", finish);
      window.removeEventListener("pointercancel", finish);
      persistExamUiPreferences();
    };

    document.body.classList.add("is-exam-rail-resizing");
    handle.classList.add("is-active");
    handle.setPointerCapture?.(pointerId);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", finish);
    window.addEventListener("pointercancel", finish);
  });

  handle.addEventListener("keydown", (event) => {
    if (window.matchMedia("(max-width: 1180px)").matches) return;
    const { min, max } = getExamRailWidthBounds();
    const current = Number(state.examRailWidth) || EXAM_RAIL_WIDTH_DEFAULT;
    let next = null;
    if (event.key === "ArrowLeft") next = current - 12;
    if (event.key === "ArrowRight") next = current + 12;
    if (event.key === "Home") next = min;
    if (event.key === "End") next = max;
    if (next == null) return;
    event.preventDefault();
    applyAndPersist(next);
  });

  handle.addEventListener("dblclick", (event) => {
    event.preventDefault();
    applyAndPersist(EXAM_RAIL_WIDTH_DEFAULT);
  });

  window.addEventListener("resize", () => {
    applyExamRailWidth(state.examRailWidth);
  });

  applyExamRailWidth(state.examRailWidth);
};

window.persistExamUiPreferences = function persistExamUiPreferences() {
  return writeUiPreferences({
    activeTab: state.activeTab,
    lastWorkspaceTab: state.lastWorkspaceTab,
    globalLevel: els.globalLevel?.value || "B2",
    examScope: els.examScope?.value || "full",
    lastExamModuleUsed: state.lastExamModuleUsed,
    selectedPracticeSetKey: state.selectedPracticeSetKey,
    selectedPracticeResourceType: state.selectedPracticeResourceType,
    mockVariantCounter: state.mockVariantCounter,
    mockVariantSignature: state.mockVariantSignature,
    mockDraftKey: state.mockDraftKey,
    mockDraftAnswers: state.mockDraftAnswers,
    mockExamPageIndex: state.mockExamPageIndex,
    mockReviewFilter: state.mockReviewFilter,
    examWorkspaceScrollY: state.examWorkspaceScrollY,
    examFocusedAnswerId: state.examFocusedAnswerId,
    examWorkspaceOpen: state.examWorkspaceActive === true,
    examEndsAt: state.examEndsAt,
    examRemainingMs: state.examRemainingMs,
    examTimerPaused: state.examTimerPaused,
    examTimerContextKey: state.examTimerContextKey,
    pausedExamSession: state.pausedExamSession,
    examRailWidth: state.examRailWidth,
    mockAudioVoiceGender: state.mockAudioVoiceGender,
    tutorAvatar: state.tutorAvatar,
    tutorIdentity: state.tutorAvatar,
  });
};

window.persistMockAudioVoicePreference = function persistMockAudioVoicePreference() {
  return writeUiPreferences({ mockAudioVoiceGender: state.mockAudioVoiceGender });
};

window.getMainTutorMode = function getMainTutorMode() {
  return "fluidez";
};

window.restoreUiPreferences = function restoreUiPreferences() {
  const saved = readUiPreferences();
  const hasOption = (selectEl, value) => Array.from(selectEl?.options || []).some((option) => option.value === value);
  const normalizeTutorIdentityPreference = (value) => {
    const key = String(value || "").trim().toLowerCase();
    if (["woman", "female", "studio"].includes(key)) return "woman";
    if (["man", "male", "coach", "examiner"].includes(key)) return "man";
    return null;
  };

  if (hasOption(els.globalLevel, saved.globalLevel)) els.globalLevel.value = saved.globalLevel;
  if (hasOption(els.examScope, saved.examScope)) els.examScope.value = saved.examScope;
  if (hasOption(els.examModule, saved.lastExamModuleUsed)) {
    state.lastExamModuleUsed = saved.lastExamModuleUsed;
    els.examModule.value = saved.lastExamModuleUsed;
  }
  if (typeof saved.selectedPracticeSetKey === "string") state.selectedPracticeSetKey = saved.selectedPracticeSetKey;
  if (typeof saved.selectedPracticeResourceType === "string") state.selectedPracticeResourceType = saved.selectedPracticeResourceType;
  if (typeof saved.chatTtsEnabled === "boolean") state.chatTtsEnabled = saved.chatTtsEnabled;
  if (typeof saved.chatVoiceVariant === "string" && ["standard", "regional"].includes(saved.chatVoiceVariant)) {
    state.chatVoiceVariant = saved.chatVoiceVariant;
  }
  if (typeof saved.chatVoiceRegion === "string" && saved.chatVoiceRegion.trim()) {
    state.chatVoiceRegion = saved.chatVoiceRegion;
  }
  if (typeof saved.mockAudioVoiceGender === "string" && ["auto", "female", "male"].includes(saved.mockAudioVoiceGender)) {
    state.mockAudioVoiceGender = saved.mockAudioVoiceGender;
  }
  const restoredVoiceGender = typeof saved.chatVoiceGender === "string" && ["female", "male"].includes(saved.chatVoiceGender)
    ? saved.chatVoiceGender
    : null;
  const restoredTutorIdentity = normalizeTutorIdentityPreference(saved.tutorAvatar)
    || normalizeTutorIdentityPreference(saved.tutorIdentity)
    || normalizeTutorIdentityPreference(saved.chatVoiceGender);
  if (restoredTutorIdentity) state.tutorAvatar = restoredTutorIdentity;
  if (restoredVoiceGender) state.chatVoiceGender = restoredVoiceGender;
  else state.chatVoiceGender = state.tutorAvatar === "man" ? "male" : "female";
  state.tutorAvatar = state.chatVoiceGender === "male" ? "man" : "woman";
  if (typeof saved.mockVariantCounter === "number" && saved.mockVariantCounter >= 1) state.mockVariantCounter = saved.mockVariantCounter;
  if (typeof saved.mockVariantSignature === "string") state.mockVariantSignature = saved.mockVariantSignature;
  if (typeof saved.mockDraftKey === "string") state.mockDraftKey = saved.mockDraftKey;
  state.mockDraftAnswers = saved.mockDraftAnswers && typeof saved.mockDraftAnswers === "object" ? saved.mockDraftAnswers : {};
  state.mockExamPageIndex = typeof saved.mockExamPageIndex === "number" && saved.mockExamPageIndex >= 0 ? saved.mockExamPageIndex : 0;
  state.mockReviewFilter = typeof saved.mockReviewFilter === "string" ? saved.mockReviewFilter : "all";
  state.examWorkspaceScrollY = typeof saved.examWorkspaceScrollY === "number" ? saved.examWorkspaceScrollY : 0;
  state.examFocusedAnswerId = typeof saved.examFocusedAnswerId === "string" ? saved.examFocusedAnswerId : null;
  state.restoreExamWorkspace = saved.examWorkspaceOpen === true;
  state.examWorkspaceActive = saved.examWorkspaceOpen === true;
  state.examEndsAt = typeof saved.examEndsAt === "number" ? saved.examEndsAt : null;
  state.examRemainingMs = typeof saved.examRemainingMs === "number" ? saved.examRemainingMs : 0;
  state.examTimerPaused = saved.examTimerPaused === true;
  state.examTimerContextKey = typeof saved.examTimerContextKey === "string" ? saved.examTimerContextKey : null;
  state.pausedExamSession = saved.pausedExamSession && typeof saved.pausedExamSession === "object" ? saved.pausedExamSession : null;
  state.examRailWidth = typeof saved.examRailWidth === "number"
    ? getExamRailRestoreWidth(saved.examRailWidth)
    : EXAM_RAIL_WIDTH_DEFAULT;
  if (typeof saved.lastWorkspaceTab === "string" && saved.lastWorkspaceTab.trim()) state.lastWorkspaceTab = saved.lastWorkspaceTab;
  if (els.panels.some((panel) => panel.id === `tab-${saved.activeTab}`)) state.activeTab = saved.activeTab;
  switchTab(state.activeTab);
  applyExamRailWidth(state.examRailWidth);
  syncPersistedExamTimerBadge();
};

window.setTutorSessionState = function setTutorSessionState(nextState, patch = {}) {
  const current = state.tutorSession && typeof state.tutorSession === "object"
    ? state.tutorSession
    : {
      state: "idle",
      transport: "none",
      activeTurnId: null,
      hasReceivedContent: false,
      lastError: "",
    };
  state.tutorSession = {
    ...current,
    ...patch,
    state: nextState,
  };
  const chatPanel = els["tab-chat"];
  if (chatPanel) chatPanel.dataset.tutorSessionState = nextState;
  if (typeof window.updateChatComposerState === "function") window.updateChatComposerState();
  return state.tutorSession;
};

window.resetTutorSessionState = function resetTutorSessionState() {
  return setTutorSessionState("idle", {
    transport: "none",
    activeTurnId: null,
    hasReceivedContent: false,
    lastError: "",
  });
};

window.isTutorSessionBusy = function isTutorSessionBusy() {
  const currentState = state.tutorSession?.state || "idle";
  return ["listening", "transcribing", "thinking", "streaming"].includes(currentState);
};

window.canInterruptTutorSession = function canInterruptTutorSession() {
  const transport = state.tutorSession?.transport || "none";
  const currentState = state.tutorSession?.state || "idle";
  return transport === "stream" && ["thinking", "streaming"].includes(currentState);
};

window.I18N = {
  de: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Prüfungen",
    tab_placement: "Einstufung",
    tab_roadmap: "Lernplan",
    tab_grammar: "Grammatik",
    tab_writing: "Schreiben",
    tab_speaking: "Sprechen",
    tab_vocab: "Wortschatz",
    tab_flashcards: "Karteikarten",
    tab_progress: "Fortschritt",
    tab_settings: "Einstellungen",
    send: "Senden",
    chat_finish: "Abschlussfeedback",
    chat_title: "Chat-Tutor",
    chat_control: "Tutor-Steuerung",
    hero_title: "Deutsch lernen, Goethe trainieren und systematisch besser werden.",
    hero_copy: "Theorie, Prüfungsmodus, Einstufung, Lernplan, Karteikarten und Sprachpraxis in einer klaren, schnellen Oberfläche.",
    metric_goal: "Ziel",
    metric_today: "Heute",
    metric_due: "Fällige Karten",
    metric_streak: "Serie",
    global_level: "Globales Niveau",
    history: "Verlauf",
    load: "Laden",
    new_session: "Neue Sitzung",
    quick_correction: "Schnellkorrektur",
    mode_tips: "Modus-Hinweise",
    chat_tts_on: "Audio an",
    chat_tts_off: "Audio aus",
    chat_tts_na: "Nicht verfügbar",
    final_feedback: "Abschlussfeedback",
    exam_title: "Goethe-Modus",
    scope: "Format",
    module: "Modul",
    start_sim: "Simulation starten",
    grade_exam: "Prüfung auswerten",
    results: "Ergebnisse",
    recent_history: "Letzte Durchläufe",
    placement_title: "Einstufungstest",
  },
  es: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Exámenes",
    tab_placement: "Nivel",
    tab_roadmap: "Plan",
    tab_grammar: "Gramática",
    tab_writing: "Escritura",
    tab_speaking: "Oral",
    tab_vocab: "Vocabulario",
    tab_flashcards: "Tarjetas",
    tab_progress: "Progreso",
    tab_settings: "Ajustes",
    send: "Enviar",
    chat_finish: "Feedback final",
    chat_title: "Tutor de chat",
    chat_control: "Control del tutor",
    hero_title: "Aprende alemán, entrena Goethe y mejora con un sistema claro.",
    hero_copy: "Teoría, modo examen, prueba de nivel, plan de estudio, tarjetas y práctica oral en una sola interfaz.",
    metric_goal: "Objetivo",
    metric_today: "Hoy",
    metric_due: "Tarjetas pendientes",
    metric_streak: "Racha",
    global_level: "Nivel global",
    history: "Historial",
    load: "Cargar",
    new_session: "Nueva sesión",
    quick_correction: "Corrección rápida",
    mode_tips: "Consejos",
    chat_tts_on: "Audio activo",
    chat_tts_off: "Audio apagado",
    chat_tts_na: "Sin audio",
    final_feedback: "Feedback final",
    exam_title: "Modo Goethe",
    scope: "Formato",
    module: "Módulo",
    start_sim: "Iniciar simulación",
    grade_exam: "Corregir examen",
    results: "Resultados",
    recent_history: "Intentos recientes",
    placement_title: "Prueba de nivel",
  },
  en: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Exams",
    tab_placement: "Placement",
    tab_roadmap: "Plan",
    tab_grammar: "Grammar",
    tab_writing: "Writing",
    tab_speaking: "Speaking",
    tab_vocab: "Vocabulary",
    tab_flashcards: "Flashcards",
    tab_progress: "Progress",
    tab_settings: "Settings",
    send: "Send",
    chat_finish: "Final feedback",
    chat_title: "Chat tutor",
    chat_control: "Tutor controls",
    hero_title: "Learn German, train for Goethe and improve with a clear system.",
    hero_copy: "Theory, exam mode, placement test, study plan, flashcards and speaking practice in one interface.",
    metric_goal: "Goal",
    metric_today: "Today",
    metric_due: "Due cards",
    metric_streak: "Streak",
    global_level: "Global level",
    history: "History",
    load: "Load",
    new_session: "New session",
    quick_correction: "Quick correction",
    mode_tips: "Mode tips",
    chat_tts_on: "Audio on",
    chat_tts_off: "Audio off",
    chat_tts_na: "Nicht verfügbar",
    final_feedback: "Final feedback",
    exam_title: "Goethe mode",
    scope: "Format",
    module: "Module",
    start_sim: "Start simulation",
    grade_exam: "Grade exam",
    results: "Results",
    recent_history: "Recent attempts",
    placement_title: "Placement test",
  },
  fr: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Examens",
    tab_placement: "Niveau",
    tab_roadmap: "Plan",
    tab_grammar: "Grammaire",
    tab_writing: "Écriture",
    tab_speaking: "Oral",
    tab_vocab: "Vocabulaire",
    tab_flashcards: "Cartes",
    tab_progress: "Progrès",
    tab_settings: "Réglages",
    send: "Envoyer",
    chat_finish: "Retour final",
    chat_title: "Tuteur de chat",
    chat_control: "Contrôle du tuteur",
    hero_title: "Apprenez l'allemand, entraînez Goethe et progressez avec un système clair.",
    hero_copy: "Théorie, mode examen, test de niveau, plan d'étude, cartes mémoire et pratique orale dans une seule interface.",
    metric_goal: "Objectif",
    metric_today: "Aujourd'hui",
    metric_due: "Cartes à revoir",
    metric_streak: "Série",
    global_level: "Niveau global",
    history: "Historique",
    load: "Charger",
    new_session: "Nouvelle session",
    quick_correction: "Correction rapide",
    mode_tips: "Conseils",
    chat_tts_on: "Audio activé",
    chat_tts_off: "Audio coupé",
    chat_tts_na: "Sans audio",
    final_feedback: "Retour final",
    exam_title: "Mode Goethe",
    scope: "Format",
    module: "Module",
    start_sim: "Lancer la simulation",
    grade_exam: "Corriger l'examen",
    results: "Résultats",
    recent_history: "Tentatives récentes",
    placement_title: "Test de niveau",
  },
  it: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Esami",
    tab_placement: "Livello",
    tab_roadmap: "Piano",
    tab_grammar: "Grammatica",
    tab_writing: "Scrittura",
    tab_speaking: "Orale",
    tab_vocab: "Vocabolario",
    tab_flashcards: "Flashcard",
    tab_progress: "Progresso",
    tab_settings: "Impostazioni",
    send: "Invia",
    chat_finish: "Feedback finale",
    chat_title: "Tutor chat",
    chat_control: "Controllo tutor",
    hero_title: "Impara il tedesco, allenati per il Goethe e migliora con un sistema chiaro.",
    hero_copy: "Teoria, modalità esame, test di livello, piano di studio, flashcard e pratica orale in un'unica interfaccia.",
    metric_goal: "Obiettivo",
    metric_today: "Oggi",
    metric_due: "Carte in scadenza",
    metric_streak: "Serie",
    global_level: "Livello globale",
    history: "Cronologia",
    load: "Carica",
    new_session: "Nuova sessione",
    quick_correction: "Correzione rapida",
    mode_tips: "Suggerimenti",
    chat_tts_on: "Audio attivo",
    chat_tts_off: "Audio spento",
    chat_tts_na: "Senza audio",
    final_feedback: "Feedback finale",
    exam_title: "Modalità Goethe",
    scope: "Formato",
    module: "Modulo",
    start_sim: "Avvia simulazione",
    grade_exam: "Correggi esame",
    results: "Risultati",
    recent_history: "Tentativi recenti",
    placement_title: "Test di livello",
  },
  pt: {
    brand: "Deutsch Lernstudio",
    tab_chat: "Chat",
    tab_exams: "Exames",
    tab_placement: "Nível",
    tab_roadmap: "Plano",
    tab_grammar: "Gramática",
    tab_writing: "Escrita",
    tab_speaking: "Oral",
    tab_vocab: "Vocabulário",
    tab_flashcards: "Flashcards",
    tab_progress: "Progresso",
    tab_settings: "Configurações",
    send: "Enviar",
    chat_finish: "Feedback final",
    chat_title: "Tutor de chat",
    chat_control: "Controle do tutor",
    hero_title: "Aprenda alemão, treine para o Goethe e melhore com um sistema claro.",
    hero_copy: "Teoria, modo exame, teste de nível, plano de estudo, flashcards e prática oral em uma única interface.",
    metric_goal: "Objetivo",
    metric_today: "Hoje",
    metric_due: "Cartões pendentes",
    metric_streak: "Sequência",
    global_level: "Nível global",
    history: "Histórico",
    load: "Carregar",
    new_session: "Nova sessão",
    quick_correction: "Correção rápida",
    mode_tips: "Dicas",
    chat_tts_on: "Audio ligado",
    chat_tts_off: "Audio desligado",
    chat_tts_na: "Sem audio",
    final_feedback: "Feedback final",
    exam_title: "Modo Goethe",
    scope: "Formato",
    module: "Módulo",
    start_sim: "Iniciar simulação",
    grade_exam: "Corrigir exame",
    results: "Resultados",
    recent_history: "Tentativas recentes",
    placement_title: "Teste de nível",
  },
};

window.t = function t(key) {
  const lang = state.settings?.interface_language || "de";
  return I18N[lang]?.[key] || I18N.de[key] || key;
};

window.applyLanguage = function applyLanguage() {
  document.documentElement.lang = state.settings?.interface_language || "de";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  if (typeof window.syncPrimaryNavigation === "function") window.syncPrimaryNavigation();
  if (typeof window.renderActiveTabContext === "function") window.renderActiveTabContext();
  if (typeof window.renderHome === "function") window.renderHome();
  if (typeof window.renderLearn === "function") window.renderLearn();
  if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
  if (typeof window.renderProgressSurface === "function") window.renderProgressSurface();
  if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
  if (typeof window.refreshChatTtsUi === "function") window.refreshChatTtsUi();
};

window.escapeHtml = function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
};

window.apiFetch = async function apiFetch(url, options = {}) {
  const { timeoutMs = 0, signal: externalSignal = null, ...fetchOptions } = options;
  const controller = new AbortController();
  const cleanup = [];
  let timeoutId = null;
  const abortRequest = (reason) => {
    if (!controller.signal.aborted) controller.abort(reason);
  };

  if (externalSignal) {
    if (externalSignal.aborted) abortRequest(externalSignal.reason);
    const onAbort = () => abortRequest(externalSignal.reason || new DOMException("Aborted", "AbortError"));
    externalSignal.addEventListener("abort", onAbort, { once: true });
    cleanup.push(() => externalSignal.removeEventListener("abort", onAbort));
  }

  if (timeoutMs > 0) {
    timeoutId = window.setTimeout(
      () => abortRequest(new DOMException("Timed out", "TimeoutError")),
      timeoutMs,
    );
  }

  try {
    const response = await fetch(url, { ...fetchOptions, signal: controller.signal });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { detail: text };
      }
    }
    if (!response.ok) throw new Error(data?.detail || "API-Fehler");
    return data;
  } catch (error) {
    if (controller.signal.aborted) {
      const reasonName = controller.signal.reason?.name || error?.name || "";
      if (reasonName === "TimeoutError") {
        throw new Error("La solicitud ha tardado demasiado y se ha cancelado.");
      }
      throw new Error("Solicitud cancelada.");
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
    cleanup.forEach((fn) => fn());
  }
};

window.setStatus = function setStatus(message) {
  if (els.statusBadge) els.statusBadge.textContent = message;
};

window.setAppBusyBanner = function setAppBusyBanner(message = "", tone = "neutral") {
  if (!els.appBusyBanner) return;
  const hasMessage = Boolean(String(message || "").trim());
  els.appBusyBanner.textContent = message || "";
  els.appBusyBanner.classList.toggle("hidden", !hasMessage);
  els.appBusyBanner.classList.remove("is-warning", "is-error", "is-success");
  if (!hasMessage) return;
  if (tone === "warning") els.appBusyBanner.classList.add("is-warning");
  if (tone === "error") els.appBusyBanner.classList.add("is-error");
  if (tone === "success") els.appBusyBanner.classList.add("is-success");
};

window.pushAppToast = function pushAppToast(message, tone = "neutral", timeoutMs = 3200) {
  if (!els.appToastRail || !String(message || "").trim()) return;
  const toast = document.createElement("div");
  toast.className = `app-toast${tone !== "neutral" ? ` is-${tone}` : ""}`;
  toast.dataset.toastId = String(++toastCounter);
  toast.textContent = message;
  els.appToastRail.appendChild(toast);
  window.setTimeout(() => {
    toast.classList.add("is-leaving");
    window.setTimeout(() => toast.remove(), 220);
  }, Math.max(1200, timeoutMs));
};

window.setActionButtonBusy = function setActionButtonBusy(button, busy, busyLabel = "Wird verarbeitet ...") {
  if (!button) return;
  if (!button.dataset.defaultLabel) button.dataset.defaultLabel = button.textContent;
  button.disabled = Boolean(busy);
  button.classList.toggle("is-busy", Boolean(busy));
  button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
};

window.countBlankExamAnswers = function countBlankExamAnswers(container) {
  if (!container) return 0;
  let blankCount = 0;
  container.querySelectorAll("[data-answer-input]").forEach((input) => {
    if (!String(input.value || "").trim()) blankCount += 1;
  });
  return blankCount;
};

window.closeConfirmModal = function closeConfirmModal(confirmed = false) {
  if (!els.confirmModal || !confirmModalResolver) return;
  els.confirmModal.classList.add("hidden");
  els.confirmModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  const resolver = confirmModalResolver;
  confirmModalResolver = null;
  const previousFocus = confirmModalPreviousFocus;
  confirmModalPreviousFocus = null;
  resolver(confirmed);
  previousFocus?.focus?.();
};

window.bindConfirmModal = function bindConfirmModal() {
  if (confirmModalBound || !els.confirmModal) return;
  confirmModalBound = true;
  els.confirmModal.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-confirm-modal]")) closeConfirmModal(false);
  });
  els.confirmModalCancelBtn?.addEventListener("click", () => closeConfirmModal(false));
  els.confirmModalConfirmBtn?.addEventListener("click", () => closeConfirmModal(true));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && confirmModalResolver) closeConfirmModal(false);
  });
};

window.openConfirmModal = function openConfirmModal({
  title = "Bestätigung",
  message = "Bitte bestätigen Sie diese Aktion.",
  confirmLabel = "Bestätigen",
  cancelLabel = "Abbrechen",
} = {}) {
  bindConfirmModal();
  if (!els.confirmModal) return Promise.resolve(false);
  if (confirmModalResolver) closeConfirmModal(false);
  confirmModalPreviousFocus = document.activeElement;
  els.confirmModalTitle.textContent = title;
  els.confirmModalMessage.textContent = message;
  els.confirmModalConfirmBtn.textContent = confirmLabel;
  els.confirmModalCancelBtn.textContent = cancelLabel;
  els.confirmModal.classList.remove("hidden");
  els.confirmModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  return new Promise((resolve) => {
    confirmModalResolver = resolve;
    window.requestAnimationFrame(() => {
      els.confirmModalConfirmBtn?.focus();
    });
  });
};

window.getPrimaryTabGroup = function getPrimaryTabGroup(tabName) {
  if (["home", "learn", "flashcards", "progress", "roadmap"].includes(tabName)) return "home";
  if (tabName === "chat") return "tutor";
  if (tabName === "settings") return "settings";
  return "exam-prep";
};

window.openPrimaryTab = function openPrimaryTab(primaryTab) {
  const nextTab = {
    home: "home",
    tutor: "chat",
    "exam-prep": "exams",
    settings: "settings",
    learn: "home",
    review: "home",
    progress: "home",
    profile: "settings",
    workspace: "exams",
  }[primaryTab] || "home";
  switchTab(nextTab);
};

window.syncPrimaryNavigation = function syncPrimaryNavigation() {
  const group = getPrimaryTabGroup(state.activeTab);
  document.body.dataset.primaryTab = group;
  els.primaryNavButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.primaryTab === group));
  els.openSettingsBtn?.classList.toggle("active", group === "settings");
  if (els.workspaceNavShell) {
    els.workspaceNavShell.classList.add("hidden");
    els.workspaceNavShell.setAttribute("hidden", "");
    els.workspaceNavShell.setAttribute("aria-hidden", "true");
  }
  els.tabContextBar?.classList.add("hidden");
};

window.refreshHeroMetrics = function refreshHeroMetrics() {
  els.metricGoal.textContent = `${(state.settings?.default_goal_exam || "goethe_b2").replace("_", " ").toUpperCase()} · ${els.globalLevel.value}`;
  const labels = {
    de: {
      home: "Start",
      chat: "Tutor",
      learn: "Lernpfad",
      exams: "Prüfung",
      placement: "Einstufung",
      roadmap: "Lernplan",
      grammar: "Grammatik",
      writing: "Schreiben",
      speaking: "Sprechen",
      vocab: "Wortschatz",
      flashcards: "Karteikarten-Wiederholung",
      progress: "Status",
      settings: "Einstellungen",
    },
    es: {
      home: "Inicio",
      chat: "Tutor",
      learn: "Ruta",
      exams: "Examen",
      placement: "Nivel",
      roadmap: "Plan",
      grammar: "Gramatica",
      writing: "Escritura",
      speaking: "Hablar",
      vocab: "Vocabulario",
      flashcards: "Repaso",
      progress: "Estado",
      settings: "Ajustes",
    },
    pt: {
      home: "Inicio",
      chat: "Tutor",
      learn: "Rota",
      exams: "Exame",
      placement: "Nivel",
      roadmap: "Plano",
      grammar: "Gramatica",
      writing: "Escrita",
      speaking: "Fala",
      vocab: "Vocabulario",
      flashcards: "Revisao",
      progress: "Estado",
      settings: "Ajustes",
    },
  };
  const lang = state.settings?.interface_language || "de";
  els.metricToday.textContent = labels[lang]?.[state.activeTab] || labels.de[state.activeTab] || "Gezieltes Training";
};

window.renderActiveTabContext = function renderActiveTabContext() {
  if (!els.tabContextBar) return;
  els.tabContextBar.innerHTML = "";
  els.tabContextBar.classList.add("hidden");
};

window.switchTab = function switchTab(tabName) {
  const alias = {
    learn: "home",
    flashcards: "home",
    progress: "home",
    roadmap: "home",
    placement: "exams",
    grammar: "exams",
    writing: "exams",
    speaking: "exams",
    vocab: "exams",
  };
  const resolvedTab = alias[tabName] || tabName;
  if (!els.panels.some((panel) => panel.id === `tab-${resolvedTab}`)) return;
  state.activeTab = resolvedTab;
  if (!["home", "chat", "settings"].includes(resolvedTab)) state.lastWorkspaceTab = resolvedTab;
  els.tabs.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tabName));
  els.panels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${resolvedTab}`));
  persistExamUiPreferences();
  syncPrimaryNavigation();
  refreshHeroMetrics();
  renderActiveTabContext();
  if (resolvedTab === "home" && typeof window.renderHome === "function") window.renderHome();
  if (resolvedTab === "settings" && typeof window.renderProfileSurface === "function") window.renderProfileSurface();
};

window.appendBubble = function appendBubble(container, role, text, extraClass = "") {
  const bubble = document.createElement("div");
  bubble.className = ["bubble", role, extraClass].filter(Boolean).join(" ");
  bubble.innerHTML = escapeHtml(text).replace(/\n/g, "<br />");
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
  return bubble;
};

window.renderTips = function renderTips(listEl, items) {
  listEl.innerHTML = (items || []).length
    ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : "<li class='muted'>Noch keine Zusatzhinweise.</li>";
};

window.renderQuestionList = function renderQuestionList(container, items, prefix) {
  if (!(items || []).length) {
    container.innerHTML = "<div class='soft-panel empty'>Noch keine Aufgaben geladen.</div>";
    return;
  }
  let currentSection = "";
  let currentPart = "";
  container.innerHTML = items.map((item, index) => {
    const id = `${prefix}-${item.id}`;
    const control = item.item_type === "mcq" || item.item_type === "true_false"
      ? `<select id="${id}" data-answer-input="${escapeHtml(item.id)}"><option value="">-</option>${(item.options || []).map((opt) => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("")}</select>`
      : `<textarea id="${id}" data-answer-input="${escapeHtml(item.id)}" rows="4" placeholder="Antwort ..."></textarea>`;
    const sectionKey = item.section || "";
    const partKey = `${item.section || ""}::${item.section_title || ""}`;
    const sectionHeader = sectionKey !== currentSection
      ? `<article class="list-item"><strong>${escapeHtml((item.section || "").toUpperCase() || "PRÜFUNG")}</strong><p class="muted">Offizieller Modulblock in Prüfungsreihenfolge</p></article>`
      : "";
    const partHeader = partKey !== currentPart
      ? `<article class="list-item"><strong>${escapeHtml(item.section_title || "")}</strong><p class="muted">${escapeHtml(item.points)} Punkte pro Aufgabe${item.min_words ? ` · mind. ${escapeHtml(item.min_words)} Wörter` : ""}</p></article>`
      : "";
    currentSection = sectionKey;
    currentPart = partKey;
    return `${sectionHeader}${partHeader}<article class="question-card"><p class="question-meta">${escapeHtml(item.section_title || "")} · ${index + 1} · ${escapeHtml(item.points)} Punkte${item.min_words ? ` · mind. ${escapeHtml(item.min_words)} Wörter` : ""}</p><h3>${escapeHtml(item.prompt)}</h3>${item.support_text ? `<div class="question-support">${escapeHtml(item.support_text).replace(/\n/g, "<br />")}</div>` : ""}${control}</article>`;
  }).join("");
};

window.collectAnswers = function collectAnswers(container) {
  const answers = {};
  container.querySelectorAll("[data-answer-input]").forEach((input) => {
    answers[input.dataset.answerInput] = input.value.trim();
  });
  return answers;
};

window.applyAnswerDrafts = function applyAnswerDrafts(container, answers = {}) {
  container.querySelectorAll("[data-answer-input]").forEach((input) => {
    const nextValue = answers[input.dataset.answerInput];
    if (typeof nextValue === "string") input.value = nextValue;
  });
};

window.persistExamWorkspaceViewport = function persistExamWorkspaceViewport(target = null) {
  if (!els.examWorkspace || els.examWorkspace.classList.contains("hidden")) return;
  state.examWorkspaceScrollY = window.scrollY;
  const candidate = target?.closest?.("[data-answer-input]");
  const activeElement = document.activeElement && typeof document.activeElement.closest === "function"
    ? document.activeElement.closest("[data-answer-input]")
    : null;
  const answerInput = candidate || activeElement;
  if (answerInput?.dataset?.answerInput) state.examFocusedAnswerId = answerInput.dataset.answerInput;
  persistExamUiPreferences();
};

window.scheduleExamWorkspaceViewportPersist = function scheduleExamWorkspaceViewportPersist(target = null) {
  if (examViewportPersistTimer) clearTimeout(examViewportPersistTimer);
  examViewportPersistTimer = window.setTimeout(() => {
    persistExamWorkspaceViewport(target);
  }, 120);
};

window.restoreExamWorkspaceViewport = function restoreExamWorkspaceViewport() {
  if (!state.restoreExamViewport) return;
  state.restoreExamViewport = false;
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      const inputs = Array.from(document.querySelectorAll("[data-answer-input]"));
      const focusedField = inputs.find((input) => input.dataset.answerInput === state.examFocusedAnswerId);
      if (focusedField) {
        focusedField.focus({ preventScroll: true });
        focusedField.scrollIntoView({ block: "center", behavior: "auto" });
        return;
      }
      window.scrollTo({ top: state.examWorkspaceScrollY || 0, behavior: "auto" });
    });
  });
};

window.getEvaluationStatusMeta = function getEvaluationStatusMeta(status) {
  const registry = {
    empty: { label: "Leer", copy: "Hier fehlt noch eine verwertbare Antwort." },
    incorrect: { label: "Falsch", copy: "Die Lösung passt nicht zum offiziellen Schlüssel." },
    weak: { label: "Zu schwach", copy: "Die Aufgabe verfehlt zentrale Anforderungen noch deutlich." },
    partial: { label: "Teilweise", copy: "Ein Teil der Aufgabe ist erkennbar gelöst, aber noch nicht stabil genug." },
    strong: { label: "Stark", copy: "Die Leistung ist tragfähig, aber noch nicht in der Top-Band." },
    excellent: { label: "Sehr stark", copy: "Die Leistung liegt in der hohen Goethe-aligned Band." },
    correct: { label: "Richtig", copy: "Die Aufgabe stimmt mit dem Lösungsschlüssel überein." },
  };
  return registry[status] || { label: "Geprüft", copy: "Die Aufgabe wurde ausgewertet." };
};

window.getEvaluationActionHint = function getEvaluationActionHint(status, errorTags = []) {
  const tags = Array.from(new Set((errorTags || []).map((item) => String(item?.tag || ""))));
  if (tags.includes("aufgabenbezug")) return "Bearbeiten Sie alle Leitpunkte sichtbarer und bleiben Sie enger an der Aufgabe.";
  if (tags.includes("interaktion")) return "Reagieren Sie deutlicher auf Rückfragen, Gegenargumente oder Gesprächsimpulse.";
  if (tags.includes("register")) return "Passen Sie Ton und Adressatenbezug konsequenter an die Prüfungssituation an.";
  if (tags.includes("koharenz")) return "Strukturieren Sie den Beitrag klarer mit Einleitung, Entwicklung und Abschluss.";
  if (tags.includes("wortschatz")) return "Präzisieren Sie Wortwahl und Formulierungen, statt sich zu wiederholen.";
  if (tags.includes("grammatik") || tags.includes("wortstellung")) return "Arbeiten Sie an sprachlicher Genauigkeit und an sauberen Satzstrukturen.";
  if (status === "empty") return "Beantworten Sie die Aufgabe zuerst vollständig, bevor Sie an Feinheiten arbeiten.";
  if (status === "partial") return "Schließen Sie die größten Lücken in Aufgabenbezug, Struktur oder Register.";
  if (status === "strong") return "Feinschliff: decken Sie alle Punkte ab und machen Sie die Leistung noch präziser.";
  if (status === "excellent" || status === "correct") return "Niveau halten und vor allem unter Zeitdruck stabil reproduzieren.";
  return "Bearbeiten Sie zuerst die größte inhaltliche oder sprachliche Schwäche dieser Aufgabe.";
};

window.renderEvaluationErrorTags = function renderEvaluationErrorTags(errorTags = [], className = "evaluation-review-tag") {
  const unique = [];
  const seen = new Set();
  (errorTags || []).forEach((item) => {
    const label = String(item?.label || item?.tag || "").trim();
    if (!label) return;
    const key = `${label}|${String(item?.description || "").trim()}`;
    if (seen.has(key)) return;
    seen.add(key);
    unique.push({ label, description: String(item?.description || "").trim() });
  });
  return unique.map((item) => `<span class="${escapeHtml(className)}" title="${escapeHtml(item.description || item.label)}">${escapeHtml(item.label)}</span>`).join("");
};

window.renderEvaluation = function renderEvaluation(container, payload) {
  const results = payload.results || [];
  const answeredCount = Number(payload.answered_count ?? results.filter((item) => String(item.user_answer || "").trim()).length);
  const totalCount = results.length;
  const unansweredCount = Number(payload.unanswered_count ?? Math.max(0, totalCount - answeredCount));
  const passed = payload.passed === true;
  const statusTone = answeredCount === 0 ? "is-empty" : (passed ? "is-pass" : "is-fail");
  const statusLabel = answeredCount === 0 ? "Leer abgegeben" : (passed ? "Im Zielbereich" : "Noch nicht bestanden");
  const failedSections = Array.isArray(payload.failed_sections) ? payload.failed_sections : [];
  const resultStatusCounts = results.reduce((acc, item) => {
    const key = String(item.status || "partial");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const breakdownCards = [
    { label: "Leer", value: resultStatusCounts.empty || 0, tone: "is-empty" },
    { label: "Kritisch", value: (resultStatusCounts.weak || 0) + (resultStatusCounts.incorrect || 0), tone: "is-weak" },
    { label: "Teilweise", value: resultStatusCounts.partial || 0, tone: "is-partial" },
    { label: "Stark", value: (resultStatusCounts.strong || 0) + (resultStatusCounts.excellent || 0) + (resultStatusCounts.correct || 0), tone: "is-excellent" },
  ].map((item) => `
    <article class="evaluation-breakdown-card ${item.tone}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(String(item.value))}</strong>
    </article>
  `).join("");
  const focusCards = [];
  if (unansweredCount > 0) {
    focusCards.push(`
      <article class="evaluation-focus-card is-empty">
        <p class="exam-kicker">Sofort schliessen</p>
        <strong>${escapeHtml(String(unansweredCount))} Aufgaben sind noch leer</strong>
        <p>Leere Antworten kosten direkt Punkte und blockieren oft ganze Teilnoten.</p>
      </article>
    `);
  }
  if (failedSections.length) {
    focusCards.push(`
      <article class="evaluation-focus-card is-weak">
        <p class="exam-kicker">Sektionen unter Ziel</p>
        <strong>${escapeHtml(failedSections.join(", "))}</strong>
        <p>Diese Bereiche liegen noch unter der pruefungsnahen Schwelle.</p>
      </article>
    `);
  }
  if ((payload.recurring_errors || []).length) {
    const firstError = payload.recurring_errors[0];
    focusCards.push(`
      <article class="evaluation-focus-card is-partial">
        <p class="exam-kicker">Haeufigster Blocker</p>
        <strong>${escapeHtml(firstError.label)}</strong>
        <p>${escapeHtml(firstError.description)}</p>
      </article>
    `);
  }
  const sections = (payload.section_scores || []).map((item) => `
    <article class="evaluation-section-card ${item.passed ? "is-pass" : "is-fail"}">
      <div class="evaluation-section-head">
        <strong>${escapeHtml(item.label)}</strong>
        <span class="evaluation-inline-pill ${item.passed ? "is-excellent" : "is-weak"}">${item.passed ? "Bestanden" : "Offen"}</span>
      </div>
      <p>${escapeHtml(item.score)} / ${escapeHtml(item.max_score)} · Schwelle ${escapeHtml(item.pass_points)}</p>
      <div class="evaluation-progress-bar" aria-hidden="true"><span style="width:${escapeHtml(String(item.max_score ? Math.round((item.score / item.max_score) * 100) : 0))}%"></span></div>
      <p class="muted">${escapeHtml((item.criteria || []).join(" · "))}</p>
      <p>${escapeHtml(item.note || "")}</p>
    </article>
  `).join("");
  const recurring = (payload.recurring_errors || []).map((item) => `<li><strong>${escapeHtml(item.label)}</strong>: ${escapeHtml(item.description)}</li>`).join("");
  const drills = (payload.mini_drills || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const study = (payload.study_plan || []).map((item) => `<li><strong>${escapeHtml(item.title)}</strong>: ${escapeHtml(item.action)}</li>`).join("");
  const statusLabels = {
    empty: "Leer",
    incorrect: "Falsch",
    weak: "Zu schwach",
    partial: "Teilweise",
    strong: "Stark",
    excellent: "Sehr stark",
    correct: "Richtig",
  };
  const reviewFilterNote = payload.review_filter_label
    ? `
      <div class="evaluation-review-filter-note">
        <span class="evaluation-inline-pill is-partial">${escapeHtml(payload.review_filter_label)}</span>
        <p>${escapeHtml(payload.review_filter_copy || "Die Aufgabenauswahl wurde fuer diese Ansicht gefiltert.")}</p>
      </div>
    `
    : "";
  const review = results.map((item) => `
    <article class="evaluation-review-card is-${escapeHtml(item.status || "partial")}">
      <div class="evaluation-review-head">
        <strong>${escapeHtml(item.prompt)}</strong>
        <span class="evaluation-inline-pill is-${escapeHtml(item.status || "partial")}">${escapeHtml(statusLabels[item.status] || "Geprüft")}</span>
      </div>
      <p class="evaluation-review-score">${escapeHtml(item.score)} / ${escapeHtml(item.max_score)}</p>
      <p class="evaluation-review-copy">${escapeHtml(getEvaluationStatusMeta(item.status || "partial").copy)}</p>
      ${item.user_answer ? `<p><strong>Ihre Antwort:</strong> ${escapeHtml(item.user_answer)}</p>` : "<p><strong>Ihre Antwort:</strong> <span class='muted'>leer</span></p>"}
      ${item.expected_answer ? `<p><strong>Erwartet:</strong> ${escapeHtml(item.expected_answer)}</p>` : ""}
      ${item.corrected_version ? `<p><strong>Überarbeitete Version:</strong> ${escapeHtml(item.corrected_version)}</p>` : ""}
      ${item.error_tags?.length ? `<div class="evaluation-review-tags">${renderEvaluationErrorTags(item.error_tags)}</div>` : ""}
      <p class="muted">${escapeHtml(item.feedback || "")}</p>
      <p class="evaluation-review-next"><strong>Nächster Schritt:</strong> ${escapeHtml(getEvaluationActionHint(item.status || "partial", item.error_tags || []))}</p>
    </article>
  `).join("");
  container.innerHTML = `
    <div class="evaluation-shell">
      <section class="evaluation-hero ${statusTone}">
        <div>
          <p class="exam-kicker">Goethe-aligned Evaluation</p>
          <strong>${escapeHtml(payload.title)}</strong>
          <p>${escapeHtml(payload.summary)}</p>
          <p class="muted">${escapeHtml(payload.official_alignment || "")}</p>
        </div>
        <div class="evaluation-hero-meta">
          <span class="evaluation-status-pill ${statusTone}">${escapeHtml(statusLabel)}</span>
          <strong class="evaluation-score">${escapeHtml(payload.score)} / ${escapeHtml(payload.max_score)}</strong>
          <p class="muted">${escapeHtml(payload.percent)}% · Schwelle ${escapeHtml(payload.pass_threshold || 60)}%</p>
        </div>
      </section>
      <section class="evaluation-stat-grid">
        <article class="evaluation-stat-card">
          <span>Beantwortet</span>
          <strong>${escapeHtml(answeredCount)}</strong>
        </article>
        <article class="evaluation-stat-card">
          <span>Offen</span>
          <strong>${escapeHtml(unansweredCount)}</strong>
        </article>
        <article class="evaluation-stat-card">
          <span>Sektionen im Ziel</span>
          <strong>${escapeHtml((payload.section_scores || []).filter((item) => item.passed).length)} / ${escapeHtml((payload.section_scores || []).length)}</strong>
        </article>
        <article class="evaluation-stat-card">
          <span>Prüfstatus</span>
          <strong>${escapeHtml(failedSections.length ? failedSections.join(", ") : "Keine offenen Sektionen")}</strong>
        </article>
      </section>
      <section>
        <h3>Statusverteilung</h3>
        <div class="evaluation-breakdown-grid">${breakdownCards}</div>
      </section>
      ${focusCards.length ? `<section><h3>Was jetzt am meisten zaehlt</h3><div class="evaluation-focus-grid">${focusCards.join("")}</div></section>` : ""}
      <section>
        <h3>Teilnoten</h3>
        <div class="evaluation-section-grid">${sections || "<p class='muted'>Noch keine Teilnoten vorhanden.</p>"}</div>
      </section>
      <section class="evaluation-support-grid">
        <article class="list-item">
          <h3>Wiederkehrende Fehler</h3>
          <ul class="simple-list">${recurring || "<li>Keine wiederkehrenden Fehler erkannt.</li>"}</ul>
        </article>
        <article class="list-item">
          <h3>Mini-Drills</h3>
          <ul class="simple-list">${drills || "<li>Keine Mini-Drills vorgeschlagen.</li>"}</ul>
        </article>
        <article class="list-item">
          <h3>Nächster Lernplan</h3>
          <ul class="simple-list">${study || "<li>Kein Lernplan vorhanden.</li>"}</ul>
        </article>
      </section>
      ${review ? `<section><h3>Aufgabenreview</h3>${reviewFilterNote}<div class="evaluation-review-grid">${review}</div></section>` : ""}
    </div>
  `;
};

window.renderExamTimerBadge = function renderExamTimerBadge(milliseconds = 0, paused = false) {
  if (!els.examTimer) return;
  const safeMs = Math.max(0, Number(milliseconds) || 0);
  const totalSeconds = Math.floor(safeMs / 1000);
  const label = `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
  const visible = paused || safeMs > 0 || state.examWorkspaceActive === true;
  els.examTimer.textContent = paused && safeMs > 0 ? `Pausiert · ${label}` : label;
  els.examTimer.classList.toggle("hidden", !visible);
  els.examTimer.classList.toggle("paused", paused && safeMs > 0);
};

window.syncPersistedExamTimerBadge = function syncPersistedExamTimerBadge() {
  if (state.examTimerPaused && state.examRemainingMs > 0) {
    renderExamTimerBadge(state.examRemainingMs, true);
    return;
  }
  if (typeof state.examEndsAt === "number" && state.examEndsAt > Date.now()) {
    renderExamTimerBadge(state.examEndsAt - Date.now(), false);
    return;
  }
  renderExamTimerBadge(0, false);
};

window.resetExamTimer = function resetExamTimer() {
  clearInterval(state.examTimerId);
  state.examTimerId = null;
  state.examEndsAt = null;
  state.examRemainingMs = 0;
  state.examTimerPaused = false;
  state.examTimerContextKey = null;
  state.pausedExamSession = null;
  renderExamTimerBadge(0, false);
  persistExamUiPreferences();
};

window.pauseExamTimer = function pauseExamTimer() {
  if (state.examTimerPaused) return;
  clearInterval(state.examTimerId);
  state.examTimerId = null;
  if (typeof state.examEndsAt === "number") {
    state.examRemainingMs = Math.max(0, state.examEndsAt - Date.now());
  }
  state.examEndsAt = null;
  state.examTimerPaused = state.examRemainingMs > 0;
  if (!state.examTimerPaused) state.pausedExamSession = null;
  renderExamTimerBadge(state.examRemainingMs, state.examTimerPaused);
  persistExamUiPreferences();
};

window.startExamTimer = function startExamTimer(minutes, endsAt = null, contextKey = null) {
  clearInterval(state.examTimerId);
  state.examTimerPaused = false;
  state.examTimerContextKey = contextKey || state.examTimerContextKey;
  state.pausedExamSession = null;
  state.examEndsAt = typeof endsAt === "number" ? endsAt : Date.now() + minutes * 60 * 1000;
  state.examRemainingMs = Math.max(0, state.examEndsAt - Date.now());
  persistExamUiPreferences();
  const tick = () => {
    const diff = Math.max(0, state.examEndsAt - Date.now());
    state.examRemainingMs = diff;
    renderExamTimerBadge(diff, false);
    if (diff <= 0) {
      clearInterval(state.examTimerId);
      state.examTimerId = null;
      state.examEndsAt = null;
      state.examRemainingMs = 0;
      state.examTimerPaused = false;
      state.examTimerContextKey = null;
      state.pausedExamSession = null;
      persistExamUiPreferences();
    }
  };
  tick();
  state.examTimerId = setInterval(tick, 1000);
};

window.renderRoadmap = function renderRoadmap(payload, container) {
  if (!payload) {
    container.textContent = "Noch kein Lernplan vorhanden.";
    return;
  }
  container.innerHTML = `<p><strong>${escapeHtml(payload.title)}</strong></p><p>${escapeHtml(payload.summary)}</p><h3>Was Sie können müssen</h3><ul class="simple-list">${(payload.must_know || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Wochenplan</h3>${(payload.weekly_plan || []).map((item) => `<article class="list-item"><strong>Woche ${escapeHtml(item.week)} · ${escapeHtml(item.title)}</strong><p>${escapeHtml(item.focus)}</p><ul class="simple-list">${(item.tasks || []).map((task) => `<li>${escapeHtml(task)}</li>`).join("")}</ul><p class="muted">${escapeHtml(item.checkpoint)}</p></article>`).join("")}`;
};

window.renderTheory = function renderTheory(payload) {
  els.grammarTheoryBox.innerHTML = `<p><strong>Wann lernen?</strong> ${escapeHtml(payload.when_to_study)}</p><h3>Kernregeln</h3><ul class="simple-list">${(payload.core_rules || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Ausführliche Erklärung</h3><ul class="simple-list">${(payload.deep_dive || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Ausnahmen und Grenzen</h3><ul class="simple-list">${(payload.exceptions || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Beispiele</h3><ul class="simple-list">${(payload.examples || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><h3>Typische Fehler</h3><ul class="simple-list">${(payload.common_mistakes || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul><p><strong>Merkhilfe:</strong> ${escapeHtml(payload.memory_hook || "")}</p><p><strong>Verwandte Themen:</strong> ${escapeHtml((payload.related_topics || []).join(", ")) || "—"}</p><p><strong>Referenzen:</strong> ${escapeHtml((payload.references || []).join(" · ")) || "—"}</p>`;
};

window.renderReviewCard = function renderReviewCard() {
  if (!state.reviewCard) {
    els.reviewCardBox.innerHTML = `
      <div class="review-card-empty-state">
        <strong>Ready for the next card</strong>
        <p>Choose a deck filter if needed, then load the next review item to start the session.</p>
      </div>
    `;
    return;
  }
  const extra = state.reviewCard.extra || {};
  const tags = (state.reviewCard.tags || []).slice(0, 4);
  const back = state.reviewBackVisible
    ? `
      <hr />
      <p class="review-card-answer">${escapeHtml(state.reviewCard.back)}</p>
      ${extra.example ? `<p class="muted">${escapeHtml(extra.example)}</p>` : ""}
      ${extra.notes ? `<p class="muted">${escapeHtml(extra.notes)}</p>` : ""}
      ${extra.note ? `<p class="muted">${escapeHtml(extra.note)}</p>` : ""}
    `
    : `<p class="muted">Flip the card to reveal the answer, then grade recall quality.</p>`;
  els.reviewCardBox.innerHTML = `
    <div class="review-card-shell ${state.reviewBackVisible ? "is-back" : "is-front"}">
      <p class="review-card-kicker">${state.reviewBackVisible ? "Answer" : "Prompt"}</p>
      <strong>${escapeHtml(state.reviewCard.front)}</strong>
      ${tags.length ? `<div class="review-card-tag-row">${tags.map((tag) => `<span class="review-card-tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
      ${back}
    </div>
  `;
};
