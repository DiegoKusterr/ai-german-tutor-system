window.loadSettings = async function loadSettings() {
  state.settings = await apiFetch("/api/settings");
  els.uiLanguageSelect.value = state.settings.interface_language;
  els.explanationLanguageSelect.value = state.settings.explanation_language;
  els.settingsGoalExam.value = state.settings.default_goal_exam;
  els.settingsGoalLevel.value = state.settings.default_goal_level;
  els.roadmapTargetExam.value = state.settings.default_goal_exam;
  els.roadmapTargetLevel.value = state.settings.default_goal_level;
  refreshMockAudioVoiceUi();
  const languageLabels = {
    de: "Deutsch",
    en: "Englisch",
    es: "Spanisch",
    fr: "Französisch",
    it: "Italienisch",
    pt: "Portugiesisch",
  };
  if (els.settingsState) {
    els.settingsState.textContent = `Oberfläche: ${languageLabels[state.settings.interface_language] || state.settings.interface_language} · Erklärungen: ${languageLabels[state.settings.explanation_language] || state.settings.explanation_language}.`;
  }
  applyLanguage();
};

window.formatGoalExamLabel = function formatGoalExamLabel(examKey) {
  const labels = {
    goethe_a1: "Goethe-Zertifikat A1",
    goethe_a2: "Goethe-Zertifikat A2",
    goethe_b1: "Goethe-Zertifikat B1",
    goethe_b2: "Goethe-Zertifikat B2",
    goethe_c1: "Goethe-Zertifikat C1",
    goethe_c2: "Goethe-Zertifikat C2",
    telc_b2: "telc B2",
    oesd_b2: "ÖSD B2",
    testdaf: "TestDaF",
  };
  return labels[String(examKey || "").trim()] || String(examKey || "").replace(/_/g, " ").trim() || "Goethe-Zertifikat B2";
};

window.saveSettings = async function saveSettings() {
  setStatus("Einstellungen werden gespeichert ...");
  state.settings = await apiFetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      interface_language: els.uiLanguageSelect.value,
      explanation_language: els.explanationLanguageSelect.value,
      default_goal_exam: els.settingsGoalExam.value,
      default_goal_level: els.settingsGoalLevel.value,
    }),
  });
  els.settingsState.textContent = `Gespeichert: UI ${state.settings.interface_language}, Erklärungen ${state.settings.explanation_language}.`;
  refreshMockAudioVoiceUi();
  applyLanguage();
  refreshHeroMetrics();
  setStatus("Einstellungen gespeichert.");
};

window.loadConfig = async function loadConfig() {
  state.config = await apiFetch("/config");
};

window.refreshChatHistory = async function refreshChatHistory() {
  const preferredConversationId = state.conversationId || els.chatHistorySelect.value || "";
  const items = await apiFetch("/api/chat/history");
  state.chatHistoryItems = items || [];
  els.chatHistorySelect.innerHTML = items.map((item) => `<option value="${escapeHtml(item.conversation_id)}">${escapeHtml(item.preview || item.conversation_id)}</option>`).join("");
  if (preferredConversationId && (items || []).some((item) => item.conversation_id === preferredConversationId)) {
    els.chatHistorySelect.value = preferredConversationId;
  }
  if (typeof window.renderHome === "function") window.renderHome();
};

window.isChatMutationBusy = function isChatMutationBusy() {
  const tutorSessionState = state.tutorSession?.state || "idle";
  return Boolean(
    state.chatRequestInFlight
    || state.chatTranscribeInFlight
    || ["thinking", "streaming"].includes(tutorSessionState)
  );
};

window.chatMessageWasEdited = function chatMessageWasEdited(entry) {
  return Number(entry?.version_index || 1) > 1 || Boolean(entry?.edited_from_id);
};

window.chatMessageHasVersionHistory = function chatMessageHasVersionHistory(entry) {
  return Boolean(entry?.id);
};

window.getChatTranscriptEntryById = function getChatTranscriptEntryById(entryId) {
  const targetId = String(entryId || "").trim();
  return (state.chatTranscriptEntries || []).find((item) => item.id === targetId) || null;
};

window.getChatTranscriptEntryByIdFromList = function getChatTranscriptEntryByIdFromList(entries, entryId) {
  const targetId = String(entryId || "").trim();
  if (!targetId) return null;
  return (Array.isArray(entries) ? entries : []).find((item) => String(item?.id || "") === targetId) || null;
};

window.chatEntryHasLaterActiveContent = function chatEntryHasLaterActiveContent(entryId) {
  const entries = Array.isArray(state.chatTranscriptEntries) ? state.chatTranscriptEntries : [];
  const entryIndex = entries.findIndex((item) => item.id === entryId);
  return entryIndex >= 0 && entryIndex < entries.length - 1;
};

window.renderChatBubbleText = function renderChatBubbleText(target, text) {
  if (!target) return;
  target.innerHTML = escapeHtml(String(text || "")).replace(/\n/g, "<br />");
};

window.describeChatVersionSource = function describeChatVersionSource(entry) {
  const source = String(entry?.meta?.source || "").trim().toLowerCase();
  if (source === "restored") return "restored";
  if (source === "edited") return "edited";
  if (source === "legacy") return "original";
  if (Number(entry?.version_index || 1) <= 1) return "original";
  return "edited";
};

window.renderChatTranscript = function renderChatTranscript(
  entries = state.chatTranscriptEntries || [],
  {
    preserveScroll = false,
  } = {},
) {
  if (!els.chatMessages) return;
  const transcriptEntries = Array.isArray(entries) ? entries : [];
  const previousScrollTop = els.chatMessages.scrollTop;
  const previousScrollHeight = els.chatMessages.scrollHeight;
  els.chatMessages.innerHTML = "";

  transcriptEntries.forEach((entry) => {
    const role = entry?.role === "assistant" ? "assistant" : "user";
    const bubble = document.createElement("div");
    bubble.className = ["bubble", role, role === "user" ? "is-editable" : ""].filter(Boolean).join(" ");
    bubble.dataset.entryId = String(entry?.id || "");
    bubble.dataset.role = role;
    if (role === "user" && chatMessageWasEdited(entry)) bubble.classList.add("is-edited");

    const body = document.createElement("div");
    body.className = "chat-bubble-body";
    bubble.appendChild(body);

    if (role !== "user") {
      renderChatBubbleText(body, entry?.text || "");
      els.chatMessages.appendChild(bubble);
      return;
    }

    const isEditing = state.chatEditingEntryId === entry.id;
    const showVersions = state.chatVersionsEntryId === entry.id;
    const canShowVersions = chatMessageHasVersionHistory(entry);
    const busy = isChatMutationBusy();

    if (isEditing) {
      const editor = document.createElement("div");
      editor.className = "chat-inline-editor";

      const textarea = document.createElement("textarea");
      textarea.className = "chat-inline-editor-input";
      textarea.value = String(entry?.text || "");
      textarea.setAttribute("rows", "4");
      textarea.dataset.chatEditInput = String(entry.id || "");
      editor.appendChild(textarea);

      const actions = document.createElement("div");
      actions.className = "chat-inline-editor-actions";

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "ghost-btn";
      cancelBtn.dataset.chatAction = "cancel-edit";
      cancelBtn.dataset.entryId = String(entry.id || "");
      cancelBtn.textContent = "Abbrechen";
      actions.appendChild(cancelBtn);

      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "primary-btn";
      saveBtn.dataset.chatAction = "save-edit";
      saveBtn.dataset.entryId = String(entry.id || "");
      saveBtn.textContent = "Speichern";
      actions.appendChild(saveBtn);

      editor.appendChild(actions);
      body.appendChild(editor);
      els.chatMessages.appendChild(bubble);
      return;
    }

    const textEl = document.createElement("div");
    textEl.className = "chat-bubble-text";
    renderChatBubbleText(textEl, entry?.text || "");
    body.appendChild(textEl);

    const footer = document.createElement("div");
    footer.className = "chat-bubble-footer";

    const meta = document.createElement("div");
    meta.className = "chat-bubble-meta";
    if (chatMessageWasEdited(entry)) {
      const editedBadge = document.createElement("span");
      editedBadge.className = "chat-bubble-badge";
      editedBadge.textContent = "bearbeitet";
      meta.appendChild(editedBadge);

      const versionBadge = document.createElement("span");
      versionBadge.className = "chat-bubble-version";
      versionBadge.textContent = `v${Number(entry?.version_index || 1)}`;
      meta.appendChild(versionBadge);
    }
    footer.appendChild(meta);

    const actions = document.createElement("div");
    actions.className = "chat-bubble-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "ghost-btn";
    editBtn.dataset.chatAction = "edit";
    editBtn.dataset.entryId = String(entry.id || "");
    editBtn.textContent = "Bearbeiten";
    editBtn.disabled = busy;
    actions.appendChild(editBtn);

    if (canShowVersions) {
      const versionsBtn = document.createElement("button");
      versionsBtn.type = "button";
      versionsBtn.className = "ghost-btn";
      versionsBtn.dataset.chatAction = showVersions ? "close-versions" : "versions";
      versionsBtn.dataset.entryId = String(entry.id || "");
      versionsBtn.textContent = showVersions ? "Versionen ausblenden" : "Versionen";
      versionsBtn.disabled = busy;
      actions.appendChild(versionsBtn);
    }

    footer.appendChild(actions);
    body.appendChild(footer);

    if (showVersions) {
      const versionsPanel = document.createElement("div");
      versionsPanel.className = "chat-bubble-versions";
      const cacheEntry = state.chatVersionsCache?.[entry.id];
      if (cacheEntry?.loading) {
        versionsPanel.innerHTML = "<p class='muted'>Versionen werden geladen ...</p>";
      } else if ((cacheEntry?.versions || []).length) {
        (cacheEntry.versions || []).forEach((version) => {
          const item = document.createElement("article");
          item.className = "chat-version-item";

          const head = document.createElement("div");
          head.className = "chat-version-head";

          const label = document.createElement("strong");
          label.textContent = `v${Number(version?.version_index || 1)}`;
          head.appendChild(label);

          const hint = document.createElement("span");
          hint.className = "chat-version-hint";
          hint.textContent = version.id === entry.id ? "aktiv" : describeChatVersionSource(version);
          head.appendChild(hint);
          item.appendChild(head);

          const copy = document.createElement("p");
          copy.className = "chat-version-copy";
          copy.textContent = String(version?.text || "");
          item.appendChild(copy);

          if (version.id !== entry.id) {
            const restoreBtn = document.createElement("button");
            restoreBtn.type = "button";
            restoreBtn.className = "ghost-btn";
            restoreBtn.dataset.chatAction = "restore-version";
            restoreBtn.dataset.entryId = String(entry.id || "");
            restoreBtn.dataset.restoreEntryId = String(version.id || "");
            restoreBtn.textContent = "Wiederherstellen";
            restoreBtn.disabled = busy;
            item.appendChild(restoreBtn);
          }

          versionsPanel.appendChild(item);
        });
      } else {
        versionsPanel.innerHTML = "<p class='muted'>Noch keine aelteren Versionen vorhanden.</p>";
      }
      body.appendChild(versionsPanel);
    }

    els.chatMessages.appendChild(bubble);
  });

  if (preserveScroll) {
    const nextMaxScroll = Math.max(els.chatMessages.scrollHeight - els.chatMessages.clientHeight, 0);
    const heightDelta = els.chatMessages.scrollHeight - previousScrollHeight;
    els.chatMessages.scrollTop = Math.max(0, Math.min(previousScrollTop + heightDelta, nextMaxScroll));
    return;
  }
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
};

window.applyChatTranscriptData = function applyChatTranscriptData(
  data,
  {
    statusMessage = null,
    statusTone = "success",
    resetSupportRail = false,
  } = {},
) {
  state.conversationId = data?.conversation_id || state.conversationId;
  const transcriptPersonaKey = String(data?.persona_key || "").trim().toLowerCase();
  if (["studio", "coach", "examiner"].includes(transcriptPersonaKey)) {
    window.applyTutorAvatarPreference?.();
    if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
  }
  state.chatTranscriptEntries = Array.isArray(data?.transcript)
    ? data.transcript.filter((entry) => !entry?.status || entry.status === "active")
    : [];
  state.chatEditingEntryId = null;
  state.chatVersionsEntryId = null;
  state.chatVersionsCache = {};
  state.chatPendingBubble = null;
  state.chatLastAssistantReply = "";
  state.chatHasCompletedAssistantTurn = false;

  if (
    els.chatHistorySelect
    && state.conversationId
    && Array.from(els.chatHistorySelect.options || []).some((option) => option.value === state.conversationId)
  ) {
    els.chatHistorySelect.value = state.conversationId;
  }

  (state.chatTranscriptEntries || []).forEach((entry) => {
    if (entry.role === "assistant" && String(entry.text || "").trim()) {
      state.chatLastAssistantReply = String(entry.text).trim();
      state.chatHasCompletedAssistantTurn = true;
    }
  });

  if (resetSupportRail) {
    els.chatCorrection.textContent = "Noch keine Korrektur.";
    els.chatFinalFeedback.textContent = "Beenden Sie die Sitzung, um Gesamtfeedback zu sehen.";
    renderTips(els.chatTips, []);
  }

  renderChatTranscript(state.chatTranscriptEntries);
  resetTutorSessionState();
  if (statusMessage) setChatStatus(statusMessage, statusTone);
  refreshChatTtsUi();
  updateChatComposerState();
};

window.scrollChatEntryIntoView = function scrollChatEntryIntoView(entryId, options = {}) {
  if (!els.chatMessages) return;
  const targetId = String(entryId || "").trim();
  if (!targetId) return;
  const bubble = els.chatMessages.querySelector(`[data-entry-id="${CSS.escape(targetId)}"]`);
  bubble?.scrollIntoView({
    block: "center",
    behavior: options.behavior || "smooth",
  });
};

window.getChatMutationAssistantReplyText = function getChatMutationAssistantReplyText(payload) {
  const assistantEntryId = String(payload?.assistant_entry_id || "").trim();
  if (!assistantEntryId) return "";
  const transcriptEntries = Array.isArray(payload?.transcript) ? payload.transcript : state.chatTranscriptEntries;
  const assistantEntry = getChatTranscriptEntryByIdFromList(transcriptEntries, assistantEntryId);
  if (!assistantEntry || assistantEntry.role !== "assistant") return "";
  return String(assistantEntry.text || "").trim();
};

window.playChatMutationAssistantReply = function playChatMutationAssistantReply(payload, options = {}) {
  const assistantText = getChatMutationAssistantReplyText(payload);
  const assistantEntryId = String(payload?.assistant_entry_id || "").trim();
  if (!assistantText) return false;
  if (typeof window.playTutorReplyAudio === "function") {
    return window.playTutorReplyAudio(assistantText, {
      turnId: assistantEntryId || undefined,
      source: options.source || "mutation",
    });
  }
  window.speakChatReply?.(assistantText);
  return true;
};

window.reopenChatVersionsForEntry = async function reopenChatVersionsForEntry(entryId) {
  const targetId = String(entryId || "").trim();
  if (!targetId) return;
  try {
    await openChatVersions(targetId);
  } finally {
    window.requestAnimationFrame(() => {
      scrollChatEntryIntoView(targetId);
    });
  }
};

window.reloadActiveChatTranscript = async function reloadActiveChatTranscript(
  {
    silent = false,
    resetSupportRail = false,
    conversationId = null,
    applyIfConversationChanged = false,
  } = {},
) {
  const targetConversationId = String(conversationId || state.conversationId || "").trim();
  if (!targetConversationId) return null;
  const data = await apiFetch(`/api/chat/transcript/${targetConversationId}`);
  if (
    !applyIfConversationChanged
    && conversationId
    && state.conversationId
    && state.conversationId !== targetConversationId
  ) {
    return data;
  }
  applyChatTranscriptData(data, {
    statusMessage: silent ? null : "Verlauf geladen.",
    statusTone: "success",
    resetSupportRail,
  });
  return data;
};

window.beginChatEntryEdit = function beginChatEntryEdit(entryId) {
  if (isChatMutationBusy()) return;
  const entry = getChatTranscriptEntryById(entryId);
  if (!entry || entry.role !== "user") return;
  state.chatEditingEntryId = entry.id;
  state.chatVersionsEntryId = null;
  renderChatTranscript(undefined, { preserveScroll: true });
  window.requestAnimationFrame(() => {
    const input = els.chatMessages.querySelector(`[data-chat-edit-input="${CSS.escape(String(entry.id || ""))}"]`);
    input?.focus();
    if (input?.setSelectionRange) {
      const value = String(input.value || "");
      input.setSelectionRange(value.length, value.length);
    }
  });
};

window.cancelChatEntryEdit = function cancelChatEntryEdit() {
  state.chatEditingEntryId = null;
  renderChatTranscript(undefined, { preserveScroll: true });
};

window.openChatVersions = async function openChatVersions(entryId) {
  if (isChatMutationBusy()) return;
  const entry = getChatTranscriptEntryById(entryId);
  if (!entry || entry.role !== "user" || !chatMessageHasVersionHistory(entry)) return;
  state.chatEditingEntryId = null;
  state.chatVersionsEntryId = entry.id;
  state.chatVersionsCache = {
    ...state.chatVersionsCache,
    [entry.id]: { loading: true, versions: [] },
  };
  renderChatTranscript(undefined, { preserveScroll: true });
  try {
    const payload = await apiFetch(`/api/chat/transcript/${state.conversationId}/message/${entry.id}/versions`);
    state.chatVersionsCache = {
      ...state.chatVersionsCache,
      [entry.id]: { loading: false, versions: Array.isArray(payload?.versions) ? payload.versions : [] },
    };
    renderChatTranscript(undefined, { preserveScroll: true });
  } catch (error) {
    state.chatVersionsCache = {
      ...state.chatVersionsCache,
      [entry.id]: { loading: false, versions: [] },
    };
    renderChatTranscript(undefined, { preserveScroll: true });
    setChatStatus(error.message || "Versionen konnten nicht geladen werden.", "error");
  }
};

window.closeChatVersions = function closeChatVersions() {
  state.chatVersionsEntryId = null;
  renderChatTranscript(undefined, { preserveScroll: true });
};

window.saveChatEntryEdit = async function saveChatEntryEdit(entryId) {
  const entry = getChatTranscriptEntryById(entryId);
  if (!entry || entry.role !== "user" || isChatMutationBusy()) return;
  const input = els.chatMessages.querySelector(`[data-chat-edit-input="${CSS.escape(String(entry.id || ""))}"]`);
  const text = String(input?.value || "").trim();
  if (!text) {
    setChatStatus("Der bearbeitete Text darf nicht leer sein.", "error");
    return;
  }
  if (text === String(entry.text || "").trim()) {
    state.chatEditingEntryId = null;
    renderChatTranscript(undefined, { preserveScroll: true });
    return;
  }
  if (chatEntryHasLaterActiveContent(entry.id)) {
    const confirmed = await openConfirmModal({
      title: "Nachrichtenverlauf neu aufbauen?",
      message: "Ab dieser Nachricht wird der aktive Verlauf ersetzt. Spätere Antworten werden aus dem aktiven Chat entfernt.",
      confirmLabel: "Änderung speichern",
      cancelLabel: "Abbrechen",
    });
    if (!confirmed) return;
  }
  stopChatSpeech();
  state.chatRequestInFlight = true;
  setChatStatus("Nachricht wird neu aufgebaut ...", "busy");
  updateChatComposerState();
  let mutationPayload = null;
  try {
    const payload = await apiFetch("/api/chat/message/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: state.conversationId,
        entry_id: entry.id,
        text,
      }),
    });
    mutationPayload = payload;
    applyChatTranscriptData(payload, {
      statusMessage: "Nachricht aktualisiert. Tutor-Antwort neu erzeugt.",
      statusTone: "success",
      resetSupportRail: true,
    });
    pushAppToast("Nachricht bearbeitet.", "success", 2600);
    refreshChatHistory().catch((historyError) => {
      setStatus(`Chatverlauf konnte nicht aktualisiert werden: ${historyError.message}`);
    });
  } catch (error) {
    setChatStatus(error.message || "Nachricht konnte nicht bearbeitet werden.", "error");
  } finally {
    state.chatRequestInFlight = false;
    updateChatComposerState();
  }
  if (mutationPayload) {
    playChatMutationAssistantReply(mutationPayload, { source: "edit" });
    reopenChatVersionsForEntry(mutationPayload.entry_id).catch((error) => {
      setChatStatus(error.message || "Versionen konnten nicht geladen werden.", "error");
    });
  }
};

window.restoreChatEntryVersion = async function restoreChatEntryVersion(entryId, restoreFromEntryId) {
  const entry = getChatTranscriptEntryById(entryId);
  if (!entry || entry.role !== "user" || isChatMutationBusy()) return;
  const confirmed = await openConfirmModal({
    title: "Version wiederherstellen?",
    message: "Die ältere Version wird wieder aktiv und der spätere aktive Verlauf wird ab diesem Punkt ersetzt.",
    confirmLabel: "Version wiederherstellen",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  stopChatSpeech();
  state.chatRequestInFlight = true;
  setChatStatus("Version wird wiederhergestellt ...", "busy");
  updateChatComposerState();
  let mutationPayload = null;
  try {
    const payload = await apiFetch("/api/chat/message/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: state.conversationId,
        entry_id: entry.id,
        restore_from_entry_id: restoreFromEntryId,
      }),
    });
    mutationPayload = payload;
    applyChatTranscriptData(payload, {
      statusMessage: "Frühere Version wiederhergestellt.",
      statusTone: "success",
      resetSupportRail: true,
    });
    pushAppToast("Version wiederhergestellt.", "success", 2600);
    refreshChatHistory().catch((historyError) => {
      setStatus(`Chatverlauf konnte nicht aktualisiert werden: ${historyError.message}`);
    });
  } catch (error) {
    setChatStatus(error.message || "Version konnte nicht wiederhergestellt werden.", "error");
  } finally {
    state.chatRequestInFlight = false;
    updateChatComposerState();
  }
  if (mutationPayload) {
    playChatMutationAssistantReply(mutationPayload, { source: "restore" });
    reopenChatVersionsForEntry(mutationPayload.entry_id).catch((error) => {
      setChatStatus(error.message || "Versionen konnten nicht geladen werden.", "error");
    });
  }
};

window.setChatStatus = function setChatStatus(message, tone = "neutral") {
  if (!els.chatStatus) return;
  els.chatStatus.textContent = message;
  els.chatStatus.classList.remove("is-busy", "is-error", "is-success");
  if (tone === "busy") els.chatStatus.classList.add("is-busy");
  if (tone === "error") els.chatStatus.classList.add("is-error");
  if (tone === "success") els.chatStatus.classList.add("is-success");
};

window.updateChatComposerState = function updateChatComposerState() {
  const tutorSessionState = state.tutorSession?.state || "idle";
  const responseBusy = state.chatRequestInFlight || ["thinking", "streaming"].includes(tutorSessionState);
  const sending = Boolean(responseBusy);
  const transcribing = Boolean(state.chatTranscribeInFlight);
  const recording = typeof window.isVoiceInputActiveForTarget === "function"
    ? window.isVoiceInputActiveForTarget("chat")
    : Boolean(state.recorder && state.recordTarget === "chat");
  const busy = sending || transcribing || recording;
  const speechSupported = typeof window.tutorAudioSupported === "function"
    ? window.tutorAudioSupported()
    : window.chatSpeechSupported();
  const browserSpeechSupported = typeof window.chatBrowserSpeechSupported === "function"
    ? window.chatBrowserSpeechSupported()
    : window.chatSpeechSupported();
  const voiceCatalog = Array.isArray(state.chatVoiceCatalog) ? state.chatVoiceCatalog : [];
  const regionalVoices = typeof window.getChatRegionalVoiceOptions === "function"
    ? window.getChatRegionalVoiceOptions()
    : [];

  els.chatSendBtn.disabled = busy;
  els.chatMicBtn.disabled = sending || transcribing;
  els.chatFinishBtn.disabled = busy || !state.chatHasCompletedAssistantTurn;
  els.chatLoadHistoryBtn.disabled = busy;
  els.chatNewBtn.disabled = busy;
  els.chatHistorySelect.disabled = busy;
  if (els.chatMode) els.chatMode.disabled = busy;
  els.chatInput.readOnly = sending;
  if (els.chatInterruptBtn) {
    const canInterrupt = typeof window.canInterruptTutorSession === "function" && window.canInterruptTutorSession();
    els.chatInterruptBtn.classList.toggle("hidden", !canInterrupt);
    els.chatInterruptBtn.disabled = !canInterrupt;
  }
  if (els.chatTtsBtn) els.chatTtsBtn.disabled = !speechSupported || busy;
  if (els.chatReplayBtn) els.chatReplayBtn.disabled = !speechSupported || !state.chatTtsEnabled || !state.chatLastAssistantReply || busy;
  if (els.chatVoiceGender) els.chatVoiceGender.disabled = !browserSpeechSupported || !voiceCatalog.length;
  if (els.chatVoiceVariant) els.chatVoiceVariant.disabled = !browserSpeechSupported || !voiceCatalog.length || !regionalVoices.length;
  if (els.chatVoiceRegion) {
    els.chatVoiceRegion.disabled = (
      !browserSpeechSupported
      || !voiceCatalog.length
      || state.chatVoiceVariant !== "regional"
      || !regionalVoices.length
    );
  }
  if (typeof window.refreshVoiceInputButtons === "function") window.refreshVoiceInputButtons();
};

window.chatSpeechSupported = function chatSpeechSupported() {
  return typeof window.speechSynthesis !== "undefined" && typeof window.SpeechSynthesisUtterance !== "undefined";
};

window.chatBrowserSpeechSupported = function chatBrowserSpeechSupported() {
  return chatSpeechSupported();
};

window.browserSpeechRecognitionSupported = function browserSpeechRecognitionSupported() {
  return typeof window.SpeechRecognition !== "undefined" || typeof window.webkitSpeechRecognition !== "undefined";
};

window.getVoiceInputStatusEl = function getVoiceInputStatusEl(target) {
  return target === "chat" ? els.chatVoiceStatus : els.speakingVoiceStatus;
};

window.getVoiceInputField = function getVoiceInputField(target) {
  return target === "chat" ? els.chatInput : els.speakingInput;
};

window.isVoiceInputActiveForTarget = function isVoiceInputActiveForTarget(target) {
  return Boolean(
    (state.speechRecognitionActive && state.speechRecognitionTarget === target)
    || (state.recorder && state.recordTarget === target)
  );
};

window.refreshVoiceInputButtons = function refreshVoiceInputButtons() {
  const syncButton = (button, target) => {
    if (!button) return;
    const active = isVoiceInputActiveForTarget(target);
    const hasNativeDictation = browserSpeechRecognitionSupported();
    const hasServerFallback = Boolean(state.config?.server_transcribe);
    const available = hasNativeDictation || hasServerFallback;
    const busy = target === "chat" ? Boolean(state.chatRequestInFlight || state.chatTranscribeInFlight) : false;
    const idleLabel = hasNativeDictation ? "Jetzt sprechen" : "Audio aufnehmen";
    const activeLabel = "Spracheingabe stoppen";
    button.classList.toggle("is-listening", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.setAttribute("aria-label", active ? activeLabel : idleLabel);
    button.title = active ? activeLabel : idleLabel;
    button.disabled = busy || (!active && !available);
  };

  syncButton(els.chatMicBtn, "chat");
  syncButton(els.speakingMicBtn, "speaking");
};

window.inferChatVoiceGender = function inferChatVoiceGender(voice) {
  const haystack = `${voice?.name || ""} ${voice?.voiceURI || ""}`.toLowerCase();
  const femaleHints = [
    "female", "frau", "weiblich", "katja", "hedda", "heda", "helena", "helene",
    "vicki", "anna", "petra", "sandra", "marlene", "claudia", "ingrid", "saskia", "lena",
  ];
  const maleHints = [
    "male", "mann", "maennlich", "stefan", "thomas", "markus", "ralf", "daniel",
    "andreas", "jonas", "conrad", "hans", "klaus", "bernd", "jens",
  ];
  if (femaleHints.some((hint) => haystack.includes(hint))) return "female";
  if (maleHints.some((hint) => haystack.includes(hint))) return "male";
  return "unknown";
};

window.getChatVoiceRegionMeta = function getChatVoiceRegionMeta(voice) {
  const lang = String(voice?.lang || "").toLowerCase();
  const haystack = `${voice?.name || ""} ${voice?.voiceURI || ""}`.toLowerCase();
  if (lang.startsWith("de-at") || haystack.includes("austria") || haystack.includes("oesterreich") || haystack.includes("österreich")) {
    return { code: "de-AT", label: "Österreich", variant: "regional" };
  }
  if (lang.startsWith("de-ch") || haystack.includes("swiss") || haystack.includes("schweiz")) {
    return { code: "de-CH", label: "Schweiz", variant: "regional" };
  }
  if (lang.startsWith("de-de") || haystack.includes("germany") || haystack.includes("deutschland")) {
    return { code: "de-DE", label: "Hochdeutsch", variant: "standard" };
  }
  if (lang === "de" || lang.startsWith("de-")) {
    return { code: lang.toUpperCase() || "de-DE", label: "Deutsch", variant: "standard" };
  }
  return null;
};

window.buildChatVoiceCatalog = function buildChatVoiceCatalog() {
  if (!chatBrowserSpeechSupported()) return [];
  const voices = window.speechSynthesis.getVoices() || [];
  return voices
    .map((voice) => {
      const regionMeta = getChatVoiceRegionMeta(voice);
      if (!regionMeta) return null;
      const name = String(voice.name || "");
      return {
        voice,
        name,
        lang: String(voice.lang || ""),
        gender: inferChatVoiceGender(voice),
        regionCode: regionMeta.code,
        regionLabel: regionMeta.label,
        variant: regionMeta.variant,
        isRegional: regionMeta.variant === "regional",
        isNatural: /natural|online|premium|enhanced/i.test(name),
      };
    })
    .filter(Boolean);
};

window.getChatRegionalVoiceOptions = function getChatRegionalVoiceOptions() {
  const groups = new Map();
  (state.chatVoiceCatalog || []).forEach((item) => {
    if (!item?.isRegional || !item.regionCode) return;
    if (!groups.has(item.regionCode)) groups.set(item.regionCode, { value: item.regionCode, label: item.regionLabel });
  });
  return Array.from(groups.values());
};

window.TUTOR_IDENTITY_VOICE_DEBUG = window.TUTOR_IDENTITY_VOICE_DEBUG || { enabled: true };
const tutorIdentityVoiceDebugEnabled = () => Boolean(window.TUTOR_IDENTITY_VOICE_DEBUG?.enabled);
window.logTutorIdentityVoiceDebug = function logTutorIdentityVoiceDebug(eventName, payload = {}) {
  if (!tutorIdentityVoiceDebugEnabled() || typeof console === "undefined" || typeof console.info !== "function") return;
  console.info("[TutorVoiceDebug]", eventName, payload);
};

window.persistChatVoicePreferences = function persistChatVoicePreferences() {
  const resolvedIdentity = state.chatVoiceGender === "male" ? "man" : "woman";
  state.tutorAvatar = resolvedIdentity;
  return writeUiPreferences({
    chatTtsEnabled: state.chatTtsEnabled,
    chatVoiceGender: state.chatVoiceGender,
    chatVoiceVariant: state.chatVoiceVariant,
    chatVoiceRegion: state.chatVoiceRegion,
    tutorAvatar: resolvedIdentity,
    tutorIdentity: resolvedIdentity,
  });
};

window.getChatTtsVoice = function getChatTtsVoice(genderOverride = null) {
  if (!chatBrowserSpeechSupported()) return null;
  const catalog = state.chatVoiceCatalog || [];
  if (!catalog.length) return null;
  const preferredGender = ["auto", "female", "male"].includes(genderOverride) ? genderOverride : state.chatVoiceGender;

  const rankVoice = (item) => {
    let score = 0;
    if (state.chatVoiceVariant === "regional") {
      if (item.isRegional) score += 40;
      else score -= 30;
      if (state.chatVoiceRegion && item.regionCode === state.chatVoiceRegion) score += 24;
    } else {
      if (!item.isRegional) score += 40;
      if (item.regionCode === "de-DE") score += 20;
      else if (item.lang.toLowerCase() === "de") score += 12;
    }
    if (preferredGender !== "auto") {
      if (item.gender === preferredGender) score += 12;
      else if (item.gender !== "unknown") score -= 4;
    }
    if (item.voice?.default) score += 6;
    if (item.isNatural) score += 4;
    if (item.lang.toLowerCase() === "de-de") score += 4;
    return score;
  };

  const sortVoices = (items) => [...items].sort((left, right) => rankVoice(right) - rankVoice(left));
  if (preferredGender !== "auto") {
    const strictMatches = catalog.filter((item) => item.gender === preferredGender);
    if (strictMatches.length) return sortVoices(strictMatches)[0] || null;

    const neutralMatches = catalog.filter((item) => item.gender === "unknown");
    if (neutralMatches.length) return sortVoices(neutralMatches)[0] || null;
  }

  return sortVoices(catalog)[0] || null;
};

const TUTOR_BROWSER_VOICE_EXACT_MAP = {
  woman: [
    {
      name: "Microsoft Katja Online (Natural) - German (Germany)",
      voiceURI: "Microsoft Katja Online (Natural) - German (Germany)",
      lang: "de-DE",
      gender: "female",
    },
  ],
  man: [],
};

window.getTutorBrowserVoiceInventory = function getTutorBrowserVoiceInventory() {
  const catalog = Array.isArray(state.chatVoiceCatalog) && state.chatVoiceCatalog.length
    ? state.chatVoiceCatalog
    : buildChatVoiceCatalog();
  return catalog.map((item) => ({
    voiceURI: item?.voice?.voiceURI || item?.name || "",
    name: item?.name || "",
    lang: item?.lang || "",
    default: Boolean(item?.voice?.default),
    localService: Boolean(item?.voice?.localService),
    gender: item?.gender || "unknown",
    genderSource: "inferred",
  }));
};

window.resolveTutorBrowserVoice = function resolveTutorBrowserVoice(identityKey = state.chatVoiceGender) {
  const resolvedIdentity = typeof window.normalizeTutorIdentityKey === "function"
    ? window.normalizeTutorIdentityKey(identityKey)
    : String(identityKey || "").trim().toLowerCase() === "man"
      ? "man"
      : "woman";
  const catalog = Array.isArray(state.chatVoiceCatalog) && state.chatVoiceCatalog.length
    ? state.chatVoiceCatalog
    : buildChatVoiceCatalog();
  const exactCandidates = TUTOR_BROWSER_VOICE_EXACT_MAP[resolvedIdentity] || [];
  for (const candidate of exactCandidates) {
    const match = catalog.find((item) => (
      String(item?.name || "") === candidate.name
      && String(item?.voice?.voiceURI || item?.name || "") === candidate.voiceURI
      && String(item?.lang || "").toLowerCase() === String(candidate.lang || "").toLowerCase()
    ));
    if (match) {
      return {
        identity: resolvedIdentity,
        voiceEntry: match,
        method: "exact-machine-match",
        warning: "",
      };
    }
  }
  const expectedGender = resolvedIdentity === "man" ? "male" : "female";
  return {
    identity: resolvedIdentity,
    voiceEntry: null,
    method: "unresolved",
    warning: `Keine feste deutsche ${expectedGender === "male" ? "Männerstimme" : "Frauenstimme"} verfügbar.`,
  };
};

window.describeTutorBrowserVoiceResolution = function describeTutorBrowserVoiceResolution(resolution) {
  if (resolution?.voiceEntry) return window.describeChatTtsVoice(resolution.voiceEntry);
  return resolution?.warning || "Keine passende Systemstimme verfügbar.";
};

window.getTutorVoiceDebugSnapshot = function getTutorVoiceDebugSnapshot() {
  const selectedIdentity = typeof window.getTutorVoicePersonaKey === "function"
    ? window.getTutorVoicePersonaKey()
    : (state.chatVoiceGender === "male" ? "man" : "woman");
  return {
    inventory: window.getTutorBrowserVoiceInventory(),
    germanInventory: window.getTutorBrowserVoiceInventory().filter((item) => String(item?.lang || "").toLowerCase().startsWith("de")),
    womanResolution: window.resolveTutorBrowserVoice("woman"),
    manResolution: window.resolveTutorBrowserVoice("man"),
    selectedIdentity,
    selectedResolution: window.resolveTutorBrowserVoice(selectedIdentity),
  };
};

window.dumpTutorVoiceDebugSnapshot = function dumpTutorVoiceDebugSnapshot() {
  const snapshot = window.getTutorVoiceDebugSnapshot();
  if (typeof console !== "undefined" && typeof console.table === "function") {
    console.table(snapshot.inventory);
    console.info("[TutorVoiceDebug] resolutions", {
      woman: snapshot.womanResolution,
      man: snapshot.manResolution,
      selectedIdentity: snapshot.selectedIdentity,
    });
  }
  return snapshot;
};

window.stopChatSpeech = function stopChatSpeech() {
  if (typeof window.stopTutorAudio === "function") {
    window.stopTutorAudio({ cancelBrowser: false, silent: true });
  }
  window.stopTutorAvatarFallbackPulse?.();
  window.resetTutorAvatarActivity?.();
  if (!chatBrowserSpeechSupported()) return;
  window.speechSynthesis.cancel();
};

window.describeChatTtsVoice = function describeChatTtsVoice(voiceEntry) {
  if (!voiceEntry) return "Keine passende Systemstimme gefunden.";
  const variantLabel = voiceEntry.isRegional ? voiceEntry.regionLabel : "Hochdeutsch";
  const genderLabel = voiceEntry.gender === "female"
    ? "Frau"
    : voiceEntry.gender === "male"
      ? "Mann"
      : "Automatisch";
  return `${variantLabel} · ${genderLabel}`;
};

window.refreshChatVoiceControls = function refreshChatVoiceControls() {
  if (!els.chatVoiceSummary) return;
  const localVoiceLabel = String(state.config?.tutor_tts_voice_label || "").trim();
  const localAvailable = Boolean(state.config?.tutor_local_tts_available);
  const browserAvailable = chatBrowserSpeechSupported();
  const localSummary = localAvailable
    ? `Gerätestimme aktiv${localVoiceLabel ? `: ${localVoiceLabel}` : ""}.`
    : "";

  if (!browserAvailable) {
    if (els.chatVoiceRegion) {
      els.chatVoiceRegion.innerHTML = "<option value='de-DE'>Hochdeutsch</option>";
      els.chatVoiceRegion.disabled = true;
    }
    els.chatVoiceSummary.textContent = localAvailable
      ? `${localSummary} Zusätzliche Systemstimme nicht verfügbar.`
      : "Auf diesem Gerät ist keine Wiedergabe verfügbar.";
    if (els.chatReplayBtn) {
      const tutorAudioSupported = typeof window.tutorAudioSupported === "function"
        ? window.tutorAudioSupported()
        : localAvailable;
      els.chatReplayBtn.disabled = !tutorAudioSupported || !state.chatTtsEnabled || !state.chatLastAssistantReply;
    }
    return;
  }

  if (!Array.isArray(state.chatVoiceCatalog) || !state.chatVoiceCatalog.length) {
    if (els.chatVoiceRegion) {
      els.chatVoiceRegion.innerHTML = "<option value='de-DE'>Hochdeutsch</option>";
      els.chatVoiceRegion.disabled = true;
    }
    els.chatVoiceSummary.textContent = localAvailable
      ? `${localSummary} Systemstimme wird vorbereitet.`
      : "Systemstimme wird vorbereitet.";
    if (els.chatReplayBtn) els.chatReplayBtn.disabled = !state.chatTtsEnabled || !state.chatLastAssistantReply;
    return;
  }

  const regionalOptions = getChatRegionalVoiceOptions();
  if (!regionalOptions.length && state.chatVoiceVariant === "regional") {
    state.chatVoiceVariant = "standard";
    state.chatVoiceRegion = "de-DE";
    persistChatVoicePreferences();
  }

  if (els.chatVoiceGender && els.chatVoiceGender.value !== state.chatVoiceGender) {
    els.chatVoiceGender.value = state.chatVoiceGender;
  }
  if (els.chatVoiceVariant && els.chatVoiceVariant.value !== state.chatVoiceVariant) {
    els.chatVoiceVariant.value = state.chatVoiceVariant;
  }

  if (els.chatVoiceRegion) {
    const options = state.chatVoiceVariant === "regional" && regionalOptions.length
      ? regionalOptions
      : [{ value: "de-DE", label: "Hochdeutsch" }];
    if (!options.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = options[0].value;
      persistChatVoicePreferences();
    }
    els.chatVoiceRegion.innerHTML = options
      .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
      .join("");
    els.chatVoiceRegion.value = state.chatVoiceRegion;
  }

  const tutorBrowserResolution = typeof window.resolveTutorBrowserVoice === "function"
    ? window.resolveTutorBrowserVoice(typeof window.getTutorVoicePersonaKey === "function" ? window.getTutorVoicePersonaKey() : state.chatVoiceGender)
    : { voiceEntry: null, warning: "Keine passende Systemstimme verfügbar." };
  const tutorSummary = typeof window.describeTutorBrowserVoiceResolution === "function"
    ? window.describeTutorBrowserVoiceResolution(tutorBrowserResolution)
    : describeChatTtsVoice(tutorBrowserResolution.voiceEntry);
  const tutorBrowserSummary = tutorBrowserResolution?.voiceEntry && !regionalOptions.length
    ? `${tutorSummary} · Nur Hochdeutsch verfügbar.`
    : tutorSummary;
  els.chatVoiceSummary.textContent = localAvailable
    ? `${localSummary} Zusätzliche Systemstimme: ${tutorBrowserSummary}`
    : `Systemstimme: ${tutorBrowserSummary}`;
  if (els.chatReplayBtn) els.chatReplayBtn.disabled = !state.chatTtsEnabled || !state.chatLastAssistantReply;
  return;

  const selectedVoice = getChatTtsVoice(personaVoiceGender);
  const legacySummary = describeChatTtsVoice(selectedVoice);
  const legacyBrowserSummary = regionalOptions.length
    ? legacySummary
    : `${legacySummary} | Nur Hochdeutsch verfügbar.`;
  els.chatVoiceSummary.textContent = regionalOptions.length
    ? legacySummary
    : `${legacySummary} | Nur Hochdeutsch verfügbar.`;
  els.chatVoiceSummary.textContent = localAvailable
    ? `${localSummary} Systemstimme nutzt ${personaMeta?.title || "das ausgewählte Sprachprofil"}: ${legacyBrowserSummary}`
    : `Systemstimme nutzt ${personaMeta?.title || "das ausgewählte Sprachprofil"}: ${legacyBrowserSummary}`;
  if (els.chatReplayBtn) els.chatReplayBtn.disabled = !state.chatTtsEnabled || !state.chatLastAssistantReply;
};

window.refreshChatTtsUi = function refreshChatTtsUi() {
  if (!els.chatTtsBtn) return;
  const tutorAudioSupported = typeof window.tutorAudioSupported === "function"
    ? window.tutorAudioSupported()
    : chatSpeechSupported();
  if (!tutorAudioSupported) {
    els.chatTtsBtn.textContent = t("chat_tts_na");
    els.chatTtsBtn.disabled = true;
    refreshChatVoiceControls();
    return;
  }
  els.chatTtsBtn.textContent = state.chatTtsEnabled ? t("chat_tts_on") : t("chat_tts_off");
  refreshChatVoiceControls();
};

window.bindChatTtsVoices = function bindChatTtsVoices() {
  if (!chatBrowserSpeechSupported()) {
    state.chatVoiceCatalog = [];
    refreshChatTtsUi();
    return;
  }
  if (state.chatTtsVoicesBound) return;
  const syncVoices = () => {
    state.chatVoiceCatalog = buildChatVoiceCatalog() || [];
    refreshChatTtsUi();
    updateChatComposerState();
  };

  state.chatTtsVoicesBound = true;
  syncVoices();
  if ("onvoiceschanged" in window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => syncVoices();
  }
};

window.toggleChatTts = function toggleChatTts() {
  const tutorAudioSupported = typeof window.tutorAudioSupported === "function"
    ? window.tutorAudioSupported()
    : chatSpeechSupported();
  if (!tutorAudioSupported) {
    els.chatVoiceStatus.textContent = "Wiedergabe ist nicht verfügbar.";
    refreshChatTtsUi();
    return;
  }
  state.chatTtsEnabled = !state.chatTtsEnabled;
  persistChatVoicePreferences();
  if (!state.chatTtsEnabled) {
    stopChatSpeech();
    els.chatVoiceStatus.textContent = "Wiedergabe aus.";
  } else {
    els.chatVoiceStatus.textContent = "Wiedergabe an.";
  }
  refreshChatTtsUi();
  updateChatComposerState();
};

window.repeatLastChatReply = function repeatLastChatReply() {
  if (!state.chatLastAssistantReply) {
    els.chatVoiceStatus.textContent = "Noch keine Tutor-Antwort zum Wiederholen.";
    return;
  }
  if (typeof window.playTutorReplyAudio === "function") {
    window.playTutorReplyAudio(state.chatLastAssistantReply, { source: "replay" });
    return;
  }
  speakChatReply(state.chatLastAssistantReply);
};

window.speakChatReply = function speakChatReply(text) {
  if (!state.chatTtsEnabled || !chatBrowserSpeechSupported() || !String(text || "").trim()) return;
  state.chatLastAssistantReply = String(text).trim();
  stopChatSpeech();
  const visibleIdentity = typeof window.getTutorVoicePersonaKey === "function"
    ? window.getTutorVoicePersonaKey()
    : (state.chatVoiceGender === "male" ? "man" : "woman");
  const outgoingPersonaKey = typeof window.getTutorVoicePersonaKey === "function"
    ? window.getTutorVoicePersonaKey()
    : visibleIdentity;
  const utterance = new SpeechSynthesisUtterance(state.chatLastAssistantReply);
  const personaVoiceGender = typeof window.getTutorPersonaVoiceGender === "function"
    ? window.getTutorPersonaVoiceGender()
    : state.chatVoiceGender;
  const browserResolution = typeof window.resolveTutorBrowserVoice === "function"
    ? window.resolveTutorBrowserVoice(visibleIdentity)
    : { voiceEntry: null, method: "unresolved", warning: "Keine passende Systemstimme verfügbar." };
  const voiceEntry = browserResolution?.voiceEntry || null;
  if (!voiceEntry?.voice) {
    const warningMessage = browserResolution?.warning || "Keine passende Systemstimme verfügbar.";
    window.logTutorIdentityVoiceDebug?.("browser-fallback-unavailable", {
      visibleIdentity,
      outgoingTtsPersonaKey: outgoingPersonaKey,
      browserFallbackGender: personaVoiceGender,
      browserResolutionMethod: browserResolution?.method || "unresolved",
      browserResolutionWarning: warningMessage,
      finalPlaybackPath: "none",
    });
    els.chatVoiceStatus.textContent = warningMessage;
    refreshChatTtsUi();
    return;
  }
  utterance.lang = voiceEntry?.lang || voiceEntry?.regionCode || "de-DE";
  if (voiceEntry?.voice) utterance.voice = voiceEntry.voice;
  utterance.rate = voiceEntry?.isRegional ? 0.94 : 0.96;
  utterance.pitch = personaVoiceGender === "male" ? 0.95 : personaVoiceGender === "female" ? 1.02 : 1;
  utterance.onstart = () => {
    window.logTutorIdentityVoiceDebug?.("browser-fallback-start", {
      visibleIdentity,
      outgoingTtsPersonaKey: outgoingPersonaKey,
      browserFallbackGender: personaVoiceGender,
      browserResolutionMethod: browserResolution?.method || "unresolved",
      resolvedBrowserVoiceName: voiceEntry?.name || null,
      resolvedBrowserVoiceURI: voiceEntry?.voice?.voiceURI || voiceEntry?.name || null,
      resolvedBrowserVoiceLang: voiceEntry?.lang || voiceEntry?.regionCode || "de-DE",
      resolvedBrowserVoiceGenderHeuristic: voiceEntry?.gender || "unknown",
      resolvedBrowserVoiceDefault: Boolean(voiceEntry?.voice?.default),
      resolvedBrowserVoiceLocalService: Boolean(voiceEntry?.voice?.localService),
      resolvedBrowserVoiceObject: {
        voiceURI: voiceEntry?.voice?.voiceURI || voiceEntry?.name || null,
        name: voiceEntry?.name || null,
        lang: voiceEntry?.lang || voiceEntry?.regionCode || "de-DE",
        default: Boolean(voiceEntry?.voice?.default),
        localService: Boolean(voiceEntry?.voice?.localService),
      },
      finalPlaybackPath: "browser",
    });
    state.tutorAudio.mode = "fallback";
    state.tutorAudio.turnId = null;
    state.tutorAudio.queueDepth = 0;
    state.tutorAudio.localPlaybackStarted = false;
    state.tutorAudio.fallbackInUse = true;
    window.startTutorAvatarFallbackPulse?.();
    window.syncTutorAvatarPresentation?.();
    els.chatVoiceStatus.textContent = `Wiedergabe: ${describeChatTtsVoice(voiceEntry)}.`;
  };
  utterance.onend = () => {
    state.tutorAudio.mode = "idle";
    state.tutorAudio.turnId = null;
    state.tutorAudio.queueDepth = 0;
    state.tutorAudio.localPlaybackStarted = false;
    state.tutorAudio.fallbackInUse = false;
    window.stopTutorAvatarFallbackPulse?.();
    window.syncTutorAvatarPresentation?.();
    els.chatVoiceStatus.textContent = "Wiedergabe bereit.";
    refreshChatTtsUi();
  };
  utterance.onerror = () => {
    state.tutorAudio.mode = "idle";
    state.tutorAudio.turnId = null;
    state.tutorAudio.queueDepth = 0;
    state.tutorAudio.localPlaybackStarted = false;
    state.tutorAudio.fallbackInUse = false;
    window.stopTutorAvatarFallbackPulse?.();
    window.syncTutorAvatarPresentation?.();
    els.chatVoiceStatus.textContent = "Wiedergabe nicht möglich.";
    refreshChatTtsUi();
  };
  window.speechSynthesis.speak(utterance);
  refreshChatTtsUi();
};

window.loadSelectedConversation = async function loadSelectedConversation() {
  if (state.chatRequestInFlight || state.chatTranscribeInFlight) return;
  if (!els.chatHistorySelect.value) return;
  stopBrowserDictation("chat");
  stopChatSpeech();
  window.interruptTutorStream?.({ silent: true, suppressStatus: true });
  const data = await apiFetch(`/api/chat/transcript/${els.chatHistorySelect.value}`);
  applyChatTranscriptData(data, {
    statusMessage: "Verlauf geladen.",
    statusTone: "success",
    resetSupportRail: true,
  });
};

window.resetChat = function resetChat() {
  window.interruptTutorStream?.({ silent: true, suppressStatus: true });
  stopBrowserDictation("chat");
  stopChatSpeech();
  state.conversationId = null;
  state.chatTranscriptEntries = [];
  state.chatEditingEntryId = null;
  state.chatVersionsEntryId = null;
  state.chatVersionsCache = {};
  state.chatRequestInFlight = false;
  state.chatRequestController = null;
  state.tutorStreamController = null;
  state.chatTranscribeInFlight = false;
  state.chatPendingBubble = null;
  state.chatLastAssistantReply = "";
  state.chatHasCompletedAssistantTurn = false;
  resetTutorSessionState();
  els.chatMessages.innerHTML = "";
  els.chatInput.value = "";
  els.chatCorrection.textContent = "Noch keine Korrektur.";
  els.chatFinalFeedback.textContent = "Beenden Sie die Sitzung, um Gesamtfeedback zu sehen.";
  els.chatVoiceStatus.textContent = "Wiedergabe bereit.";
  setChatStatus("Tutor bereit.");
  renderTips(els.chatTips, []);
  refreshChatTtsUi();
  updateChatComposerState();
  window.resetTutorAvatarActivity?.();
};

window.hasChatResetRisk = function hasChatResetRisk() {
  return Boolean(
    state.conversationId
    || els.chatInput.value.trim()
    || els.chatMessages.childElementCount
  );
};

window.requestChatReset = async function requestChatReset() {
  if (state.chatRequestInFlight || state.chatTranscribeInFlight) return;
  if (!hasChatResetRisk()) {
    resetChat();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Chatsitzung verwerfen?",
    message: "Die aktuelle Chatsitzung und ungesendete Eingaben werden entfernt. Wirklich neu starten?",
    confirmLabel: "Neue Sitzung",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  resetChat();
};

window.hasQuestionDraft = function hasQuestionDraft(container) {
  if (!container) return false;
  if (Object.values(collectAnswers(container)).some((value) => String(value || "").trim())) return true;
  return container.childElementCount > 0;
};

window.sendChatBlockingLegacy = async function sendChatBlockingLegacy(messageOverride = null) {
  const message = typeof messageOverride === "string" ? messageOverride.trim() : els.chatInput.value.trim();
  if (!message || state.chatRequestInFlight || state.chatTranscribeInFlight) return;
  const controller = new AbortController();
  const requestStartedAt = typeof window.performance?.now === "function" ? window.performance.now() : Date.now();
  const turnId = `legacy-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  stopBrowserDictation("chat");
  stopChatSpeech();
  appendBubble(els.chatMessages, "user", message);
  els.chatInput.value = "";
  state.chatRequestInFlight = true;
  state.chatRequestController = controller;
  state.tutorStreamController = null;
  state.chatPendingBubble = appendBubble(els.chatMessages, "assistant", "Der Tutor denkt nach ...", "pending");
  setTutorSessionState("thinking", {
    transport: "blocking",
    activeTurnId: turnId,
    hasReceivedContent: false,
    lastError: "",
  });
  setChatStatus("Tutor antwortet ...", "busy");
  els.chatCorrection.textContent = "Noch keine Korrektur.";
  renderTips(els.chatTips, []);
  updateChatComposerState();
  try {
    const data = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: state.conversationId,
        level: els.globalLevel.value,
        mode: typeof window.getMainTutorMode === "function" ? window.getMainTutorMode() : "fluidez",
        persona_key: typeof window.getTutorConversationPersonaKey === "function"
          ? window.getTutorConversationPersonaKey()
          : "studio",
      }),
      signal: controller.signal,
      timeoutMs: state.config?.chat_timeout_ms || 45000,
    });
    state.conversationId = data.conversation_id;
    if (state.chatPendingBubble) {
      state.chatPendingBubble.className = "bubble assistant";
      state.chatPendingBubble.innerHTML = escapeHtml(data.reply).replace(/\n/g, "<br />");
    } else {
      appendBubble(els.chatMessages, "assistant", data.reply);
    }
    state.chatLastAssistantReply = String(data.reply || "").trim();
    state.chatHasCompletedAssistantTurn = true;
    els.chatCorrection.textContent = data.correction || "Keine unmittelbare Korrektur.";
    renderTips(els.chatTips, data.tips || []);
    const latencyMs = Math.round((typeof window.performance?.now === "function" ? window.performance.now() : Date.now()) - requestStartedAt);
    setChatStatus(`Antwort erhalten (${(latencyMs / 1000).toFixed(latencyMs >= 10000 ? 0 : 1)} s).`, "success");
    setTutorSessionState("idle", {
      transport: "none",
      activeTurnId: null,
      hasReceivedContent: false,
      lastError: "",
    });
    if (typeof window.playTutorReplyAudio === "function") {
      window.playTutorReplyAudio(data.reply, { turnId, source: "blocking" });
    } else {
      speakChatReply(data.reply);
    }
    refreshChatTtsUi();
    refreshChatHistory().catch((historyError) => {
      setStatus(`Chatverlauf konnte nicht aktualisiert werden: ${historyError.message}`);
    });
    window.reloadActiveChatTranscript?.({
      silent: true,
      conversationId: data.conversation_id,
      applyIfConversationChanged: false,
    }).catch((transcriptError) => {
      setStatus(`Aktiver Verlauf konnte nicht aktualisiert werden: ${transcriptError.message}`);
    });
  } catch (error) {
    const errorMessage = error.message || "Chat-Anfrage fehlgeschlagen.";
    if (state.chatPendingBubble) {
      state.chatPendingBubble.className = "bubble system";
      state.chatPendingBubble.innerHTML = escapeHtml(errorMessage);
    } else {
      appendBubble(els.chatMessages, "system", errorMessage);
    }
    els.chatInput.value = message;
    setTutorSessionState("error", {
      transport: "none",
      activeTurnId: null,
      hasReceivedContent: false,
      lastError: errorMessage,
    });
    setChatStatus(errorMessage, "error");
  } finally {
    state.chatRequestInFlight = false;
    state.chatRequestController = null;
    state.tutorStreamController = null;
    state.chatPendingBubble = null;
    refreshChatTtsUi();
    updateChatComposerState();
  }
};

window.sendChat = async function sendChat() {
  const message = els.chatInput.value.trim();
  if (!message || state.chatRequestInFlight || state.chatTranscribeInFlight) return;
  const useStreaming = Boolean(
    state.config?.tutor_streaming_enabled
    && typeof window.sendTutorStreamMessage === "function"
    && typeof window.tutorStreamingSupported === "function"
    && window.tutorStreamingSupported()
  );
  if (!useStreaming) {
    await window.sendChatBlockingLegacy(message);
    return;
  }
  try {
    await window.sendTutorStreamMessage(message);
  } catch (error) {
    if (error?.canFallback) {
      await window.sendChatBlockingLegacy(message);
      return;
    }
    const errorMessage = error?.message || "Tutor-Streaming fehlgeschlagen.";
    setTutorSessionState("error", {
      transport: "none",
      activeTurnId: null,
      hasReceivedContent: false,
      lastError: errorMessage,
    });
    setChatStatus(errorMessage, "error");
    state.chatRequestInFlight = false;
    state.chatRequestController = null;
    state.tutorStreamController = null;
    state.chatPendingBubble = null;
    updateChatComposerState();
  }
};

window.finishChat = async function finishChat() {
  if (!state.conversationId || !state.chatHasCompletedAssistantTurn || state.chatRequestInFlight || state.chatTranscribeInFlight) return;
  state.chatRequestInFlight = true;
  setChatStatus("Abschlussfeedback wird erstellt ...", "busy");
  updateChatComposerState();
  try {
    const data = await apiFetch("/api/chat/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: state.conversationId }),
      timeoutMs: state.config?.chat_timeout_ms || 45000,
    });
    els.chatFinalFeedback.innerHTML = escapeHtml(data.feedback).replace(/\n/g, "<br />");
    setChatStatus("Abschlussfeedback bereit.", "success");
  } catch (error) {
    els.chatFinalFeedback.textContent = error.message;
    setChatStatus(error.message, "error");
  } finally {
    state.chatRequestInFlight = false;
    updateChatComposerState();
  }
};

window.stopBrowserDictation = function stopBrowserDictation(target = null) {
  if (!state.speechRecognition) return;
  if (target && state.speechRecognitionTarget !== target) return;
  try {
    state.speechRecognition.stop();
  } catch {
    state.speechRecognition = null;
    state.speechRecognitionTarget = null;
    state.speechRecognitionActive = false;
    if (target === "chat" && state.tutorSession?.transport === "browser-dictation") {
      resetTutorSessionState();
    }
    refreshVoiceInputButtons();
    updateChatComposerState();
  }
};

window.microphoneBlockedHint = function microphoneBlockedHint() {
  const isRemoteHttp = (
    window.location.protocol !== "https:"
    && window.location.hostname !== "localhost"
    && window.location.hostname !== "127.0.0.1"
  );
  if (isRemoteHttp) {
    return "Im mobilen Browser kann das Mikrofon über eine lokale http-Adresse blockiert sein.";
  }
  return "Mikrofonzugriff wurde nicht erteilt.";
};

window.focusVoiceInputFallback = function focusVoiceInputFallback(target) {
  const inputEl = getVoiceInputField(target);
  const statusEl = getVoiceInputStatusEl(target);
  if (!inputEl) return;

  const placeCaretAtEnd = () => {
    const value = String(inputEl.value || "");
    if (typeof inputEl.setSelectionRange === "function") {
      inputEl.setSelectionRange(value.length, value.length);
    }
  };

  inputEl.removeAttribute("readonly");
  inputEl.focus();
  placeCaretAtEnd();
  inputEl.scrollIntoView({ block: "center", behavior: "smooth" });

  if (navigator.virtualKeyboard?.show) {
    try {
      navigator.virtualKeyboard.show();
    } catch {
      // Best effort only.
    }
  }

  statusEl.textContent = "Web-Mikrofon blockiert. Nutzen Sie bei Bedarf die Spracheingabe der Tastatur.";
  if (target === "chat") {
    setChatStatus("Web-Mikrofon blockiert. Nutzen Sie die Spracheingabe der Tastatur.", "error");
  }
};

window.startBrowserDictation = function startBrowserDictation(target) {
  const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!RecognitionCtor) return false;

  if (state.speechRecognitionActive && state.speechRecognitionTarget === target) {
    stopBrowserDictation(target);
    return true;
  }
  if (state.speechRecognitionActive && state.speechRecognitionTarget !== target) {
    stopBrowserDictation();
    return true;
  }

  const inputEl = getVoiceInputField(target);
  const statusEl = getVoiceInputStatusEl(target);
  if (!inputEl || !statusEl) return false;

  const seedText = String(inputEl.value || "").trim();
  let committedText = "";
  let lastErrorMessage = "";
  const recognition = new RecognitionCtor();
  recognition.lang = "de-DE";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  state.speechRecognition = recognition;
  state.speechRecognitionTarget = target;
  state.speechRecognitionActive = false;

  const applyTranscript = (liveText = "") => {
    inputEl.value = [seedText, committedText, liveText].filter(Boolean).join(" ").trim();
  };

  const cleanup = () => {
    state.speechRecognition = null;
    state.speechRecognitionTarget = null;
    state.speechRecognitionActive = false;
    refreshVoiceInputButtons();
    updateChatComposerState();
  };

  recognition.onstart = () => {
    state.speechRecognitionActive = true;
    if (target === "chat") {
      setTutorSessionState("listening", {
        transport: "browser-dictation",
        activeTurnId: null,
        hasReceivedContent: false,
        lastError: "",
      });
    }
    refreshVoiceInputButtons();
    if (target === "chat") {
      setChatStatus("Diktat läuft ...", "busy");
      updateChatComposerState();
    }
    statusEl.textContent = "Diktat läuft ... sprich jetzt.";
  };

  recognition.onresult = (event) => {
    let interimText = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = String(event.results[index][0]?.transcript || "").trim();
      if (!transcript) continue;
      if (event.results[index].isFinal) {
        committedText = [committedText, transcript].filter(Boolean).join(" ").trim();
      } else {
        interimText = [interimText, transcript].filter(Boolean).join(" ").trim();
      }
    }
    applyTranscript(interimText);
    statusEl.textContent = interimText ? "Ich höre zu ..." : "Diktat übernommen.";
  };

  recognition.onerror = (event) => {
    const errorCode = String(event.error || "unknown");
    const errorMap = {
      "audio-capture": "Kein Mikrofon gefunden.",
      "network": "Die Spracherkennung ist gerade nicht erreichbar.",
      "not-allowed": "Der Browser hat das Diktat blockiert.",
      "service-not-allowed": "Der Browser erlaubt dieses Diktat hier nicht.",
      "no-speech": "Keine Sprache erkannt.",
      "aborted": "Diktat abgebrochen.",
    };
    lastErrorMessage = errorMap[errorCode] || "Das Diktat konnte nicht gestartet werden.";
    statusEl.textContent = errorCode === "not-allowed" ? microphoneBlockedHint() : lastErrorMessage;
    if (target === "chat") {
      if (state.tutorSession?.transport === "browser-dictation") {
        if (errorCode === "aborted") {
          resetTutorSessionState();
        } else {
          setTutorSessionState("error", {
            transport: "none",
            activeTurnId: null,
            hasReceivedContent: false,
            lastError: lastErrorMessage,
          });
        }
      }
      setChatStatus(statusEl.textContent, "error");
    }
    if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
      focusVoiceInputFallback(target);
    }
  };

  recognition.onend = () => {
    const finalMessage = lastErrorMessage || (committedText ? "Diktat übernommen." : "Keine Sprache erkannt.");
    if (!lastErrorMessage) statusEl.textContent = finalMessage;
    if (target === "chat" && !lastErrorMessage) {
      if (state.tutorSession?.transport === "browser-dictation") resetTutorSessionState();
      setChatStatus(committedText ? "Diktat bereit." : "Keine Sprache erkannt.", committedText ? "success" : "error");
    }
    cleanup();
  };

  try {
    recognition.start();
    return true;
  } catch {
    cleanup();
    return false;
  }
};

window.toggleVoiceInput = async function toggleVoiceInput(target) {
  if (state.speechRecognitionActive && state.speechRecognitionTarget === target) {
    stopBrowserDictation(target);
    return;
  }
  if (state.recorder && state.recordTarget === target) {
    state.recorder.stop();
    return;
  }
  if (target === "chat") stopChatSpeech();
  if (browserSpeechRecognitionSupported() && startBrowserDictation(target)) return;
  await toggleRecorder(target);
};

window.toggleRecorder = async function toggleRecorder(target) {
  if (state.recorder) {
    state.recorder.stop();
    return;
  }
  if (target === "chat") stopChatSpeech();
  const statusEl = getVoiceInputStatusEl(target);
  if (target === "chat" && (state.chatRequestInFlight || state.chatTranscribeInFlight)) {
    setChatStatus("Warte auf das Ende der aktuellen Anfrage.", "error");
    return;
  }
  if (!state.config?.server_transcribe) {
    if (target === "chat") setChatStatus("Automatische Transkription ist nicht verfügbar.", "error");
    statusEl.textContent = "Automatische Transkription ist nicht verfügbar.";
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    const detail = microphoneBlockedHint();
    statusEl.textContent = detail;
    if (target === "chat") setChatStatus(detail, "error");
    focusVoiceInputFallback(target);
    refreshVoiceInputButtons();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.recorderChunks = [];
    state.recordTarget = target;
    state.recorder = new MediaRecorder(stream);
    if (target === "chat") {
      setTutorSessionState("listening", {
        transport: "recorder",
        activeTurnId: null,
        hasReceivedContent: false,
        lastError: "",
      });
    }
    refreshVoiceInputButtons();
    state.recorder.ondataavailable = (event) => state.recorderChunks.push(event.data);
    state.recorder.onstop = async () => {
      const blob = new Blob(state.recorderChunks, { type: "audio/webm" });
      const stoppedTarget = state.recordTarget;
      stream.getTracks().forEach((track) => track.stop());
      state.recorder = null;
      state.recordTarget = null;
      refreshVoiceInputButtons();
      if (target === "chat") {
        state.chatTranscribeInFlight = true;
        if (state.tutorSession?.transport === "recorder") {
          setTutorSessionState("transcribing", {
            transport: "recorder",
            activeTurnId: null,
            hasReceivedContent: false,
            lastError: "",
          });
        }
        updateChatComposerState();
        setChatStatus("Audio wird transkribiert ...", "busy");
      }
      const form = new FormData();
      form.append("audio", blob, "speech.webm");
      form.append("language", "de");
      statusEl.textContent = "Audio wird transkribiert ...";
      try {
        const data = await apiFetch("/transcribe", {
          method: "POST",
          body: form,
          timeoutMs: state.config?.transcribe_timeout_ms || 50000,
        });
        if (stoppedTarget === "chat") els.chatInput.value = data.text;
        if (stoppedTarget === "speaking") els.speakingInput.value = data.text;
        if (target === "chat") {
          if (state.tutorSession?.transport === "recorder") resetTutorSessionState();
          setChatStatus("Transkription bereit.", "success");
        }
        statusEl.textContent = "Transkription übernommen.";
      } catch (error) {
        statusEl.textContent = error.message;
        if (target === "chat") {
          if (state.tutorSession?.transport === "recorder") {
            setTutorSessionState("error", {
              transport: "none",
              activeTurnId: null,
              hasReceivedContent: false,
              lastError: error.message || "Transkription fehlgeschlagen.",
            });
          }
          setChatStatus(error.message, "error");
        }
      } finally {
        if (target === "chat") {
          state.chatTranscribeInFlight = false;
          updateChatComposerState();
        }
      }
    };
    state.recorder.start();
    if (target === "chat") {
      setChatStatus("Aufnahme läuft ...", "busy");
      updateChatComposerState();
    }
    statusEl.textContent = "Aufnahme läuft ... erneut klicken zum Stoppen.";
  } catch {
    const detail = microphoneBlockedHint();
    statusEl.textContent = detail;
    if (target === "chat") setChatStatus(detail, "error");
    focusVoiceInputFallback(target);
    refreshVoiceInputButtons();
  }
};

window.loadExamHistory = async function loadExamHistory() {
  const data = await apiFetch("/api/exam/history");
  els.examHistoryList.innerHTML = (data || []).map((item) => `
    <article class="list-item">
      <p class="exam-kicker">Letzter Versuch</p>
      <strong>${escapeHtml(item.title)}</strong>
      <div class="exam-chip-row">
        <span class="exam-chip">${escapeHtml(item.level)}</span>
        <span class="exam-chip">${escapeHtml(item.module)}</span>
        <span class="exam-chip">${escapeHtml(`${item.percent}%`)}</span>
      </div>
    </article>
  `).join("") || "<p class='empty'>Noch kein Prüfungsverlauf.</p>";
};

window.formatMockGenerationDuration = function formatMockGenerationDuration(milliseconds = 0) {
  const value = Number(milliseconds) || 0;
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)} s`;
  return `${value} ms`;
};

window.renderMockExamHealth = function renderMockExamHealth() {
  if (!els.examMockHealth) return;
  const health = state.mockExamHealth;
  if (!health?.recent_runs?.length) {
    els.examMockHealth.innerHTML = "<p class='empty'>Noch keine Mock-Telemetrie vorhanden.</p>";
    return;
  }
  const aggregates = Array.isArray(health.aggregates) ? health.aggregates : [];
  const totalRuns = Math.max(1, Number(health.window_runs) || 0);
  const fallbackRuns = aggregates.reduce((sum, item) => sum + Math.round((Number(item.fallback_ratio) || 0) * (Number(item.total_runs) || 0)), 0);
  const elapsedTotal = aggregates.reduce((sum, item) => sum + ((Number(item.average_elapsed_ms) || 0) * (Number(item.total_runs) || 0)), 0);
  const modeTotals = aggregates.reduce((acc, item) => {
    Object.entries(item.generation_modes || {}).forEach(([mode, count]) => {
      acc[mode] = (acc[mode] || 0) + Number(count || 0);
    });
    return acc;
  }, {});
  const modeSummary = Object.entries(modeTotals)
    .sort((left, right) => right[1] - left[1])
    .map(([mode, count]) => `${mode}: ${count}`)
    .join(" ? ");
  const aggregateCards = aggregates.slice(0, 4).map((item) => `
    <article class="exam-resource-card exam-mock-health-card">
      <span class="exam-resource-type">${escapeHtml(item.level)} ? ${escapeHtml(item.module)}</span>
      <strong>${escapeHtml(String(item.total_runs))} Läufe</strong>
      <span class="exam-resource-meta">Fallback ${escapeHtml(String(Math.round((Number(item.fallback_ratio) || 0) * 100)))}% | ${escapeHtml(formatMockGenerationDuration(item.average_elapsed_ms))}</span>
      <span class="exam-resource-meta">${escapeHtml(Object.entries(item.generation_modes || {}).map(([mode, count]) => `${mode}: ${count}`).join(" | ") || "Keine Modi protokolliert")}</span>
    </article>
  `).join("");
  const recentRuns = health.recent_runs.map((run) => `
    <li>
      <strong>${escapeHtml(run.level)} | ${escapeHtml(run.module)}</strong>: ${escapeHtml(run.generation_mode)} | ${escapeHtml(formatMockGenerationDuration(run.elapsed_ms))}
      ${run.fallback_used ? " | validierter Fallback" : ""}
    </li>
  `).join("");
  els.examMockHealth.innerHTML = `
    <article class="list-item">
      <strong>Gesundheit des Mock-Generators</strong>
      <p>${escapeHtml(modeSummary || "Noch keine Modusdaten.")}</p>
      <p class="muted">Fenster: ${escapeHtml(String(totalRuns))} Läufe | Fallback gesamt ${escapeHtml(String(Math.round((fallbackRuns / totalRuns) * 100)))}% | ${escapeHtml(formatMockGenerationDuration(totalRuns ? Math.round(elapsedTotal / totalRuns) : 0))}</p>
    </article>
    ${aggregateCards ? `<div class="exam-resource-grid exam-mock-health-grid">${aggregateCards}</div>` : ""}
    <article class="list-item">
      <strong>Letzte Mock-Läufe</strong>
      <ul class="simple-list">${recentRuns}</ul>
    </article>
  `;
};

window.loadMockExamHealth = async function loadMockExamHealth() {
  try {
    state.mockExamHealth = await apiFetch("/api/exam/mock-health");
    renderMockExamHealth();
  } catch (error) {
    if (els.examMockHealth) {
      els.examMockHealth.innerHTML = `<article class="list-item"><strong>Mock-Generator</strong><p>${escapeHtml(error.message || "Mock-Telemetrie konnte nicht geladen werden.")}</p></article>`;
    }
  }
};

window.startPlacement = async function startPlacement() {
  state.placement = await apiFetch("/api/placement/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level_hint: els.globalLevel.value, goal_exam: state.settings?.default_goal_exam || "goethe_b2" }),
  });
  renderQuestionList(els.placementQuestions, state.placement.items, "placement");
  els.placementResults.textContent = "Einstufungstest aktiv.";
};

window.hasPlacementRestartRisk = function hasPlacementRestartRisk() {
  return Boolean(state.placement || hasQuestionDraft(els.placementQuestions));
};

window.requestPlacementStart = async function requestPlacementStart() {
  if (!hasPlacementRestartRisk()) {
    await startPlacement();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Einstufung neu starten?",
    message: "Der aktuelle Einstufungstest wird ersetzt. Wirklich einen neuen Test starten?",
    confirmLabel: "Test starten",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  await startPlacement();
};

window.submitPlacement = async function submitPlacement() {
  if (!state.placement) return;
  const result = await apiFetch("/api/placement/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.placement.session_id, answers: collectAnswers(els.placementQuestions) }),
  });
  els.placementResults.innerHTML = `<strong>${escapeHtml(result.overall_level)}</strong> · ${escapeHtml(result.confidence)}<br />Empfohlene Prüfung: ${escapeHtml(result.recommended_exam)}<ul class="simple-list">${(result.skill_estimates || []).map((item) => `<li><strong>${escapeHtml(item.skill)}</strong>: ${escapeHtml(item.level)} · ${escapeHtml(item.percent)}%</li>`).join("")}</ul>`;
  refreshProgress();
  loadPlacementHistory();
};

window.loadPlacementHistory = async function loadPlacementHistory() {
  const history = await apiFetch("/api/placement/history");
  els.placementHistoryList.innerHTML = (history || []).map((item) => `<article class="list-item"><strong>${escapeHtml(item.overall_level)}</strong><p>${escapeHtml(item.recommended_exam)} · ${escapeHtml(item.confidence)}</p></article>`).join("") || "<p class='empty'>Noch keine Einstufung vorhanden.</p>";
};

window.generateRoadmap = async function generateRoadmap() {
  state.roadmap = await apiFetch("/api/roadmap/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_level: els.globalLevel.value,
      target_level: els.roadmapTargetLevel.value,
      target_exam: els.roadmapTargetExam.value,
    }),
  });
  renderRoadmap(state.roadmap, els.roadmapOutput);
};

window.activateRoadmap = async function activateRoadmap() {
  if (!state.roadmap) return;
  const active = await apiFetch("/api/roadmap/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ roadmap_id: state.roadmap.roadmap_id }),
  });
  renderRoadmap(active, els.roadmapCurrent);
  refreshProgress();
};

window.loadGrammarCatalog = async function loadGrammarCatalog() {
  state.grammarCatalog = await apiFetch("/api/grammar/catalog");
  const groups = {};
  state.grammarCatalog.forEach((item) => {
    const key = `${item.level} · ${item.category}`;
    groups[key] = groups[key] || [];
    groups[key].push(item);
  });
  els.grammarTopicSelect.innerHTML = Object.entries(groups).map(([group, items]) => `<optgroup label="${escapeHtml(group)}">${items.map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.label)}</option>`).join("")}</optgroup>`).join("");
  if (state.grammarCatalog[0]) loadGrammarTheory(state.grammarCatalog[0].key);
};

window.loadGrammarTheory = async function loadGrammarTheory(topicKey) {
  const theory = await apiFetch(`/api/grammar/theory/${topicKey}`);
  els.grammarTopicMeta.innerHTML = `<strong>${escapeHtml(theory.label)}</strong><br />${escapeHtml(theory.level)} · ${escapeHtml(theory.category)}<br />${escapeHtml(theory.summary)}`;
  renderTheory(theory);
};

window.generateGrammar = async function generateGrammar() {
  const pendingRecommendation = getPendingRecommendationAttribution();
  state.grammar = await apiFetch("/api/grammar/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level: els.globalLevel.value,
      focus: els.grammarTopicSelect.value,
      exercise_type: els.grammarType.value,
      recommendation_event_id: pendingRecommendation?.recommendationEventId || null,
    }),
  });
  if (pendingRecommendation?.recommendationEventId) clearPendingRecommendationAttribution();
  renderQuestionList(els.grammarQuestions, state.grammar.items, "grammar");
  els.grammarResults.textContent = "Nach der Korrektur sehen Sie Fehler, Mini-Drills und den nächsten Schritt.";
  loadGrammarTheory(state.grammar.topic_key);
};

window.hasGrammarRestartRisk = function hasGrammarRestartRisk() {
  return Boolean(state.grammar || hasQuestionDraft(els.grammarQuestions));
};

window.requestGrammarGenerate = async function requestGrammarGenerate() {
  if (!hasGrammarRestartRisk()) {
    await generateGrammar();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Grammatikübung ersetzen?",
    message: "Die aktuelle Grammatikübung und Ihre bisherigen Antworten werden verworfen. Wirklich neu erzeugen?",
    confirmLabel: "Übung erzeugen",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  await generateGrammar();
};

// Exact event-level attribution only starts after the learner explicitly uses
// the currently displayed progress recommendation.
window.getPendingRecommendationAttribution = function getPendingRecommendationAttribution() {
  return state.pendingRecommendationAttribution?.recommendationEventId
    ? state.pendingRecommendationAttribution
    : null;
};

window.clearPendingRecommendationAttribution = function clearPendingRecommendationAttribution() {
  state.pendingRecommendationAttribution = null;
};

window.activateRecommendationLaunch = function activateRecommendationLaunch({
  recommendationEventId = "",
  recommendationStrategy = "",
  recommendedScope = "full",
  priorityModule = "",
  source = "progress_overview",
} = {}) {
  const normalizedRecommendationEventId = String(recommendationEventId || "").trim();
  if (!normalizedRecommendationEventId) return;
  const normalizedScope = recommendedScope === "module" ? "module" : "full";
  const normalizedPriorityModule = String(priorityModule || "").trim();
  state.pendingRecommendationAttribution = {
    recommendationEventId: normalizedRecommendationEventId,
    recommendationStrategy: String(recommendationStrategy || "").trim(),
    recommendedScope: normalizedScope,
    priorityModule: normalizedPriorityModule,
    source,
  };
  if (els.examScope) els.examScope.value = normalizedScope;
  if (
    normalizedScope === "module"
    && normalizedPriorityModule
    && Array.from(els.examModule?.options || []).some((option) => option.value === normalizedPriorityModule)
  ) {
    els.examModule.value = normalizedPriorityModule;
    state.lastExamModuleUsed = normalizedPriorityModule;
  }
  syncExamScopeUi();
  switchTab("exams");
  pushAppToast("Empfehlung markiert. Der nächste Lernfluss ist vorbereitet.", "success");
};

window.useDisplayedRecommendation = function useDisplayedRecommendation(button) {
  const recommendationEventId = String(button?.dataset.recommendationEventId || "").trim();
  if (!recommendationEventId) return;
  activateRecommendationLaunch({
    recommendationEventId,
    recommendationStrategy: String(button.dataset.recommendationStrategy || "").trim(),
    recommendedScope: button.dataset.scope === "module" ? "module" : "full",
    priorityModule: String(button.dataset.priorityModule || "").trim(),
  });
};

window.submitGrammar = async function submitGrammar() {
  if (!state.grammar) return;
  const payload = await apiFetch("/api/grammar/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      exercise_id: state.grammar.exercise_id,
      answers: collectAnswers(els.grammarQuestions),
      explanation_language: state.settings?.explanation_language || "es",
    }),
  });
  renderEvaluation(els.grammarResults, payload);
  refreshProgress();
};

window.generateWritingPrompt = async function generateWritingPrompt() {
  const pendingRecommendation = getPendingRecommendationAttribution();
  state.writingPrompt = await apiFetch("/api/writing/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level: els.globalLevel.value,
      target_exam: els.writingExam.value,
      text_type: els.writingType.value,
      topic: els.writingTopic.value.trim() || null,
      recommendation_event_id: pendingRecommendation?.recommendationEventId || null,
    }),
  });
  if (pendingRecommendation?.recommendationEventId) clearPendingRecommendationAttribution();
  els.writingPromptBox.innerHTML = `<strong>${escapeHtml(state.writingPrompt.title)}</strong><p>${escapeHtml(state.writingPrompt.instructions)}</p><ul class="simple-list">${(state.writingPrompt.bullet_points || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  els.writingInput.value = "";
  els.writingResults.textContent = "Die Rubrik erscheint hier.";
};

window.hasWritingRestartRisk = function hasWritingRestartRisk() {
  return Boolean(state.writingPrompt || els.writingInput.value.trim());
};

window.requestWritingPrompt = async function requestWritingPrompt() {
  if (!hasWritingRestartRisk()) {
    await generateWritingPrompt();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Schreibaufgabe ersetzen?",
    message: "Die aktuelle Schreibaufgabe und Ihr Entwurf werden verworfen. Wirklich eine neue Aufgabe erzeugen?",
    confirmLabel: "Aufgabe erzeugen",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  await generateWritingPrompt();
};

window.gradeWriting = async function gradeWriting() {
  if (!state.writingPrompt) return;
  const payload = await apiFetch("/api/writing/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt_id: state.writingPrompt.prompt_id,
      text: els.writingInput.value,
      explanation_language: state.settings?.explanation_language || "es",
    }),
  });
  els.writingResults.innerHTML = `<p class="muted">Heuristische Textbewertung · keine validierte CEFR- oder Prüfungsbewertung.</p><p><strong>${escapeHtml(payload.total_score)} / ${escapeHtml(payload.max_score)} · ${escapeHtml(payload.percent)}%</strong></p><div class="soft-panel">${escapeHtml(payload.corrected_version).replace(/\n/g, "<br />")}</div><ul class="simple-list">${(payload.rubric || []).map((item) => `<li><strong>${escapeHtml(item.criterion)}</strong>: ${escapeHtml(item.score)} / ${escapeHtml(item.max_score)} · ${escapeHtml(item.comment)}</li>`).join("")}</ul>`;
  refreshProgress();
};

window.startSpeaking = async function startSpeaking() {
  const pendingRecommendation = getPendingRecommendationAttribution();
  const data = await apiFetch("/api/speaking/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      level: els.globalLevel.value,
      target_exam: els.speakingExam.value,
      mode: els.speakingMode.value,
      topic: els.speakingTopic.value.trim() || null,
      recommendation_event_id: pendingRecommendation?.recommendationEventId || null,
    }),
  });
  if (pendingRecommendation?.recommendationEventId) clearPendingRecommendationAttribution();
  state.speakingSessionId = data.session_id;
  els.speakingScenario.innerHTML = `<strong>${escapeHtml(data.title)}</strong><p>${escapeHtml(data.scenario)}</p><p>${escapeHtml(data.examiner_prompt)}</p>`;
  els.speakingTranscript.innerHTML = "";
  els.speakingInput.value = "";
  els.speakingFeedback.textContent = "Das Feedback zu jeder Runde erscheint hier.";
  appendBubble(els.speakingTranscript, "assistant", data.examiner_prompt);
};

window.hasSpeakingRestartRisk = function hasSpeakingRestartRisk() {
  return Boolean(
    state.speakingSessionId
    || els.speakingInput.value.trim()
    || els.speakingTranscript.childElementCount
  );
};

window.requestSpeakingStart = async function requestSpeakingStart() {
  if (!hasSpeakingRestartRisk()) {
    await startSpeaking();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Sprechsimulation ersetzen?",
    message: "Die aktuelle Simulation und Ihr Verlauf werden verworfen. Wirklich neu starten?",
    confirmLabel: "Simulation starten",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  await startSpeaking();
};

window.sendSpeakingTurn = async function sendSpeakingTurn() {
  if (!state.speakingSessionId) return;
  const message = els.speakingInput.value.trim();
  if (!message) return;
  appendBubble(els.speakingTranscript, "user", message);
  els.speakingInput.value = "";
  const payload = await apiFetch("/api/speaking/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.speakingSessionId,
      user_message: message,
      explanation_language: state.settings?.explanation_language || "es",
    }),
  });
  appendBubble(els.speakingTranscript, "assistant", payload.examiner_reply);
  els.speakingFeedback.innerHTML = `<p><strong>Runde ${escapeHtml(payload.turn_number)}</strong></p><p>${escapeHtml(payload.corrected_version)}</p><ul class="simple-list">${(payload.turn_feedback || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>${payload.is_complete ? `<ul class="simple-list">${(payload.final_recommendation || []).map((item) => `<li><strong>${escapeHtml(item.title)}</strong>: ${escapeHtml(item.action)}</li>`).join("")}</ul>` : ""}`;
  if (payload.is_complete) refreshProgress();
};

window.generateVocab = async function generateVocab() {
  const data = await apiFetch("/api/vocab/from-topic", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic: els.vocabTopic.value.trim(),
      level: els.globalLevel.value,
      count: Number(els.vocabCount.value || 12),
    }),
  });
  state.vocabItems = data.items || [];
  state.selectedVocabIds.clear();
  els.vocabTable.innerHTML = state.vocabItems.map((item) => `<article class="list-item"><label><input type="checkbox" data-vocab-id="${escapeHtml(item.id)}" /> <strong>${escapeHtml(item.lemma)}</strong>${item.gender ? ` (${escapeHtml(item.gender)})` : ""}${item.plural ? ` · ${escapeHtml(item.plural)}` : ""}</label><p>${escapeHtml(item.translation)} · ${escapeHtml(item.level)} · ${escapeHtml(item.collocation)}</p><p class="muted">${escapeHtml(item.example)}</p></article>`).join("");
  els.vocabImportResult.textContent = "Wählen Sie Wörter aus und speichern Sie sie als Kartensatz.";
};

window.hasVocabGenerationRisk = function hasVocabGenerationRisk() {
  return Boolean(
    state.vocabItems.length
    || state.selectedVocabIds.size
    || els.vocabTable.childElementCount
  );
};

window.requestVocabGenerate = async function requestVocabGenerate() {
  if (!hasVocabGenerationRisk()) {
    await generateVocab();
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Wortschatzliste ersetzen?",
    message: "Die aktuelle Wortschatzliste und Ihre Auswahl werden verworfen. Wirklich neu erzeugen?",
    confirmLabel: "Wortschatz erzeugen",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) return;
  await generateVocab();
};

window.importSelectedVocab = async function importSelectedVocab() {
  const items = state.vocabItems.filter((item) => state.selectedVocabIds.has(item.id));
  if (!items.length) return;
  const data = await apiFetch("/api/flashcards/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      deck_name: els.vocabDeckName.value.trim() || `Kartensatz ${els.globalLevel.value}`,
      deck_description: "Import aus Thema → Wortschatz",
      source: "vocab",
      items,
    }),
  });
  els.vocabImportResult.innerHTML = `Kartensatz <strong>${escapeHtml(data.deck.name)}</strong> erstellt. Karten: ${escapeHtml(data.imported_cards)}.`;
  refreshDecks();
  refreshProgress();
};

window.refreshStarterDecks = async function refreshStarterDecks() {
  state.starterDecks = await apiFetch("/api/flashcards/starter-decks");
  if (typeof window.renderReviewOverview === "function") {
    window.queueMicrotask(() => window.renderReviewOverview());
  }
  els.starterDeckList.innerHTML = state.starterDecks.map((deck) => `<article class="list-item"><strong>${escapeHtml(deck.name)}</strong><p>${escapeHtml(deck.description)}</p><p class="muted">${escapeHtml(deck.level)} · ${escapeHtml(deck.card_count)} Karten</p><p class="muted">${(deck.sample_fronts || []).map((item) => escapeHtml(item)).join(" · ")}</p><button class="ghost-btn" data-import-starter="${escapeHtml(deck.key)}">Importieren</button></article>`).join("") || "<p class='empty'>Keine Startsets vorhanden.</p>";
};

window.refreshDecks = async function refreshDecks() {
  state.decks = await apiFetch("/api/flashcards/decks");
  if (typeof window.renderReviewOverview === "function") {
    window.queueMicrotask(() => window.renderReviewOverview());
  }
  if (typeof window.renderHome === "function") {
    window.queueMicrotask(() => window.renderHome());
  }
  els.deckList.innerHTML = state.decks.map((deck) => `<article class="list-item"><strong>${escapeHtml(deck.name)}</strong><p>${escapeHtml(deck.description || "Ohne Beschreibung")}</p><p class="muted">${escapeHtml(deck.total_cards)} Karten · ${escapeHtml(deck.due_cards)} fällig</p><button class="ghost-btn" data-select-deck="${escapeHtml(deck.id)}">Zur Wiederholung wählen</button></article>`).join("") || "<p class='empty'>Noch keine Kartensätze vorhanden.</p>";
  els.reviewDeckSelect.innerHTML = `<option value="">Alle Kartensätze</option>${state.decks.map((deck) => `<option value="${escapeHtml(deck.id)}">${escapeHtml(deck.name)}</option>`).join("")}`;
  els.reviewDeckSelect.dataset.previousValue = els.reviewDeckSelect.value || "";
};

window.createDeck = async function createDeck() {
  if (!els.deckName.value.trim()) return;
  await apiFetch("/api/flashcards/decks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: els.deckName.value.trim(),
      description: els.deckDescription.value.trim(),
      source: "manual",
      tags: [],
    }),
  });
  els.deckName.value = "";
  els.deckDescription.value = "";
  refreshDecks();
};

window.importStarterDeck = async function importStarterDeck(deckKey) {
  await apiFetch(`/api/flashcards/starter-decks/${deckKey}/import`, { method: "POST" });
  refreshDecks();
  refreshProgress();
};

window.nextReviewCard = async function nextReviewCard() {
  const pendingRecommendation = getPendingRecommendationAttribution();
  const data = await apiFetch("/api/flashcards/review/next", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      deck_id: els.reviewDeckSelect.value || null,
      recommendation_event_id: pendingRecommendation?.recommendationEventId || null,
    }),
  });
  state.reviewCard = data.card;
  state.reviewCardRecommendationEventId = data.card ? (data.recommendation_event_id || null) : null;
  if (data.card && pendingRecommendation?.recommendationEventId) clearPendingRecommendationAttribution();
  state.reviewBackVisible = false;
  renderReviewCard();
  if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
  els.reviewResult.textContent = data.message || "Bereit für die nächste Wiederholungskarte.";
};

window.hasReviewAdvanceRisk = function hasReviewAdvanceRisk() {
  return Boolean(state.reviewCard);
};

window.requestNextReviewCard = async function requestNextReviewCard() {
  if (hasReviewAdvanceRisk()) {
    const confirmed = await openConfirmModal({
      title: "Aktuelle Karte überspringen?",
      message: "Die aktuelle Wiederholungskarte wird verworfen und Sie wechseln zur nächsten Karte. Wirklich fortfahren?",
      confirmLabel: "Nächste Karte",
      cancelLabel: "Abbrechen",
    });
    if (!confirmed) return;
  }
  await nextReviewCard();
};

window.applyReviewDeckSelection = function applyReviewDeckSelection(deckId) {
  els.reviewDeckSelect.value = deckId || "";
  els.reviewDeckSelect.dataset.previousValue = deckId || "";
  state.reviewCard = null;
  state.reviewCardRecommendationEventId = null;
  state.reviewBackVisible = false;
  renderReviewCard();
  if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
  els.reviewResult.textContent = deckId ? "Kartensatz gewechselt. Laden Sie die nächste Karte." : "Kartensatzfilter zurückgesetzt.";
};

window.hasReviewDeckSwitchRisk = function hasReviewDeckSwitchRisk(nextDeckId) {
  return Boolean(state.reviewCard && (els.reviewDeckSelect.dataset.previousValue || "") !== (nextDeckId || ""));
};

window.requestReviewDeckSelection = async function requestReviewDeckSelection(nextDeckId) {
  if (!hasReviewDeckSwitchRisk(nextDeckId)) {
    els.reviewDeckSelect.dataset.previousValue = nextDeckId || "";
    els.reviewDeckSelect.value = nextDeckId || "";
    return;
  }
  const confirmed = await openConfirmModal({
    title: "Kartensatz wechseln?",
    message: "Die aktuelle Karte wird verworfen und der aktive Kartensatz für die Wiederholung wird gewechselt. Wirklich fortfahren?",
    confirmLabel: "Kartensatz wechseln",
    cancelLabel: "Abbrechen",
  });
  if (!confirmed) {
    els.reviewDeckSelect.value = els.reviewDeckSelect.dataset.previousValue || "";
    return;
  }
  applyReviewDeckSelection(nextDeckId);
};

window.flipReviewCard = function flipReviewCard() {
  if (!state.reviewCard) return;
  state.reviewBackVisible = !state.reviewBackVisible;
  renderReviewCard();
};

window.gradeReview = async function gradeReview(quality) {
  if (!state.reviewCard || !state.reviewBackVisible) return;
  const data = await apiFetch("/api/flashcards/review/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      card_id: state.reviewCard.id,
      quality,
      recommendation_event_id: state.reviewCardRecommendationEventId || null,
    }),
  });
  els.reviewResult.innerHTML = `Qualität ${escapeHtml(data.quality)} · nächster Termin <strong>${escapeHtml(data.next_due_date)}</strong><br />Intervall ${escapeHtml(data.interval_days)} Tage · EF ${escapeHtml(data.easiness)}`;
  state.reviewCard = null;
  state.reviewCardRecommendationEventId = null;
  renderReviewCard();
  if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
  refreshDecks();
  refreshProgress();
};

window.refreshProgress = async function refreshProgress() {
  const goal = state.settings?.default_goal_exam || "goethe_b2";
  const [overview, mistakes] = await Promise.all([
    apiFetch(`/api/progress/overview?goal=${goal}`),
    apiFetch("/api/progress/mistakes?limit=10"),
  ]);
  state.progressOverview = overview;
  state.progressMistakes = mistakes?.mistakes || [];
  const probabilityBasisLabels = {
    empirisch: "aus Übungsprüfungen (heuristisch)",
    geschaetzt: "heuristische Schätzung",
    keine_daten: "noch keine Daten",
  };
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const goalLabels = {
    goethe_a1: "Goethe-Zertifikat A1",
    goethe_a2: "Goethe-Zertifikat A2",
    goethe_b1: "Goethe-Zertifikat B1",
    goethe_b2: "Goethe-Zertifikat B2",
    goethe_c1: "Goethe-Zertifikat C1",
    goethe_c2: "Goethe-Zertifikat C2",
  };
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "";
  const passProbabilityCards = [overview.full_exam_probability, ...(overview.module_probabilities || [])]
    .filter(Boolean)
    .map((item) => {
      const probability = item.probability_percent == null ? null : Number(item.probability_percent);
      const probabilityLabel = probability == null ? "Noch offen" : `${probability}% (heuristisch)`;
      const width = probability == null ? 0 : Math.max(6, Math.min(probability, 100));
      const metaParts = [
        probabilityBasisLabels[item.basis] || item.basis,
        item.attempts ? `${item.attempts} Versuche` : "",
        item.average_percent != null ? `Schnitt ${item.average_percent}%` : "",
      ].filter(Boolean).join(" · ");
      return `
        <article class="list-item">
          <div class="skill-row">
            <div><strong>${escapeHtml(item.label)}</strong> · ${escapeHtml(probabilityLabel)} · ${escapeHtml(item.status || "")}</div>
            <div class="bar-track"><div class="bar-fill" style="width: ${width}%"></div></div>
          </div>
          <p class="muted">${escapeHtml(metaParts)}</p>
          <p class="muted">${escapeHtml(item.note || "")}</p>
        </article>
      `;
    })
    .join("");
  els.metricDue.textContent = overview.due_flashcards ?? "-";
  els.metricStreak.textContent = overview.streak_days ? `${overview.streak_days} Tage` : "0 Tage";
  els.progressProbabilities.innerHTML = passProbabilityCards || "<p class='empty'>Noch keine Daten zum heuristischen Übungsindikator vorhanden.</p>";
  els.progressSkills.innerHTML = (overview.weak_skills || []).map((skill) => `<div class="skill-row"><div><strong>${escapeHtml(skillLabels[skill.skill] || skill.skill)}</strong> · ${escapeHtml(skill.average_percent)}% · ${escapeHtml(skill.attempts)} Versuche</div><div class="bar-track"><div class="bar-fill" style="width: ${Math.min(Number(skill.average_percent || 0), 100)}%"></div></div></div>`).join("") || "<p class='empty'>Noch zu wenig Daten vorhanden.</p>";
  els.progressPlan.innerHTML = (overview.weekly_plan || []).map((item) => `<article class="list-item"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.action)}</p></article>`).join("") || "Noch kein Plan vorhanden.";
  els.progressMistakes.innerHTML = (mistakes.mistakes || []).map((item) => `<article class="list-item"><strong>${escapeHtml(item.label)}</strong><p>${escapeHtml(item.description)}</p><p class="muted">${escapeHtml(item.example)}</p></article>`).join("") || "<p class='empty'>Noch keine häufigen Fehler erkannt.</p>";
  const recommendedScopeLabel = overview.recommended_exam_scope === "module" ? "Modultraining" : "Gesamtprüfung";
  const recommendationCta = overview.recommendation_event_id
    ? `<div class="inline-actions"><button class="primary-btn" data-use-recommendation="1" data-recommendation-event-id="${escapeHtml(overview.recommendation_event_id)}" data-recommendation-strategy="${escapeHtml(overview.recommendation_strategy || "")}" data-scope="${escapeHtml(overview.recommended_exam_scope || "full")}" data-priority-module="${escapeHtml(overview.priority_module || "")}">Diese Empfehlung starten</button></div><p class="muted">Nur Starts über diesen Button sind später exakt einem einzelnen Empfehlungsevent zuordenbar.</p>`
    : "";
  els.progressRoadmap.innerHTML = `
    <strong>${escapeHtml(overview.exam_readiness || "Nächste Prüfungslogik")}</strong>
    <p>Empfohlener Modus: ${escapeHtml(recommendedScopeLabel)}${priorityModuleLabel ? ` · Fokus ${escapeHtml(priorityModuleLabel)}` : ""}</p>
    ${overview.next_session ? `<p class="muted"><strong>${escapeHtml(overview.next_session.title)}</strong>: ${escapeHtml(overview.next_session.action)}</p>` : ""}
    ${recommendationCta}
    ${overview.active_roadmap ? `<p><strong>${escapeHtml(overview.active_roadmap.title)}</strong></p><p class="muted">${escapeHtml(goalLabels[overview.active_roadmap.target_exam] || overview.active_roadmap.target_exam)} · ${escapeHtml(overview.active_roadmap.target_level)} · ${escapeHtml(overview.active_roadmap.next_checkpoint)}</p>` : "<p class='muted'>Kein aktiver Lernplan.</p>"}
  `;
  els.progressPlacement.innerHTML = overview.latest_placement_level ? `Letzte Einstufung: <strong>${escapeHtml(overview.latest_placement_level)}</strong>` : "Noch kein Einstufungsergebnis gespeichert.";
  if (typeof window.renderHome === "function") window.renderHome();
  if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
};

window.renderHome = function renderHome() {
  if (!els.homeMissionCard) return;
  const overview = state.progressOverview || {};
  const mistakes = state.progressMistakes || [];
  const dueDecks = [...(state.decks || [])]
    .filter((deck) => Number(deck.due_cards || 0) > 0)
    .sort((left, right) => Number(right.due_cards || 0) - Number(left.due_cards || 0));
  const recentConversation = (state.chatHistoryItems || [])[0] || null;
  const recommendationScopeLabel = overview.recommended_exam_scope === "module" ? "Module focus" : "Full exam";
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "Exam";
  const probability = overview.full_exam_probability?.probability_percent;
  const activeRoadmap = overview.active_roadmap || null;
  const coachBrief = [
    {
      title: "Heuristic practice indicator",
      copy: probability == null ? "No target-level exam evidence yet." : `${probability}% heuristic indicator; not a validated exam pass probability.`,
    },
    {
      title: "Weakest focus",
      copy: (overview.weak_skills || []).length
        ? (overview.weak_skills || []).slice(0, 3).map((item) => `${skillLabels[item.skill] || item.skill} ${item.average_percent}%`).join(" · ")
        : "No weak-skill cluster detected yet.",
    },
    {
      title: "Tutor memory",
      copy: recentConversation ? `${recentConversation.turns} turns · ${recentConversation.preview}` : "No stored tutor session yet.",
    },
  ];

  els.homeMissionActions.innerHTML = `
    ${overview.recommendation_event_id ? `<button class="primary-btn" type="button" data-start-recommendation="1">Start recommended flow</button>` : `<button class="primary-btn" type="button" data-open-primary="tutor">Open tutor</button>`}
    <button class="ghost-btn" type="button" data-open-primary="review">Review due cards</button>
    <button class="ghost-btn" type="button" data-open-tab="progress">Open progress</button>
  `;

  els.homeMissionCard.innerHTML = `
    <p class="home-card-kicker">Today's mission</p>
    <strong>${escapeHtml(overview.exam_readiness || "Build momentum through one focused session.")}</strong>
    <p>${escapeHtml(overview.next_session?.action || "Open Tutor to warm up, then move into Review or the recommended workspace flow.")}</p>
    <div class="home-chip-row">
      <span class="home-chip">${escapeHtml(recommendationScopeLabel)}</span>
      <span class="home-chip">${escapeHtml(priorityModuleLabel)}</span>
      <span class="home-chip">${escapeHtml(String(overview.due_flashcards ?? 0))} due cards</span>
    </div>
  `;

  els.homeQuickStart.innerHTML = [
    {
      title: "Tutor sprint",
      copy: "Use the live tutor for natural conversation, quick replies, and light correction.",
      action: "tutor",
      kind: "primary",
      label: "Open tutor",
    },
    {
      title: "Review block",
      copy: "Clear due cards and turn repeated errors into short retrieval reps.",
      action: "review",
      kind: "secondary",
      label: "Open review",
    },
    {
      title: "Legacy workspace",
      copy: "Placement, grammar, writing, speaking sims, progress, and settings remain available here during migration.",
      tab: activeRoadmap ? "progress" : "exams",
      kind: "secondary",
      label: "Open workspace",
    },
  ].map((item) => `
    <article class="home-action-card">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.copy)}</p>
      <button class="${item.kind === "primary" ? "primary-btn" : "ghost-btn"}" type="button" ${item.action ? `data-open-primary="${escapeHtml(item.action)}"` : `data-open-tab="${escapeHtml(item.tab)}"`}>${escapeHtml(item.label)}</button>
    </article>
  `).join("");

  els.homeCoachBrief.innerHTML = coachBrief.map((item) => `
    <article class="home-stack-item">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.copy)}</p>
    </article>
  `).join("");

  els.homeContinueList.innerHTML = `
    <article class="home-stack-item">
      <strong>Recommended next move</strong>
      <p>${escapeHtml(overview.next_session?.title || "Next session")}: ${escapeHtml(overview.next_session?.action || "Use Tutor or Review to keep the streak alive.")}</p>
    </article>
    <article class="home-stack-item">
      <strong>Due review load</strong>
      <p>${dueDecks.length ? dueDecks.slice(0, 3).map((deck) => `${deck.name} (${deck.due_cards})`).join(" · ") : "No deck is due right now."}</p>
    </article>
    <article class="home-stack-item">
      <strong>Last tutor session</strong>
      <p>${recentConversation ? `${recentConversation.preview} · ${recentConversation.turns} turns` : "No recent tutor transcript yet."}</p>
    </article>
  `;

  els.homeRoadmapCard.innerHTML = activeRoadmap
    ? `
      <article class="home-stack-item">
        <strong>${escapeHtml(activeRoadmap.title)}</strong>
        <p>${escapeHtml(activeRoadmap.target_exam)} · ${escapeHtml(activeRoadmap.target_level)}</p>
        <p class="muted">${escapeHtml(activeRoadmap.next_checkpoint)}</p>
        <button class="ghost-btn" type="button" data-open-tab="progress">Open progress</button>
      </article>
    `
    : `
      <article class="home-stack-item">
        <strong>No active roadmap</strong>
        <p>Generate or activate a roadmap in the workspace to keep the plan visible here.</p>
        <button class="ghost-btn" type="button" data-open-tab="roadmap">Open roadmap</button>
      </article>
    `;

  els.homeMistakeList.innerHTML = mistakes.length
    ? mistakes.slice(0, 4).map((item) => `
        <article class="home-stack-item">
          <strong>${escapeHtml(item.label)}</strong>
          <p>${escapeHtml(item.description)}</p>
          <p class="muted">${escapeHtml(item.example)}</p>
        </article>
      `).join("")
    : `
      <article class="home-stack-item">
        <strong>No repeated error cluster yet</strong>
        <p>Complete more tracked work and your mistake-driven review loop will appear here.</p>
      </article>
    `;

  els.homeWorkspaceLinks.innerHTML = [
    ["exams", "Exam prep"],
    ["grammar", "Grammar"],
    ["writing", "Writing"],
    ["speaking", "Speaking"],
    ["progress", "Progress"],
    ["settings", "Settings"],
  ].map(([tab, label]) => `<button class="ghost-btn" type="button" data-open-tab="${escapeHtml(tab)}">${escapeHtml(label)}</button>`).join("");
};

window.renderReviewOverview = function renderReviewOverview() {
  if (!els.reviewHeroStats || !els.reviewQueueSummary) return;
  const dueDecks = [...(state.decks || [])].filter((deck) => Number(deck.due_cards || 0) > 0);
  const dueCards = dueDecks.reduce((sum, deck) => sum + Number(deck.due_cards || 0), 0);
  const selectedDeck = (state.decks || []).find((deck) => deck.id === (els.reviewDeckSelect?.value || ""));
  const activeDeckLabel = selectedDeck?.name || "All decks";

  els.reviewHeroStats.innerHTML = `
    <article class="review-stat-pill"><span>Due cards</span><strong>${escapeHtml(String(dueCards))}</strong></article>
    <article class="review-stat-pill"><span>Ready decks</span><strong>${escapeHtml(String(dueDecks.length))}</strong></article>
    <article class="review-stat-pill"><span>Filter</span><strong>${escapeHtml(activeDeckLabel)}</strong></article>
  `;

  if (state.reviewCard) {
    els.reviewQueueSummary.innerHTML = `<strong>Active card loaded</strong><p>${escapeHtml(state.reviewCard.front)}</p><p class="muted">Flip the card, grade recall, and the next interval will update immediately.</p>`;
    return;
  }

  if (selectedDeck) {
    els.reviewQueueSummary.innerHTML = `<strong>${escapeHtml(selectedDeck.name)}</strong><p>${escapeHtml(String(selectedDeck.due_cards || 0))} cards are due in this deck right now.</p>`;
    return;
  }

  els.reviewQueueSummary.innerHTML = dueCards
    ? `<strong>Review is ready</strong><p>${escapeHtml(String(dueCards))} cards are due across ${escapeHtml(String(dueDecks.length))} deck(s). Load the next card to start the session.</p>`
    : `<strong>No card is due</strong><p>Your review queue is clear. Import a starter deck or open the workspace to generate more material.</p>`;
};

window.getDefaultPracticeSet = function getDefaultPracticeSet() {
  const sets = state.officialExam?.practice_sets || [];
  if (!sets.length) return null;
  return sets.find((item) => item.key === state.selectedPracticeSetKey) || sets[0];
};

window.getDefaultPracticeResource = function getDefaultPracticeResource(practiceSet) {
  if (!practiceSet) return null;
  const resources = practiceSet.resources || [];
  if (!resources.length) return null;
  const preferredType = state.selectedPracticeResourceType || practiceSet.default_resource_type;
  return resources.find((item) => item.resource_type === preferredType) || resources[0];
};

window.syncPracticeSelection = function syncPracticeSelection() {
  const practiceSet = getDefaultPracticeSet();
  state.selectedPracticeSetKey = practiceSet?.key || null;
  state.selectedPracticeResourceType = practiceSet
    ? (state.selectedPracticeResourceType === "mock" ? "mock" : getDefaultPracticeResource(practiceSet)?.resource_type || null)
    : null;
  persistExamUiPreferences();
};

window.selectOfficialPracticeResource = function selectOfficialPracticeResource(setKey = null) {
  if (setKey) state.selectedPracticeSetKey = setKey;
  const practiceSet = getDefaultPracticeSet();
  state.selectedPracticeResourceType = practiceSet
    ? (getDefaultPracticeResource(practiceSet)?.resource_type || practiceSet.default_resource_type || null)
    : null;
  persistExamUiPreferences();
};

window.closeOfficialExamWorkspace = async function closeOfficialExamWorkspace() {
  if (state.selectedPracticeResourceType === "mock" && hasStartedMockDraft()) {
    const confirmed = await openConfirmModal({
      title: "Arbeitsansicht verlassen?",
      message: "Ihr aktueller Mock-Stand wird pausiert. Wirklich in den ruhigen Auswahlmodus wechseln?",
      confirmLabel: "Sitzung pausieren",
      cancelLabel: "Abbrechen",
    });
    if (!confirmed) return;
  }
  if (typeof window.stopMockMediaPlayers === "function") stopMockMediaPlayers(true);
  if (typeof window.stopMockExamSpeech === "function") stopMockExamSpeech({ message: "", forceStatus: false });
  if (document.fullscreenElement) {
    try {
      document.exitFullscreen();
    } catch {
      // ignore browser-specific fullscreen teardown errors
    }
  }
  persistExamWorkspaceViewport();
  state.pausedExamSession = currentExamSessionSnapshot();
  state.examWorkspaceActive = false;
  pauseExamTimer();
  renderExamWorkspace();
  renderPausedExamSessionPanel();
  persistExamUiPreferences();
  pushAppToast("Sitzung pausiert. Das Material bleibt rechts verfügbar.", "success");
};

window.syncExamScopeUi = function syncExamScopeUi() {
  const isFull = els.examScope.value === "full";
  if (!isFull) {
    const availableModules = Array.from(els.examModule.options || []).map((option) => option.value);
    if (state.lastExamModuleUsed && availableModules.includes(state.lastExamModuleUsed)) {
      els.examModule.value = state.lastExamModuleUsed;
    }
  }
  els.examModule.disabled = isFull;
  const moduleField = els.examModule.closest(".field");
  moduleField?.classList.toggle("hidden", isFull);
  moduleField?.classList.toggle("field-disabled", false);
};

window.getSelectedOfficialModule = function getSelectedOfficialModule() {
  if (els.examScope.value === "full") return null;
  return (state.officialExam?.modules || []).find((item) => item.key === els.examModule.value) || null;
};

window.getSelectedExamDurationMinutes = function getSelectedExamDurationMinutes() {
  const modules = state.officialExam?.modules || [];
  if (!modules.length) return 0;
  if (els.examScope.value === "full") {
    return modules.reduce((total, item) => total + (item.duration_minutes || 0) + (item.prep_minutes || 0), 0);
  }
  const selectedModule = getSelectedOfficialModule();
  return selectedModule ? (selectedModule.duration_minutes || 0) + (selectedModule.prep_minutes || 0) : 0;
};

window.getSelectedExamLabel = function getSelectedExamLabel() {
  const selectedModule = getSelectedOfficialModule();
  return els.examScope.value === "full" ? "Gesamtpr\u00fcfung" : (selectedModule?.label || els.examModule.value.toUpperCase());
};

window.applyLevelTheme = function applyLevelTheme(level = null) {
  const normalizedLevel = String(level || els.globalLevel?.value || "B2").toUpperCase();
  const allowed = ["A1", "A2", "B1", "B2", "C1", "C2"];
  const nextLevel = allowed.includes(normalizedLevel) ? normalizedLevel : "B2";
  document.body?.setAttribute("data-level", nextLevel);
  document.documentElement?.setAttribute("data-level", nextLevel);
};

window.currentExamTimerContextKey = function currentExamTimerContextKey() {
  return [els.globalLevel.value, els.examScope.value, els.examScope.value === "full" ? "gesamtpruefung" : els.examModule.value].join("|");
};

window.currentExamSessionSnapshot = function currentExamSessionSnapshot() {
  return {
    level: els.globalLevel.value,
    scope: els.examScope.value,
    module: els.examModule.value,
    selectedPracticeSetKey: state.selectedPracticeSetKey,
    selectedPracticeResourceType: state.selectedPracticeResourceType,
    timerContextKey: currentExamTimerContextKey(),
  };
};

window.applyExamSessionSnapshot = function applyExamSessionSnapshot(snapshot) {
  if (!snapshot) return;
  if (snapshot.level) els.globalLevel.value = snapshot.level;
  applyLevelTheme(snapshot.level || els.globalLevel.value);
  if (snapshot.scope) els.examScope.value = snapshot.scope;
  if (snapshot.module) {
    state.lastExamModuleUsed = snapshot.module;
    els.examModule.value = snapshot.module;
  }
  syncExamScopeUi();
  state.selectedPracticeSetKey = snapshot.selectedPracticeSetKey || null;
  state.selectedPracticeResourceType = snapshot.selectedPracticeResourceType || null;
  persistExamUiPreferences();
};

window.renderPausedExamSessionPanel = function renderPausedExamSessionPanel() {
  const session = state.pausedExamSession;
  const hasPausedSession = state.examTimerPaused && state.examRemainingMs > 0 && session?.timerContextKey;
  els.examPausedSessionPanel.classList.toggle("hidden", !hasPausedSession);
  if (!hasPausedSession) return;

  const scopeLabel = session.scope === "full" ? "Gesamtprüfung" : `Ein Modul · ${(session.module || "").toUpperCase()}`;
  const totalSeconds = Math.floor((state.examRemainingMs || 0) / 1000);
  const remainingLabel = `${String(Math.floor(totalSeconds / 60)).padStart(2, "0")}:${String(totalSeconds % 60).padStart(2, "0")}`;
  const currentMatchesPaused = session.timerContextKey === currentExamTimerContextKey();
  els.examPausedSessionSummary.innerHTML = `
    <strong>${escapeHtml(session.level || "B2")} · ${escapeHtml(scopeLabel)}</strong><br />
    Restzeit: ${escapeHtml(remainingLabel)}${currentMatchesPaused ? "" : "<br /><span class='muted'>Die aktuelle Auswahl weicht von der pausierten Sitzung ab.</span>"}
  `;
};

window.resumePausedExamSession = async function resumePausedExamSession() {
  const snapshot = state.pausedExamSession;
  if (!snapshot) return;
  applyExamSessionSnapshot(snapshot);
  await loadOfficialExam();
  openOfficialExamWorkspace(snapshot.selectedPracticeSetKey, { restoreTimer: true, restoreViewport: true, smoothScroll: false });
};

window.willRestartReplacePausedSession = function willRestartReplacePausedSession() {
  const snapshot = state.pausedExamSession;
  if (!snapshot || !state.examTimerPaused || state.examRemainingMs <= 0) return false;
  return snapshot.timerContextKey !== currentExamTimerContextKey()
    || (snapshot.selectedPracticeSetKey || null) !== (state.selectedPracticeSetKey || null)
    || (snapshot.selectedPracticeResourceType || null) !== (state.selectedPracticeResourceType || null);
};

window.restartExamSessionFromHub = async function restartExamSessionFromHub() {
  if (willRestartReplacePausedSession()) {
    const scopeLabel = state.pausedExamSession?.scope === "full" ? "Gesamtprüfung" : `Ein Modul · ${(state.pausedExamSession?.module || "").toUpperCase()}`;
    const confirmed = await openConfirmModal({
      title: "Pausierte Sitzung verwerfen?",
      message: `Die pausierte Sitzung ${state.pausedExamSession?.level || "B2"} · ${scopeLabel} wird verworfen. Wirklich neu starten?`,
      confirmLabel: "Neu starten",
      cancelLabel: "Abbrechen",
    });
    if (!confirmed) return;
  }
  resetExamTimer();
  renderPausedExamSessionPanel();
  await generateExam();
};

window.currentMockDraftKey = function currentMockDraftKey() {
  return `${currentExamTimerContextKey()}|variant:${state.mockVariantCounter}`;
};

window.persistCurrentMockDraft = function persistCurrentMockDraft() {
  const answersContainer = document.getElementById("examMockQuestions");
  if (!answersContainer || state.selectedPracticeResourceType !== "mock") return;
  state.mockDraftKey = currentMockDraftKey();
  state.mockDraftAnswers = {
    ...(state.mockDraftAnswers || {}),
    ...collectAnswers(answersContainer),
  };
  persistExamUiPreferences();
};

let mockExamRequestPromise = null;
let mockExamRequestSignature = null;

window.hasStartedMockDraft = function hasStartedMockDraft() {
  const answersContainer = document.getElementById("examMockQuestions");
  const liveAnswers = answersContainer ? Object.values(collectAnswers(answersContainer)) : [];
  if (liveAnswers.some((value) => String(value || "").trim())) return true;
  return Object.values(state.mockDraftAnswers || {}).some((value) => String(value || "").trim());
};

window.currentMockSignature = function currentMockSignature() {
  return currentExamTimerContextKey();
};

window.renderMockLoadingPanel = function renderMockLoadingPanel(forceRegenerate = false) {
  const scopeLabel = els.examScope.value === "full" ? "Gesamtpruefung" : `Modul ${getSelectedExamLabel()}`;
  const variantLabel = `Variante ${state.mockVariantCounter}`;
  const loadingTitle = forceRegenerate ? "Neuer Goethe-Mock wird erzeugt ..." : "Goethe-Mock wird geladen ...";
  return `
    <div class="soft-panel exam-mock-loading-panel">
      <div class="exam-mock-loading-head">
        <div>
          <p class="exam-kicker">AI-Mock Praxis</p>
          <strong>${escapeHtml(loadingTitle)}</strong>
        </div>
        <span class="exam-chip">Live-Aufbau</span>
      </div>
      <p>Die App baut gerade einen neuen ${escapeHtml(scopeLabel)}-Mock im Goethe-Rahmen. Die offiziellen Ansichten bleiben links jederzeit verfügbar.</p>
      <div class="exam-mock-loading-meta">
        <span class="exam-chip">${escapeHtml(variantLabel)}</span>
        <span class="exam-chip">${escapeHtml(els.globalLevel.value)} · ${escapeHtml(scopeLabel)}</span>
        <span class="exam-chip">Validierter Schnellpfad</span>
      </div>
      <div class="exam-loading-progress" aria-hidden="true"><span></span></div>
      <div class="exam-loading-skeleton-grid" aria-hidden="true">
        <span class="exam-loading-skeleton exam-loading-skeleton-wide"></span>
        <span class="exam-loading-skeleton"></span>
        <span class="exam-loading-skeleton"></span>
        <span class="exam-loading-skeleton exam-loading-skeleton-wide"></span>
      </div>
      <ol class="exam-loading-steps">
        <li>Blueprint und offizieller Modulrahmen werden geladen.</li>
        <li>Aufgaben, Punkte und Reihenfolge werden zusammengesetzt.</li>
        <li>Arbeitsbogen und Medienpaket werden vorbereitet.</li>
      </ol>
      <p class="muted">Der Mock wird jetzt so schnell wie möglich aufgebaut. Wenn lokales LLM-Tuning zu langsam wäre, bleibt die App automatisch auf dem schnellen, validierten Goethe-Blueprint-Pfad.</p>
    </div>
  `;
};

window.resetMockExamSessionState = function resetMockExamSessionState(options = {}) {
  if (options.clearDrafts) {
    state.mockDraftKey = null;
    state.mockDraftAnswers = {};
  }
  state.mockExamPageIndex = 0;
  state.mockEvaluation = null;
  state.mockReviewFilter = "all";
  persistExamUiPreferences();
};

window.captureMockDraftAnswers = function captureMockDraftAnswers() {
  const answersContainer = document.getElementById("examMockQuestions");
  if (answersContainer && state.selectedPracticeResourceType === "mock") {
    state.mockDraftAnswers = {
      ...(state.mockDraftAnswers || {}),
      ...collectAnswers(answersContainer),
    };
    state.mockDraftKey = currentMockDraftKey();
    persistExamUiPreferences();
  }
  return { ...(state.mockDraftAnswers || {}) };
};

window.lookupMockPartMeta = function lookupMockPartMeta(sectionKey, sectionTitle) {
  const module = (state.exam?.official_reference?.modules || state.officialExam?.modules || []).find((item) => item.key === sectionKey);
  const part = (module?.parts || []).find((item) => item.title === sectionTitle);
  return {
    moduleLabel: module?.label || (sectionKey || "").toUpperCase() || "Prüfung",
    partKey: part?.key || `${sectionKey || "general"}-${sectionTitle || "part"}`,
    instructions: part?.instructions || "",
    points: Number(part?.points || 0),
    recommendedMinutes: Number(part?.recommended_minutes || 0),
    audioPlays: Number(part?.audio_plays || 0),
    minWords: Number(part?.min_words || 0),
    taskTypes: Array.isArray(part?.task_types) ? part.task_types : [],
  };
};

window.getMockExamPages = function getMockExamPages() {
  const items = Array.isArray(state.exam?.items) ? state.exam.items : [];
  const pages = [];
  let currentPage = null;
  items.forEach((item, absoluteIndex) => {
    const sectionKey = item.section || "general";
    const sectionTitle = item.section_title || "Teil";
    const pageIdentity = `${sectionKey}::${sectionTitle}`;
    if (!currentPage || currentPage.identity !== pageIdentity) {
      const meta = lookupMockPartMeta(sectionKey, sectionTitle);
      currentPage = {
        identity: pageIdentity,
        sectionKey,
        sectionLabel: meta.moduleLabel,
        sectionTitle,
        partKey: meta.partKey,
        instructions: meta.instructions,
        partPoints: meta.points,
        recommendedMinutes: meta.recommendedMinutes,
        audioPlays: meta.audioPlays,
        minWords: meta.minWords,
        taskTypes: meta.taskTypes,
        items: [],
        startIndex: absoluteIndex,
      };
      pages.push(currentPage);
    }
    currentPage.items.push(item);
  });
  return pages.map((page, index) => ({
    ...page,
    index,
    totalPoints: page.partPoints || page.items.reduce((sum, item) => sum + Number(item.points || 0), 0),
  }));
};

window.getMockExamAnswers = function getMockExamAnswers() {
  return captureMockDraftAnswers();
};

window.getMockEvaluationResultMap = function getMockEvaluationResultMap() {
  const entries = Array.isArray(state.mockEvaluation?.results) ? state.mockEvaluation.results : [];
  return new Map(entries.map((item) => [item.item_id, item]));
};

window.getMockReviewResultsByFilter = function getMockReviewResultsByFilter(filter = state.mockReviewFilter || "all") {
  const entries = Array.isArray(state.mockEvaluation?.results) ? state.mockEvaluation.results : [];
  if (filter === "empty") return entries.filter((item) => item.status === "empty");
  if (filter === "problem") return entries.filter((item) => ["empty", "incorrect", "weak", "partial"].includes(item.status));
  if (filter === "strong") return entries.filter((item) => ["strong", "excellent", "correct"].includes(item.status));
  return entries;
};

window.getFilteredMockEvaluationPayload = function getFilteredMockEvaluationPayload() {
  if (!state.mockEvaluation) return null;
  const filter = state.mockReviewFilter || "all";
  if (filter === "all") return state.mockEvaluation;
  const filterMeta = {
    problem: {
      label: "Mit Handlungsbedarf",
      copy: "Es werden nur Aufgaben gezeigt, die noch leer, kritisch oder nur teilweise gelöst sind.",
    },
    empty: {
      label: "Nur leer",
      copy: "Es werden nur leer abgegebene Aufgaben gezeigt.",
    },
    strong: {
      label: "Nur stark",
      copy: "Es werden nur starke oder bereits sehr gute Aufgaben gezeigt.",
    },
  };
  return {
    ...state.mockEvaluation,
    results: getMockReviewResultsByFilter(filter),
    review_filter_label: filterMeta[filter]?.label || "",
    review_filter_copy: filterMeta[filter]?.copy || "",
  };
};

window.setMockReviewFilter = function setMockReviewFilter(nextFilter = "all") {
  state.mockReviewFilter = nextFilter;
  persistExamUiPreferences();
  renderMockExamWorkspace();
};

window.jumpToMockReviewTarget = function jumpToMockReviewTarget(filter = "problem") {
  const targetResult = getMockReviewResultsByFilter(filter)[0];
  if (!targetResult) {
    pushAppToast("Fuer diesen Filter gibt es aktuell keine passende Aufgabe.", "info", 2400);
    return;
  }
  const pages = getMockExamPages();
  const pageIndex = pages.findIndex((page) => (page.items || []).some((item) => item.id === targetResult.item_id));
  if (pageIndex >= 0) setMockExamPageIndex(pageIndex);
  window.requestAnimationFrame(() => {
    const answerControl = document.querySelector(`[data-answer-input="${CSS.escape(targetResult.item_id)}"]`);
    const questionCard = answerControl?.closest?.(".exam-mock-question-card");
    if (questionCard) questionCard.scrollIntoView({ block: "start", behavior: "smooth" });
  });
};

window.getMockPageProgress = function getMockPageProgress(page) {
  const answers = getMockExamAnswers();
  const answered = (page?.items || []).filter((item) => String(answers[item.id] || "").trim()).length;
  const total = (page?.items || []).length;
  return { answered, total };
};

window.setMockExamPageIndex = function setMockExamPageIndex(nextIndex) {
  const pages = getMockExamPages();
  if (!pages.length) {
    state.mockExamPageIndex = 0;
    return;
  }
  const clampedIndex = Math.max(0, Math.min(Number(nextIndex) || 0, pages.length - 1));
  captureMockDraftAnswers();
  state.mockExamPageIndex = clampedIndex;
  persistExamUiPreferences();
  renderMockExamWorkspace();
};

window.toggleMockExamFullscreen = async function toggleMockExamFullscreen() {
  if (!document.fullscreenEnabled || !els.examWorkspace) {
    pushAppToast("Vollbild wird in diesem Browser nicht unterstuetzt.", "warning", 2600);
    return;
  }
  if (document.fullscreenElement) {
    await document.exitFullscreen();
    return;
  }
  await els.examWorkspace.requestFullscreen();
};

window.renderMockExamPreparationPanel = function renderMockExamPreparationPanel() {
  const practiceSet = getDefaultPracticeSet();
  const scopeLabel = els.examScope.value === "full" ? "Gesamtpruefung" : getSelectedExamLabel();
  const nextSeed = `${currentMockSignature()}|variant:${state.mockVariantCounter}`;
  const hasCurrentVariant = state.exam && state.exam.mock_signature === currentMockSignature();
  const officialModules = Array.isArray(state.officialExam?.modules) ? state.officialExam.modules : [];
  const prepModules = els.examScope.value === "full"
    ? officialModules
    : officialModules.filter((module) => module.key === els.examModule.value);
  const prepDuration = prepModules.reduce((total, module) => total + Number(module.duration_minutes || 0) + Number(module.prep_minutes || 0), 0);
  const prepPoints = prepModules.reduce((total, module) => total + Number(module.scoring?.max_points || 0), 0);
  const prepNotes = prepModules.flatMap((module) => (module.parts || []).map((part) => {
    const notes = [
      part.audio_plays ? `${part.audio_plays}x hören` : "",
      part.min_words ? `mind. ${part.min_words} Wörter` : "",
    ].filter(Boolean).join(" · ");
    return notes ? `${part.title}: ${notes}` : "";
  })).filter(Boolean).slice(0, 3);
  const currentSummary = hasCurrentVariant
    ? `<div class="exam-chip-row"><span class="exam-chip">Aktive Variante ${escapeHtml(String(state.exam.mock_variant_counter || state.mockVariantCounter))}</span><span class="exam-chip">${escapeHtml(state.exam.generation_mode || "mock")}</span>${state.exam.generation_elapsed_ms ? `<span class="exam-chip">${escapeHtml(formatMockGenerationDuration(state.exam.generation_elapsed_ms))}</span>` : ""}</div><p class="muted">Sie können den vorhandenen Mock fortsetzen oder eine neue Variante erzeugen.</p>`
    : "<p class='muted'>Noch kein Mock für diese Auswahl geladen. Die Generierung startet erst nach Ihrem Klick.</p>";
  return `
    <section class="soft-panel exam-mock-prep-panel">
      <div class="exam-mock-prep-head">
        <div>
          <p class="exam-kicker">AI-Mock Praxis</p>
          <strong>Mock-Session vorbereiten</strong>
        </div>
        <span class="exam-chip">Nicht offiziell</span>
      </div>
      <p>Hier erzeugen Sie eine neue Trainingsvariante im Goethe-Rahmen. Das offizielle Material bleibt dabei unverändert verfügbar.</p>
      <div class="exam-mock-prep-grid">
        <article class="exam-resource-card">
          <span class="exam-resource-type">Was erzeugt wird</span>
          <strong>${escapeHtml(scopeLabel)}</strong>
          <span class="exam-resource-meta">${escapeHtml(els.globalLevel.value)} · ${escapeHtml(practiceSet?.label || "Goethe-Mock")}</span>
        </article>
        <article class="exam-resource-card">
          <span class="exam-resource-type">Variante</span>
          <strong>Neue Seed bei jedem Klick</strong>
          <span class="exam-resource-meta">${escapeHtml(nextSeed)}</span>
        </article>
        <article class="exam-resource-card">
          <span class="exam-resource-type">Offizieller Rahmen</span>
          <strong>${escapeHtml(String(prepDuration || getSelectedExamDurationMinutes()))} Min. · ${escapeHtml(String(prepPoints || 0))} Punkte</strong>
          <span class="exam-resource-meta">${escapeHtml(prepNotes[0] || "Zeit, Punkte und Teilregeln folgen dem offiziellen Goethe-Rahmen der aktuellen Auswahl.")}</span>
        </article>
        <article class="exam-resource-card">
          <span class="exam-resource-type">Ablauf</span>
          <strong>Seitenweise wie ein Exam Workspace</strong>
          <span class="exam-resource-meta">${escapeHtml(prepNotes[1] || "Teilnavigation, Vollbild, Antworten, Abgabe und Goethe-aligned Auswertung.")}</span>
        </article>
      </div>
      ${prepNotes[2] ? `<p class="muted">${escapeHtml(prepNotes[2])}</p>` : ""}
      ${currentSummary}
      <div class="inline-actions exam-mock-prep-actions">
        <button id="examMockGenerateBtn" data-force-regenerate="${hasCurrentVariant ? "1" : "0"}" class="primary-btn"${state.examRequestInFlight ? " disabled" : ""}>${hasCurrentVariant ? "Neue Variante erzeugen" : "Mock generieren"}</button>
        ${hasCurrentVariant ? `<button id="examMockResumeBtn" class="ghost-btn">Aktuellen Mock fortsetzen</button>` : ""}
      </div>
    </section>
  `;
};

window.hasExamContextSwitchRisk = function hasExamContextSwitchRisk(nextResourceType = null) {
  const targetType = nextResourceType || state.selectedPracticeResourceType;
  if (targetType !== "mock") return false;
  return hasStartedMockDraft();
};

window.confirmExamContextSwitch = async function confirmExamContextSwitch(message, confirmLabel = "Wechseln") {
  return openConfirmModal({
    title: "Ansicht wechseln?",
    message,
    confirmLabel,
    cancelLabel: "Abbrechen",
  });
};

window.getExamSubmissionRisk = function getExamSubmissionRisk() {
  const items = Array.isArray(state.exam?.items) ? state.exam.items : [];
  if (!items.length) return { blankCount: 0, totalCount: 0 };
  const answers = getMockExamAnswers();
  const blankCount = items.filter((item) => !String(answers[item.id] || "").trim()).length;
  return { blankCount, totalCount: items.length };
};

window.isRecoverableMockLoadError = function isRecoverableMockLoadError(error) {
  const message = String(error?.message || "").toLowerCase();
  return message.includes("cancel") || message.includes("solicitud") || message.includes("tardado demasiado") || message.includes("timeout");
};

window.loadMockExam = async function loadMockExam(forceRegenerate = false) {
  if (typeof window.stopMockMediaPlayers === "function") stopMockMediaPlayers(true);
  if (typeof window.stopMockExamSpeech === "function") stopMockExamSpeech({ message: "", forceStatus: false });
  const nextSignature = currentMockSignature();
  const pendingRecommendation = getPendingRecommendationAttribution();
  if (state.mockVariantSignature !== nextSignature) {
    state.mockVariantCounter = 1;
    resetMockExamSessionState({ clearDrafts: true });
  }
  if (forceRegenerate) {
    state.mockVariantCounter += 1;
    resetMockExamSessionState({ clearDrafts: true });
  }
  if (
    !forceRegenerate
    && !pendingRecommendation?.recommendationEventId
    && state.exam?.mock_signature === nextSignature
    && state.exam?.mock_variant_counter === state.mockVariantCounter
    && state.exam?.mock_audio_voice_gender === state.mockAudioVoiceGender
  ) {
    refreshMockAudioVoiceUi();
    return state.exam;
  }
  state.examMode = "mock";
  const variantSeed = `${nextSignature}|variant:${state.mockVariantCounter}`;
  const requestSignature = `${variantSeed}|voice:${state.mockAudioVoiceGender}|scope:${els.examScope.value}|module:${els.examModule.value}`;
  if (!forceRegenerate && state.examRequestInFlight && mockExamRequestPromise && mockExamRequestSignature === requestSignature) {
    return mockExamRequestPromise;
  }
  state.examRequestInFlight = true;
  setAppBusyBanner(`Goethe-Mock wird erzeugt ... ${els.globalLevel.value} · ${els.examScope.value === "full" ? "Gesamtprüfung" : getSelectedExamLabel()}`, "warning");
  if (els.examWorkspaceBody && state.selectedPracticeResourceType === "mock") {
    els.examWorkspaceBody.innerHTML = renderMockLoadingPanel(forceRegenerate);
  }
  mockExamRequestSignature = requestSignature;
  mockExamRequestPromise = (async () => {
    const basePayload = {
      level: els.globalLevel.value,
      scope: els.examScope.value,
      module: els.examModule.value,
      variant_seed: variantSeed,
      mock_audio_voice_gender: state.mockAudioVoiceGender,
      recommendation_event_id: pendingRecommendation?.recommendationEventId || null,
    };
    const timeouts = [15000];
    let lastError = null;
    for (let attempt = 0; attempt < timeouts.length; attempt += 1) {
      try {
        state.exam = await apiFetch("/api/exam/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          timeoutMs: timeouts[attempt],
          body: JSON.stringify(basePayload),
        });
        if (pendingRecommendation?.recommendationEventId) clearPendingRecommendationAttribution();
        state.mockVariantSignature = nextSignature;
        state.mockDraftKey = currentMockDraftKey();
        state.exam.mock_signature = nextSignature;
        state.exam.mock_variant_counter = state.mockVariantCounter;
        state.exam.mock_audio_voice_gender = state.mockAudioVoiceGender;
        state.mockExamPageIndex = 0;
        state.mockEvaluation = null;
        persistExamUiPreferences();
        refreshMockAudioVoiceUi();
        loadMockExamHealth();
        pushAppToast(
          `Neuer Goethe-Mock bereit: ${state.exam.generation_mode || "mock"}${state.exam.generation_elapsed_ms ? ` · ${formatMockGenerationDuration(state.exam.generation_elapsed_ms)}` : ""}`,
          state.exam.fallback_used ? "warning" : "success",
        );
        return state.exam;
      } catch (error) {
        lastError = error;
        if (attempt < timeouts.length - 1 && isRecoverableMockLoadError(error)) {
          pushAppToast("Die Mock-Anfrage wurde erneut versucht, damit der Goethe-Mock sauber geladen wird.", "warning", 2600);
          continue;
        }
        pushAppToast(error.message || "Der Mock konnte nicht erzeugt werden.", "error", 4200);
        throw error;
      }
    }
    throw lastError || new Error("Der Mock konnte nicht erzeugt werden.");
  })();
  try {
    return await mockExamRequestPromise;
  } finally {
    state.examRequestInFlight = false;
    setAppBusyBanner("");
    if (mockExamRequestSignature === requestSignature) {
      mockExamRequestPromise = null;
      mockExamRequestSignature = null;
    }
  }
};

window.getMockMediaSegments = function getMockMediaSegments() {
  return Array.isArray(state.exam?.mock_media_pack) ? state.exam.mock_media_pack : [];
};

window.getMockMediaSegment = function getMockMediaSegment(partKey) {
  return getMockMediaSegments().find((item) => item.part_key === partKey) || null;
};

window.getMockAudioVoicePreferenceLabel = function getMockAudioVoicePreferenceLabel(gender = state.mockAudioVoiceGender) {
  if (gender === "female") return "Frau";
  if (gender === "male") return "Mann";
  return "Automatisch";
};

window.describeMockAudioState = function describeMockAudioState(segments = getMockMediaSegments()) {
  const preferenceLabel = getMockAudioVoicePreferenceLabel();
  if (!segments.length) {
    return `Neue KI-Mock-Hörtexte nutzen aktuell die Stimmwahl "${preferenceLabel}". Offizielle Goethe-Audios bleiben unverändert.`;
  }
  const serverSegments = segments.filter((segment) => Boolean(segment.audio_url));
  const voiceLabels = [...new Set(serverSegments.map((segment) => String(segment.voice_label || "").trim()).filter(Boolean))];
  if (serverSegments.length) {
    const voiceSuffix = voiceLabels.length ? ` Aktive Server-Stimme: ${voiceLabels.join(", ")}.` : "";
    return `Die aktuelle Mock-Variante nutzt in ${serverSegments.length}/${segments.length} Hörteilen lokales Backend-Audio. Bevorzugte Stimmwahl: ${preferenceLabel}.${voiceSuffix}`;
  }
  if (chatSpeechSupported()) {
    return `Die aktuelle Mock-Variante nutzt Browser-Audio als Fallback. Bevorzugte Stimmwahl: ${preferenceLabel}.`;
  }
  return `Die aktuelle Mock-Variante zeigt nur das Transkript. Bevorzugte Stimmwahl: ${preferenceLabel}.`;
};

window.refreshMockAudioVoiceUi = function refreshMockAudioVoiceUi() {
  if (els.settingsMockAudioVoiceGender && els.settingsMockAudioVoiceGender.value !== state.mockAudioVoiceGender) {
    els.settingsMockAudioVoiceGender.value = state.mockAudioVoiceGender;
  }
  const workspaceSelect = document.getElementById("mockAudioVoiceGenderSelect");
  if (workspaceSelect && workspaceSelect.value !== state.mockAudioVoiceGender) {
    workspaceSelect.value = state.mockAudioVoiceGender;
  }
  if (els.settingsMockAudioState) {
    els.settingsMockAudioState.textContent = describeMockAudioState();
  }
};

window.setMockExamSpeechStatus = function setMockExamSpeechStatus(message, tone = "neutral") {
  const statusEl = document.getElementById("examMockMediaStatus");
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.classList.remove("is-success", "is-warning", "is-error");
  if (tone === "success") statusEl.classList.add("is-success");
  if (tone === "warning") statusEl.classList.add("is-warning");
  if (tone === "error") statusEl.classList.add("is-error");
};

window.refreshMockMediaPackControls = function refreshMockMediaPackControls() {
  const activePartKey = state.mockMediaSpeechPartKey;
  const speechSupported = chatSpeechSupported();
  document.querySelectorAll("[data-play-mock-media]").forEach((button) => {
    const isActive = button.dataset.playMockMedia === activePartKey;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
    button.textContent = isActive ? "Wird vorgelesen ..." : (button.dataset.baseLabel || "Teil abspielen");
    button.disabled = !speechSupported;
  });
  document.querySelectorAll("[data-stop-mock-media]").forEach((button) => {
    button.disabled = !speechSupported || !activePartKey || button.dataset.stopMockMedia !== activePartKey;
  });
};

window.stopMockMediaPlayers = function stopMockMediaPlayers(reset = false) {
  document.querySelectorAll("[data-server-mock-media]").forEach((player) => {
    try {
      player.pause();
      if (reset) player.currentTime = 0;
    } catch {
      // ignore browser media errors while tearing down the workspace
    }
  });
};

window.stopMockExamSpeech = function stopMockExamSpeech(options = {}) {
  const hadActivePlayback = Boolean(state.mockMediaSpeechPartKey);
  state.mockMediaSpeechPartKey = null;
  state.mockMediaSpeechRemainingPlays = 0;
  if (chatSpeechSupported()) window.speechSynthesis.cancel();
  refreshMockMediaPackControls();
  if (options.forceStatus || (hadActivePlayback && options.message !== "")) {
    setMockExamSpeechStatus(options.message || "Hörtext gestoppt.", options.tone || "neutral");
  }
};

window.updateMockAudioVoicePreference = async function updateMockAudioVoicePreference(nextGender) {
  if (!["auto", "female", "male"].includes(nextGender) || state.mockAudioVoiceGender === nextGender) return;
  state.mockAudioVoiceGender = nextGender;
  persistMockAudioVoicePreference();
  persistExamUiPreferences();
  refreshMockAudioVoiceUi();
  stopMockMediaPlayers(true);
  stopMockExamSpeech({ message: "", forceStatus: false });
  if (state.selectedPracticeResourceType !== "mock" || !state.exam) return;
  setMockExamSpeechStatus("Mock-Stimme wird aktualisiert ...", "warning");
  try {
    const usesServerAudio = getMockMediaSegments().some((segment) => Boolean(segment.audio_url));
    if (!usesServerAudio) {
      renderMockExamWorkspace();
      setMockExamSpeechStatus("Stimme aktualisiert. Der Mock bleibt unverändert.", "success");
      return;
    }
    await loadMockExam(false);
    renderMockExamWorkspace();
    refreshMockAudioVoiceUi();
  } catch (error) {
    setMockExamSpeechStatus(error.message || "Die Mock-Stimme konnte nicht aktualisiert werden.", "error");
  }
};

window.buildMockSpeechPassages = function buildMockSpeechPassages(scriptText) {
  return String(scriptText || "")
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((chunk) => chunk.trim())
    .filter(Boolean);
};

window.playMockExamMediaSegment = function playMockExamMediaSegment(partKey) {
  const segment = getMockMediaSegment(partKey);
  if (!segment) return;
  if (!chatSpeechSupported()) {
    setMockExamSpeechStatus("Systemstimme ist nicht verfügbar. Nutzen Sie das Transkript.", "error");
    refreshMockMediaPackControls();
    return;
  }

  stopMockMediaPlayers(true);
  stopMockExamSpeech({ message: "", forceStatus: false });
  const voiceEntry = getChatTtsVoice(state.mockAudioVoiceGender);
  const passages = buildMockSpeechPassages(segment.script_text || "");
  let remainingPlays = Math.max(1, Number(segment.audio_plays || 1));
  state.mockMediaSpeechPartKey = partKey;
  state.mockMediaSpeechRemainingPlays = remainingPlays;

  const speakPass = () => {
    if (state.mockMediaSpeechPartKey !== partKey) return;
    const currentPass = Number(segment.audio_plays || 1) - remainingPlays + 1;
    const queue = passages.length ? passages : [String(segment.script_text || "").trim()];
    const playbackRate = Math.max(0.82, Math.min(1.02, Number(segment.playback_rate || 0.95) - (voiceEntry?.isNatural ? 0 : 0.03)));
    const speakChunk = (chunkIndex) => {
      if (state.mockMediaSpeechPartKey !== partKey) return;
      if (chunkIndex >= queue.length) {
        remainingPlays -= 1;
        state.mockMediaSpeechRemainingPlays = remainingPlays;
        if (remainingPlays > 0) {
          setMockExamSpeechStatus(`${segment.part_title}: nächster Durchgang startet ...`, "warning");
          window.setTimeout(() => speakPass(), 520);
          return;
        }
        state.mockMediaSpeechPartKey = null;
        state.mockMediaSpeechRemainingPlays = 0;
        refreshMockMediaPackControls();
        setMockExamSpeechStatus(`${segment.part_title}: Hörtext abgeschlossen. Sie können erneut starten oder das Transkript aufklappen.`, "success");
        return;
      }
      const utterance = new SpeechSynthesisUtterance(queue[chunkIndex]);
      utterance.lang = voiceEntry?.lang || voiceEntry?.regionCode || "de-DE";
      if (voiceEntry?.voice) utterance.voice = voiceEntry.voice;
      utterance.rate = playbackRate;
      utterance.pitch = state.mockAudioVoiceGender === "male" ? 0.95 : state.mockAudioVoiceGender === "female" ? 1.02 : 1;
      utterance.onstart = () => {
        setMockExamSpeechStatus(
          `${segment.part_title}: Durchgang ${currentPass}/${segment.audio_plays}. ${describeChatTtsVoice(voiceEntry)}`,
          "success"
        );
        refreshMockMediaPackControls();
      };
      utterance.onend = () => {
        if (state.mockMediaSpeechPartKey !== partKey) return;
        const pauseMs = chunkIndex < queue.length - 1 ? 260 : 420;
        window.setTimeout(() => speakChunk(chunkIndex + 1), pauseMs);
      };
      utterance.onerror = () => {
        if (state.mockMediaSpeechPartKey !== partKey) return;
        state.mockMediaSpeechPartKey = null;
        state.mockMediaSpeechRemainingPlays = 0;
        refreshMockMediaPackControls();
        setMockExamSpeechStatus("Die Systemstimme konnte nicht abgespielt werden.", "error");
      };
      window.speechSynthesis.speak(utterance);
    };
    speakChunk(0);
    return;
    const utterance = new SpeechSynthesisUtterance(String(segment.script_text || "").trim());
    utterance.lang = voiceEntry?.lang || voiceEntry?.regionCode || "de-DE";
    if (voiceEntry?.voice) utterance.voice = voiceEntry.voice;
    utterance.rate = Number(segment.playback_rate || 0.95);
    utterance.pitch = state.mockAudioVoiceGender === "male" ? 0.95 : state.mockAudioVoiceGender === "female" ? 1.02 : 1;
    utterance.onstart = () => {
      setMockExamSpeechStatus(
        `${segment.part_title}: Durchgang ${currentPass}/${segment.audio_plays}. ${describeChatTtsVoice(voiceEntry)}`,
        "success"
      );
      refreshMockMediaPackControls();
    };
    utterance.onend = () => {
      if (state.mockMediaSpeechPartKey !== partKey) return;
      remainingPlays -= 1;
      state.mockMediaSpeechRemainingPlays = remainingPlays;
      if (remainingPlays > 0) {
        setMockExamSpeechStatus(`${segment.part_title}: nächster Durchgang startet ...`, "warning");
        speakPass();
        return;
      }
      state.mockMediaSpeechPartKey = null;
      state.mockMediaSpeechRemainingPlays = 0;
      refreshMockMediaPackControls();
      setMockExamSpeechStatus(`${segment.part_title}: Hörtext abgeschlossen. Sie können erneut starten oder das Transkript aufklappen.`, "success");
    };
    utterance.onerror = () => {
      if (state.mockMediaSpeechPartKey !== partKey) return;
      state.mockMediaSpeechPartKey = null;
      state.mockMediaSpeechRemainingPlays = 0;
      refreshMockMediaPackControls();
      setMockExamSpeechStatus("Die Systemstimme konnte nicht abgespielt werden.", "error");
    };
    window.speechSynthesis.speak(utterance);
  };

  refreshMockMediaPackControls();
  speakPass();
};

window.renderMockMediaPack = function renderMockMediaPack() {
  const segments = getMockMediaSegments();
  if (!segments.length) return "";
  const speechSupported = chatSpeechSupported();
  const hasServerAudio = segments.some((segment) => Boolean(segment.audio_url));
  const stateSummary = describeMockAudioState(segments);
  const initialStatus = speechSupported
    ? "Systemstimme bereit. Das Transkript bleibt zusätzlich verfügbar."
    : "Auf diesem Gerät ist nur das Transkript verfügbar.";

  return `
    <section class="exam-mock-media-panel">
      <div class="exam-mock-media-head">
        <div>
          <p class="exam-kicker">Hören-Medien</p>
          <strong>Zusätzliche Hörhilfe</strong>
        </div>
        <div class="exam-mock-media-head-actions">
          <span class="exam-chip">${escapeHtml(String(segments.length))} Teile</span>
          <label class="field inline exam-mock-media-voice-field">
            <span>Mock-Stimme</span>
            <select id="mockAudioVoiceGenderSelect">
              <option value="auto"${state.mockAudioVoiceGender === "auto" ? " selected" : ""}>Automatisch</option>
              <option value="female"${state.mockAudioVoiceGender === "female" ? " selected" : ""}>Frau</option>
              <option value="male"${state.mockAudioVoiceGender === "male" ? " selected" : ""}>Mann</option>
            </select>
          </label>
        </div>
      </div>
      <p id="examMockMediaStatus" class="exam-mock-media-status${hasServerAudio ? " is-success" : (speechSupported ? "" : " is-warning")}">${escapeHtml(hasServerAudio ? "Vorbereitete Audiodateien sind verfügbar. Die Systemstimme bleibt zusätzlich nutzbar." : initialStatus)}</p>
      <p class="exam-mock-media-summary">${escapeHtml(stateSummary)}</p>
      <div class="exam-mock-media-grid">
        ${segments.map((segment) => {
          const playLabel = segment.audio_url
            ? "Systemstimme"
            : `Teil abspielen${segment.audio_plays > 1 ? ` (${segment.audio_plays}x)` : ""}`;
          const providerLabel = segment.audio_provider === "local_windows_tts"
            ? `Vorbereitete Audiodatei: ${segment.voice_label || "Systemstimme"}`
            : "Keine vorbereitete Audiodatei";
          return `
            <article class="exam-mock-media-card">
              <div class="exam-mock-media-meta">
                <span class="exam-resource-type">${escapeHtml(segment.module)}</span>
                <span class="muted">${escapeHtml(segment.part_title)}</span>
              </div>
              <strong>${escapeHtml(segment.source_title)}</strong>
              <div class="exam-chip-row">
                <span class="exam-chip">${escapeHtml(String(segment.audio_plays))}x hören</span>
                <span class="exam-chip">ca. ${escapeHtml(String(segment.duration_hint_seconds))} Sek.</span>
              </div>
              <p class="muted">${escapeHtml(providerLabel)}</p>
              ${segment.audio_url ? `<audio class="exam-media-player exam-mock-media-player" data-server-mock-media="${escapeHtml(segment.part_key)}" data-part-title="${escapeHtml(segment.part_title)}" controls preload="none" src="${escapeHtml(segment.audio_url)}"></audio>` : ""}
              <div class="inline-actions exam-mock-media-actions">
                <button class="primary-btn" data-play-mock-media="${escapeHtml(segment.part_key)}" data-base-label="${escapeHtml(playLabel)}"${speechSupported ? "" : " disabled"}>${escapeHtml(playLabel)}</button>
                <button class="ghost-btn" data-stop-mock-media="${escapeHtml(segment.part_key)}" disabled>Stopp</button>
              </div>
              <details class="exam-mock-media-transcript">
                <summary>Transkript anzeigen</summary>
                <div class="exam-mock-media-script">${escapeHtml(segment.script_text || "").replace(/\n/g, "<br />")}</div>
              </details>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
};

window.bindMockMediaPlayers = function bindMockMediaPlayers() {
  document.querySelectorAll("[data-server-mock-media]").forEach((player) => {
    if (player.dataset.bound === "true") return;
    player.dataset.bound = "true";
    player.addEventListener("play", () => {
      stopMockExamSpeech({ message: "", forceStatus: false });
      setMockExamSpeechStatus(`${player.dataset.partTitle || "Hörtext"}: Audiodatei läuft.`, "success");
    });
    player.addEventListener("ended", () => {
      setMockExamSpeechStatus(`${player.dataset.partTitle || "Hörtext"}: Audiodatei beendet.`, "success");
    });
    player.addEventListener("error", () => {
      setMockExamSpeechStatus("Die Audiodatei konnte nicht geladen werden. Die Systemstimme bleibt verfügbar.", "error");
    });
  });
};

window.renderMockExamPageMedia = function renderMockExamPageMedia(page) {
  const segment = page ? getMockMediaSegment(page.partKey) : null;
  if (!segment) return "";
  const providerLabel = segment.audio_url
    ? `Audiodatei verfügbar · ${segment.voice_label || "Systemstimme"}`
    : "Systemstimme mit Sprechpausen";
  return `
    <section class="exam-mock-part-media">
      <div class="exam-mock-part-media-head">
        <div>
          <p class="exam-kicker">Hören</p>
          <strong>${escapeHtml(segment.part_title)}</strong>
        </div>
        <div class="exam-chip-row">
          <span class="exam-chip">${escapeHtml(String(segment.audio_plays))}x hören</span>
          <span class="exam-chip">ca. ${escapeHtml(String(segment.duration_hint_seconds))} Sek.</span>
        </div>
      </div>
      <p class="muted">${escapeHtml(providerLabel)}</p>
      <div class="inline-actions exam-mock-media-actions">
        <button class="primary-btn" data-play-mock-media="${escapeHtml(segment.part_key)}" data-base-label="Teil abspielen">Teil abspielen</button>
        <button class="ghost-btn" data-stop-mock-media="${escapeHtml(segment.part_key)}" disabled>Stopp</button>
      </div>
      ${segment.audio_url ? `<details class="exam-mock-audio-advanced"><summary>Audiodatei anzeigen</summary><audio class="exam-media-player exam-mock-media-player" data-server-mock-media="${escapeHtml(segment.part_key)}" data-part-title="${escapeHtml(segment.part_title)}" controls preload="none" src="${escapeHtml(segment.audio_url)}"></audio></details>` : ""}
      <details class="exam-mock-media-transcript">
        <summary>Transkript anzeigen</summary>
        <div class="exam-mock-media-script">${escapeHtml(segment.script_text || "").replace(/\n/g, "<br />")}</div>
      </details>
      <p id="examMockMediaStatus" class="exam-mock-media-status">${escapeHtml(describeMockAudioState([segment]))}</p>
    </section>
  `;
};

window.renderMockExamPageNavigator = function renderMockExamPageNavigator(pages) {
  const answers = getMockExamAnswers();
  return pages.map((page) => {
    const answered = (page.items || []).filter((item) => String(answers[item.id] || "").trim()).length;
    const active = page.index === state.mockExamPageIndex;
    const completionTone = answered === 0 ? " is-empty" : answered >= page.items.length ? " is-complete" : " is-progress";
    return `
      <button class="exam-choice-btn exam-mock-page-btn${active ? " is-active" : ""}${completionTone}" data-mock-page-index="${escapeHtml(String(page.index))}">
        <span class="exam-choice-kicker">${escapeHtml(page.sectionLabel)}</span>
        <strong>${escapeHtml(page.sectionTitle)}</strong>
        <span class="exam-choice-meta">${escapeHtml(String(answered))}/${escapeHtml(String(page.items.length))} Antworten · ${escapeHtml(String(page.totalPoints))} Punkte</span>
      </button>
    `;
  }).join("");
};

window.renderMockExamQuestionCard = function renderMockExamQuestionCard(item, itemIndex, evaluationMap) {
  const id = `exam-mock-${item.id}`;
  const result = evaluationMap.get(item.id);
  const status = result?.status || "";
  const statusMeta = getEvaluationStatusMeta(status || "partial");
  const statusLabels = {
    empty: "Leer",
    incorrect: "Falsch",
    weak: "Zu schwach",
    partial: "Teilweise",
    strong: "Stark",
    excellent: "Sehr stark",
    correct: "Richtig",
  };
  const reviewTone = status ? `is-${status}` : "";
  const control = item.item_type === "mcq" || item.item_type === "true_false"
    ? `<select id="${id}" data-answer-input="${escapeHtml(item.id)}"${state.mockEvaluation ? " disabled" : ""}><option value="">-</option>${(item.options || []).map((opt) => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("")}</select>`
    : `<textarea id="${id}" data-answer-input="${escapeHtml(item.id)}" rows="${item.item_type === "open" ? 7 : 4}" placeholder="Antwort ..."${state.mockEvaluation ? " disabled" : ""}></textarea>`;
  return `
    <article class="question-card exam-mock-question-card ${reviewTone}">
      <p class="question-meta">${escapeHtml(item.section_title || "")} · ${escapeHtml(String(itemIndex + 1))} · ${escapeHtml(String(item.points))} Punkte${item.min_words ? ` · mind. ${escapeHtml(String(item.min_words))} Wörter` : ""}</p>
      <h3>${escapeHtml(item.prompt)}</h3>
      ${item.support_text ? `<div class="question-support">${escapeHtml(item.support_text).replace(/\n/g, "<br />")}</div>` : ""}
      ${control}
      ${result ? `
        <div class="exam-mock-review-box">
          <div class="exam-mock-review-head">
            <strong>${escapeHtml(String(result.score))} / ${escapeHtml(String(result.max_score))}</strong>
            <span class="evaluation-inline-pill is-${escapeHtml(status || "partial")}">${escapeHtml(statusLabels[status] || statusMeta.label)}</span>
          </div>
          <p class="exam-mock-review-copy">${escapeHtml(statusMeta.copy)}</p>
          ${result.user_answer ? `<p><strong>Ihre Antwort:</strong> ${escapeHtml(result.user_answer)}</p>` : "<p><strong>Ihre Antwort:</strong> <span class='muted'>leer</span></p>"}
          ${result.expected_answer && result.expected_answer !== "freie Bearbeitung" ? `<p><strong>Erwartet:</strong> ${escapeHtml(result.expected_answer)}</p>` : ""}
          ${result.corrected_version ? `<p><strong>Verbesserte Version:</strong> ${escapeHtml(result.corrected_version)}</p>` : ""}
          ${result.error_tags?.length ? `<div class="exam-mock-review-tags">${renderEvaluationErrorTags(result.error_tags, "exam-mock-review-tag")}</div>` : ""}
          <p class="muted">${escapeHtml(result.feedback || "")}</p>
          <p class="exam-mock-review-next"><strong>Nächster Schritt:</strong> ${escapeHtml(getEvaluationActionHint(status || "partial", result.error_tags || []))}</p>
        </div>
      ` : ""}
    </article>
  `;
};

window.renderMockExamSessionShell = function renderMockExamSessionShell() {
  const pages = getMockExamPages();
  if (!pages.length) return renderMockExamPreparationPanel();
  const page = pages[Math.max(0, Math.min(state.mockExamPageIndex || 0, pages.length - 1))];
  state.mockExamPageIndex = page.index;
  const pageProgress = getMockPageProgress(page);
  const evaluationMap = getMockEvaluationResultMap();
  const totalAnswered = pages.reduce((sum, entry) => sum + getMockPageProgress(entry).answered, 0);
  const totalQuestions = pages.reduce((sum, entry) => sum + entry.items.length, 0);
  const progressPercent = totalQuestions ? Math.round((totalAnswered / totalQuestions) * 100) : 0;
  const unansweredCount = Math.max(0, totalQuestions - totalAnswered);
  const failedSections = Array.isArray(state.mockEvaluation?.failed_sections) ? state.mockEvaluation.failed_sections : [];
  const reviewFilter = state.mockReviewFilter || "all";
  const filteredEvaluationPayload = getFilteredMockEvaluationPayload();
  const reviewFilterCopy = filteredEvaluationPayload?.review_filter_copy || "";
  const evaluationCounts = (state.mockEvaluation?.results || []).reduce((acc, item) => {
    const key = String(item.status || "partial");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const resultSummary = state.mockEvaluation
    ? `
      <section class="soft-panel exam-mock-result-summary">
        <p class="exam-kicker">Goethe-aligned Evaluation</p>
        <div class="exam-mock-result-summary-head">
          <strong>${escapeHtml(String(state.mockEvaluation.percent))}% · ${escapeHtml(String(state.mockEvaluation.score))}/${escapeHtml(String(state.mockEvaluation.max_score))}</strong>
          <span class="evaluation-inline-pill is-${state.mockEvaluation.passed ? "excellent" : "weak"}">${state.mockEvaluation.passed ? "Im Zielbereich" : "Noch nicht bestanden"}</span>
        </div>
        <p>${escapeHtml(state.mockEvaluation.summary || "")}</p>
        <div class="exam-chip-row">
          <span class="exam-chip">${escapeHtml(String(state.mockEvaluation.answered_count || 0))}/${escapeHtml(String(totalQuestions))} beantwortet</span>
          <span class="exam-chip">${escapeHtml(String(state.mockEvaluation.unanswered_count || 0))} leer</span>
          ${failedSections.length ? `<span class="exam-chip">Offene Sektionen: ${escapeHtml(failedSections.join(", "))}</span>` : ""}
        </div>
        <div class="exam-mock-result-flags">
          <span class="evaluation-inline-pill is-empty">Leer ${escapeHtml(String(evaluationCounts.empty || 0))}</span>
          <span class="evaluation-inline-pill is-weak">Kritisch ${escapeHtml(String((evaluationCounts.weak || 0) + (evaluationCounts.incorrect || 0)))}</span>
          <span class="evaluation-inline-pill is-partial">Teilweise ${escapeHtml(String(evaluationCounts.partial || 0))}</span>
          <span class="evaluation-inline-pill is-excellent">Stark ${escapeHtml(String((evaluationCounts.strong || 0) + (evaluationCounts.excellent || 0) + (evaluationCounts.correct || 0)))}</span>
        </div>
        <div class="exam-mock-review-actions">
          <button class="ghost-btn exam-mock-filter-btn${reviewFilter === "all" ? " is-active" : ""}" data-mock-review-filter="all">Alles</button>
          <button class="ghost-btn exam-mock-filter-btn${reviewFilter === "problem" ? " is-active" : ""}" data-mock-review-filter="problem">Mit Handlungsbedarf</button>
          <button class="ghost-btn exam-mock-filter-btn${reviewFilter === "empty" ? " is-active" : ""}" data-mock-review-filter="empty">Nur leer</button>
          <button class="ghost-btn exam-mock-filter-btn${reviewFilter === "strong" ? " is-active" : ""}" data-mock-review-filter="strong">Nur stark</button>
        </div>
        <div class="exam-mock-review-actions">
          <button class="ghost-btn exam-mock-jump-btn" data-mock-review-jump="problem">Zu erster offenen Baustelle</button>
          <button class="ghost-btn exam-mock-jump-btn" data-mock-review-jump="empty">Zu erster leeren Aufgabe</button>
        </div>
        ${reviewFilterCopy ? `<p class="exam-mock-review-filter-copy muted">${escapeHtml(reviewFilterCopy)}</p>` : ""}
      </section>
    `
    : "";
  const mediaPanel = page.sectionKey === "hoeren" ? renderMockExamPageMedia(page) : "";

  return `
    <section class="exam-mock-session-shell">
      <aside class="soft-panel exam-mock-session-sidebar">
        <div>
          <p class="exam-kicker">Session</p>
          <strong>${escapeHtml(state.exam?.title || "Goethe-Mock")}</strong>
        </div>
        <div class="exam-loading-progress exam-mock-session-progress" aria-hidden="true"><span style="width:${escapeHtml(String(progressPercent))}%"></span></div>
        <div class="exam-mock-session-stats">
          <article class="exam-mock-session-stat">
            <strong>${escapeHtml(String(totalAnswered))}</strong>
            <span>Beantwortet</span>
          </article>
          <article class="exam-mock-session-stat">
            <strong>${escapeHtml(String(unansweredCount))}</strong>
            <span>Offen</span>
          </article>
          <article class="exam-mock-session-stat">
            <strong>${escapeHtml(String(progressPercent))}%</strong>
            <span>Fortschritt</span>
          </article>
        </div>
        <p class="muted">${escapeHtml(String(pageProgress.answered))}/${escapeHtml(String(pageProgress.total))} Antworten im aktuellen Teil.</p>
        <div class="exam-choice-grid exam-mock-page-grid">
          ${renderMockExamPageNavigator(pages)}
        </div>
      </aside>
      <div class="exam-mock-session-main">
        <div class="inline-actions exam-mock-toolbar">
          <button id="examMockPrevPageBtn" class="ghost-btn"${page.index === 0 ? " disabled" : ""}>Zurueck</button>
          <button id="examMockNextPageBtn" class="ghost-btn"${page.index === pages.length - 1 ? " disabled" : ""}>Weiter</button>
          <button id="examMockFullscreenBtn" class="ghost-btn">${document.fullscreenElement ? "Vollbild verlassen" : "Vollbild"}</button>
          <button id="examMockRegenerateBtn" class="ghost-btn${state.examRequestInFlight ? " is-busy" : ""}"${state.examRequestInFlight || state.examSubmitInFlight ? " disabled" : ""}>Neue Variante</button>
          <button id="examMockSubmitBtn" class="primary-btn${state.examSubmitInFlight ? " is-busy" : ""}"${state.examSubmitInFlight || state.examRequestInFlight ? " disabled" : ""}>${state.mockEvaluation ? "Neu auswerten" : "Mock abgeben"}</button>
        </div>
        <section class="soft-panel exam-mock-page-panel">
          <div class="exam-mock-page-head">
            <div>
              <p class="exam-kicker">${escapeHtml(page.sectionLabel)}</p>
              <strong>${escapeHtml(page.sectionTitle)}</strong>
            </div>
            <div class="exam-chip-row">
              <span class="exam-chip">Seite ${escapeHtml(String(page.index + 1))}/${escapeHtml(String(pages.length))}</span>
              ${page.recommendedMinutes ? `<span class="exam-chip">${escapeHtml(String(page.recommendedMinutes))} Min.</span>` : ""}
              ${page.audioPlays ? `<span class="exam-chip">${escapeHtml(String(page.audioPlays))}x hören</span>` : ""}
              ${page.minWords ? `<span class="exam-chip">mind. ${escapeHtml(String(page.minWords))} Wörter</span>` : ""}
              <span class="exam-chip">${escapeHtml(String(page.totalPoints))} Punkte</span>
            </div>
          </div>
          ${page.instructions ? `<p>${escapeHtml(page.instructions)}</p>` : ""}
          <p class="muted">${escapeHtml(String(pageProgress.answered))}/${escapeHtml(String(pageProgress.total))} Antworten in diesem Teil.</p>
          ${mediaPanel}
          <div id="examMockQuestions" class="question-list exam-mock-question-list">
            ${page.items.map((item, itemIndex) => renderMockExamQuestionCard(item, itemIndex, evaluationMap)).join("")}
          </div>
        </section>
        ${resultSummary}
        <div id="examMockResults" class="soft-panel">${state.mockEvaluation ? "" : "Noch keine Auswertung vorhanden."}</div>
        <details class="soft-panel exam-mock-library-panel">
          <summary>Weitere Hörtexte und Mock-Medien</summary>
          ${getMockMediaSegments().length
            ? `<div class="exam-mock-library-list">${getMockMediaSegments().map((segment) => `<article class="exam-resource-card"><span class="exam-resource-type">${escapeHtml(segment.part_title)}</span><strong>${escapeHtml(segment.source_title)}</strong><span class="exam-resource-meta">${escapeHtml(String(segment.audio_plays))}x hören · ca. ${escapeHtml(String(segment.duration_hint_seconds))} Sek.</span></article>`).join("")}</div>`
            : "<p class='muted'>Keine zusätzlichen Medien für diese Variante.</p>"}
        </details>
      </div>
    </section>
  `;
};

window.getExamResourceTypeLabel = function getExamResourceTypeLabel(resourceType) {
  const labels = {
    pdf: "PDF",
    audio: "Audio",
    video: "Video",
    digital: "Digital",
    page: "Info",
    mock: "App-Mock",
  };
  if (labels[resourceType]) return labels[resourceType];
  return String(resourceType || "Quelle").toUpperCase();
};

window.renderExamResourceCards = function renderExamResourceCards(resources = [], options = {}) {
  const originLabel = options.originLabel || "Goethe-Institut";
  return resources.map((item) => `
    <a class="exam-resource-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">
      <span class="exam-resource-type">${escapeHtml(getExamResourceTypeLabel(item.resource_type))}</span>
      <strong>${escapeHtml(item.label)}</strong>
      <span class="exam-resource-meta">${escapeHtml(item.official === false ? "App-Material · nicht offiziell" : originLabel)}</span>
    </a>
  `).join("");
};

window.renderExamModuleGuide = function renderExamModuleGuide() {
  const modules = Array.isArray(state.officialExam?.modules) ? state.officialExam.modules : [];
  if (!modules.length) return "";

  return modules.map((module) => {
    const parts = (module.parts || []).map((part) => {
      const meta = [
        part.item_count ? `${escapeHtml(part.item_count)} Aufgaben` : "",
        part.points ? `${escapeHtml(part.points)} Punkte` : "",
        part.recommended_minutes ? `${escapeHtml(part.recommended_minutes)} Min.` : "",
        part.audio_plays ? `${escapeHtml(part.audio_plays)}x hören` : "",
        part.min_words ? `mind. ${escapeHtml(part.min_words)} Wörter` : "",
      ].filter(Boolean).join(" · ");
      return `<li><strong>${escapeHtml(part.title)}</strong>: ${escapeHtml(part.instructions)}${meta ? `<br /><span class="muted">${meta}</span>` : ""}</li>`;
    }).join("");

    return `
      <article class="exam-module-card">
        <strong>${escapeHtml(module.label)}</strong>
        <p>${escapeHtml(module.duration_minutes)} Min.${module.prep_minutes ? ` + ${escapeHtml(module.prep_minutes)} Min. Vorbereitung` : ""} · ${escapeHtml(module.scoring?.max_points)} Punkte · Schwelle ${escapeHtml(module.scoring?.pass_points)}</p>
        <p class="muted">${escapeHtml((module.structure || []).join(" · "))}</p>
        <ul class="simple-list">${parts}</ul>
      </article>
    `;
  }).join("");
};

window.renderExamModeStrip = function renderExamModeStrip({ kicker = "Arbeitsmodus", title = "", copy = "", metaLine = "", chips = [] } = {}) {
  const chipMarkup = (chips || []).filter(Boolean).map((item) => `<span class="exam-chip">${escapeHtml(String(item))}</span>`).join("");
  return `
    <div class="exam-mode-strip">
      <div class="exam-mode-strip-copy">
        ${kicker ? `<p class="exam-kicker">${escapeHtml(kicker)}</p>` : ""}
        <div class="exam-mode-strip-head">
          <strong>${escapeHtml(title)}</strong>
          ${chipMarkup ? `<div class="exam-chip-row">${chipMarkup}</div>` : ""}
        </div>
        ${copy ? `<p>${escapeHtml(copy)}</p>` : ""}
        ${metaLine ? `<p class="muted">${escapeHtml(metaLine)}</p>` : ""}
      </div>
    </div>
  `;
};

window.renderOfficialExamOverview = function renderOfficialExamOverview() {
  const practiceSets = state.officialExam?.practice_sets || [];
  const selectedSet = getDefaultPracticeSet();
  const selectedResource = state.selectedPracticeResourceType === "mock"
    ? { resource_type: "mock", label: "Goethe-Mock der App" }
    : getDefaultPracticeResource(selectedSet);
  const moduleSummary = (state.officialExam?.modules || [])
    .map((module) => `${module.label} · ${module.duration_minutes} Min.`)
    .join(" · ");
  const metaNotes = [state.officialExam?.official_version, state.officialExam?.pass_rule].filter(Boolean).join(" · ");

  if (els.examMeta) {
    els.examMeta.className = "exam-meta-panel";
    els.examMeta.innerHTML = `
      <div class="exam-meta-stack">
        <strong>${escapeHtml(state.officialExam?.title || "")}</strong>
        <p>${escapeHtml(state.officialExam?.official_note || "Offizielles Material des Goethe-Instituts.")}</p>
        <div class="exam-chip-row">
          <span class="exam-chip">${escapeHtml(els.globalLevel.value)}</span>
          <span class="exam-chip">${escapeHtml(els.examScope.value === "full" ? "Gesamtprüfung" : getSelectedExamLabel())}</span>
          <span class="exam-chip">${escapeHtml(String(getSelectedExamDurationMinutes()))} Min.</span>
        </div>
        ${moduleSummary ? `<p class="muted">${escapeHtml(moduleSummary)}</p>` : ""}
        ${metaNotes ? `<p class="muted">${escapeHtml(metaNotes)}</p>` : ""}
      </div>
    `;
  }
  if (els.examResults) {
    els.examResults.className = "exam-stage-summary";
    els.examResults.innerHTML = `
      <strong>${escapeHtml(selectedSet?.label || state.officialExam?.title || "Goethe-Training")}</strong>
      <p>${escapeHtml(selectedSet?.description || "Offiziellen Satz öffnen und danach bei Bedarf in die Mock-Praxis wechseln.")}</p>
    `;
  }
  if (els.examLaunchSummary) {
    els.examLaunchSummary.className = "exam-launch-summary";
  }

  const overviewResources = [
    ...(state.officialExam?.practice_page_url ? [{ label: "Offizielle Trainingsseite", url: state.officialExam.practice_page_url, resource_type: "page", official: true }] : []),
    ...((state.officialExam?.resources || []).map((item) => ({ ...item, official: item.official !== false }))),
  ];
  els.examResources.innerHTML = renderExamResourceCards(overviewResources) || "<p class='empty'>Keine Zusatzquellen gefunden.</p>";
  els.examPracticeSets.innerHTML = practiceSets.map((item) => {
    const active = item.key === state.selectedPracticeSetKey;
    const resourceKinds = [...new Set([...(item.resources || []).map((resource) => getExamResourceTypeLabel(resource.resource_type)), "App-Mock"])];
    return `
      <article class="exam-practice-card${active ? " is-active" : ""}">
        <div class="exam-practice-card-head">
          <div>
            <p class="exam-kicker">${escapeHtml(item.audience)}</p>
            <strong>${escapeHtml(item.label)}</strong>
          </div>
          ${active ? "<span class='pill'>Aktiv</span>" : ""}
        </div>
        <p>${escapeHtml(item.description || "")}</p>
        <div class="exam-chip-row">${resourceKinds.map((label) => `<span class="exam-chip">${escapeHtml(label)}</span>`).join("")}</div>
        <p class="exam-practice-meta">Startansicht: ${escapeHtml(getExamResourceTypeLabel(item.default_resource_type))}</p>
        <button class="${active ? "primary-btn" : "ghost-btn"}" data-open-practice-set="${escapeHtml(item.key)}">${active ? "Arbeitsansicht öffnen" : "Satz wählen"}</button>
      </article>
    `;
  }).join("") || "<p class='empty'>Keine offiziellen Prüfungssätze gefunden.</p>";

  els.examLaunchSummary.innerHTML = selectedSet
    ? `
      <div class="exam-summary-card">
        <p class="exam-kicker">Aktive Auswahl</p>
        <strong>${escapeHtml(selectedSet.label)} · ${escapeHtml(selectedSet.audience)}</strong>
        <p>${escapeHtml(selectedSet.description || "")}</p>
        <div class="exam-chip-row">${(selectedSet.resources || []).map((item) => `<span class="exam-chip">${escapeHtml(getExamResourceTypeLabel(item.resource_type))}</span>`).join("")}<span class="exam-chip">App-Mock</span></div>
        <p class="muted">Startansicht: ${escapeHtml(selectedResource?.label || getExamResourceTypeLabel(selectedResource?.resource_type))}</p>
        <p class="muted">Zuerst das offizielle Material öffnen, danach bei Bedarf zur Mock-Praxis wechseln.</p>
      </div>
    `
    : "<p class='muted'>Kein offizieller Prüfungssatz verfügbar.</p>";
  renderPausedExamSessionPanel();
};

window.renderMockExamWorkspace = function renderMockExamWorkspace() {
  const practiceSet = getDefaultPracticeSet();
  const currentExamMatchesSelection = Boolean(state.exam && state.exam.mock_signature === currentMockSignature());
  const validationNote = (state.exam?.validation_notes || [])[0] || "";
  const calibrationLabel = state.exam?.module_brief_used ? "Mit lokalem Modulbrief kalibriert" : "";
  const moduleGuide = renderExamModuleGuide();
  if (els.examWorkspaceGuide) {
    els.examWorkspaceGuide.className = "exam-guide-strip";
    els.examWorkspaceGuide.innerHTML = `
      ${renderExamModeStrip({
        kicker: "Mock-Praxis",
        title: "AI-Mock · nicht offiziell",
        copy: currentExamMatchesSelection
          ? "Zusätzliche Trainingsvariante im offiziellen Rahmen. Der offizielle Satz bleibt separat erhalten."
          : "Der Mock wird erst nach Ihrem Klick erzeugt und bleibt klar vom offiziellen Material getrennt.",
        metaLine: currentExamMatchesSelection
          ? ([state.exam?.source_framework, state.exam?.generator_version, calibrationLabel, validationNote || state.exam?.validation_notes].filter(Boolean).join(" · ") || "Blueprint-basierter Mock")
          : "Startet nur auf Anforderung",
        chips: [
          practiceSet?.label || "Goethe-Mock der App",
          currentExamMatchesSelection ? `Seed ${state.exam?.variant_seed || "n/a"}` : "Noch nicht erzeugt",
          currentExamMatchesSelection ? (state.exam?.generation_mode || "mock") : "Bereit",
          currentExamMatchesSelection && state.exam?.generation_elapsed_ms ? formatMockGenerationDuration(state.exam.generation_elapsed_ms) : "",
        ],
      })}
      ${moduleGuide ? `<div class="exam-module-guide exam-module-guide-inline" hidden>${moduleGuide}</div>` : ""}
    `;
  }
  els.examWorkspaceBody.innerHTML = currentExamMatchesSelection
    ? renderMockExamSessionShell()
    : renderMockExamPreparationPanel();
  refreshMockMediaPackControls();
  bindMockMediaPlayers();
  refreshMockAudioVoiceUi();
  const mockQuestions = document.getElementById("examMockQuestions");
  if (mockQuestions) {
    if (state.mockDraftKey === currentMockDraftKey()) applyAnswerDrafts(mockQuestions, state.mockDraftAnswers);
  }
  if (state.mockEvaluation) {
    const finalTarget = document.getElementById("examMockResults");
    if (finalTarget) renderEvaluation(finalTarget, getFilteredMockEvaluationPayload());
  }
  restoreExamWorkspaceViewport();
};

window.getEmbeddedOfficialResourceUrl = function getEmbeddedOfficialResourceUrl(resource) {
  if (!resource?.url) return "";
  if (resource.resource_type === "pdf") return `/api/exam/resource?url=${encodeURIComponent(resource.url)}`;
  return resource.url;
};

window.renderExamWorkspace = function renderExamWorkspace() {
  if (typeof window.stopMockMediaPlayers === "function") stopMockMediaPlayers(true);
  if (typeof window.stopMockExamSpeech === "function") stopMockExamSpeech({ message: "", forceStatus: false });
  const practiceSet = getDefaultPracticeSet();
  const selectedModule = getSelectedExamLabel();
  const selectedDuration = getSelectedExamDurationMinutes();
  const isMock = state.selectedPracticeResourceType === "mock";
  const resource = isMock ? null : getDefaultPracticeResource(practiceSet);
  const officialResources = practiceSet?.resources || [];
  const companionCards = renderExamResourceCards(
    isMock
      ? officialResources
      : officialResources.filter((item) => item.resource_type !== resource?.resource_type || item.url !== resource?.url)
  );
  const companionBlock = companionCards ? `<div class="exam-resource-grid exam-resource-grid-inline">${companionCards}</div>` : "";
  const officialModeChips = [
    selectedModule,
    `${String(selectedDuration)} Min.`,
    practiceSet?.audience || "",
    resource?.label || "",
  ].filter(Boolean);
  const mockSummary = isMock && state.exam
    ? `Seed ${state.exam.variant_seed || "n/a"} · ${state.exam.generation_mode || "mock"}${state.exam.generation_elapsed_ms ? ` · ${formatMockGenerationDuration(state.exam.generation_elapsed_ms)}` : ""}`
    : "Zusätzliche KI-Variante, klar getrennt vom offiziellen Material.";

  if (els.examWorkspaceMeta) {
    els.examWorkspaceMeta.className = "exam-workspace-meta";
    els.examWorkspaceMeta.innerHTML = `
      <strong>${escapeHtml(state.officialExam?.title || "")}</strong>
      <div class="exam-chip-row">
        <span class="exam-chip">${escapeHtml(selectedModule)}</span>
        <span class="exam-chip">${escapeHtml(String(selectedDuration))} Min.</span>
        ${practiceSet ? `<span class="exam-chip">${escapeHtml(practiceSet.audience)}</span>` : ""}
      </div>
      <p class="muted">${escapeHtml(state.officialExam?.pass_rule || "")}</p>
    `;
  }

  els.examWorkspaceSets.innerHTML = (state.officialExam?.practice_sets || []).map((item) => `
    <button class="exam-choice-btn${item.key === state.selectedPracticeSetKey ? " is-active" : ""}" data-practice-set="${escapeHtml(item.key)}">
      <span class="exam-choice-kicker">Satz</span>
      <strong>${escapeHtml(item.label)}</strong>
      <span class="exam-choice-meta">${escapeHtml(item.audience)} · ${escapeHtml(String((item.resources || []).length))} Ansichten</span>
    </button>
  `).join("");
  els.examWorkspaceAssets.innerHTML = ((practiceSet?.resources || []).map((item) => `
    <button class="exam-choice-btn exam-choice-btn-compact${item.resource_type === state.selectedPracticeResourceType ? " is-active" : ""}" data-practice-resource="${escapeHtml(item.resource_type)}">
      <span class="exam-choice-kicker">${escapeHtml(getExamResourceTypeLabel(item.resource_type))}</span>
      <strong>${escapeHtml(item.label)}</strong>
    </button>
  `)).join("");
  els.examWorkspaceMock.innerHTML = `
    <button class="exam-choice-btn exam-choice-btn-compact exam-choice-btn-mock${isMock ? " is-active" : ""}" data-practice-resource="mock">
      <span class="exam-choice-kicker">Mock-Praxis</span>
      <strong>Goethe-Mock der App</strong>
      <span class="exam-choice-meta">${escapeHtml(isMock ? "Aktive Mock-Ansicht" : "Zusätzliche Trainingsvariante.")}</span>
    </button>
    <article class="list-item exam-choice-btn-mock-note">
      <strong>${isMock ? "Aktuelle Variante" : "Mock-Logik"}</strong>
      <p>${escapeHtml(mockSummary)}</p>
    </article>
  `;

  if (els.examWorkspaceGuide) {
    els.examWorkspaceGuide.className = "exam-guide-strip";
    els.examWorkspaceGuide.innerHTML = isMock
      ? renderExamModeStrip({
        kicker: "Mock-Praxis",
        title: "AI-Mock · nicht offiziell",
        copy: "Zusätzliche Trainingsvariante, klar getrennt vom offiziellen Satz.",
        metaLine: state.exam?.source_framework || "Blueprint-basierter Mock",
        chips: [
          practiceSet?.label || "Goethe-Mock",
          `Seed ${state.exam?.variant_seed || "wird geladen"}`,
          state.exam?.generation_mode || "mock",
        ],
      })
      : renderExamModeStrip({
        kicker: "Offizielles Material",
        title: "Originaler Trainingssatz",
        copy: "PDF, Audio oder digitale Version direkt in dieser Arbeitsansicht.",
        metaLine: state.officialExam?.official_version || state.officialExam?.official_note || "",
        chips: officialModeChips,
      });
  }

  els.examWorkspaceTitle.textContent = isMock
    ? (practiceSet ? `${practiceSet.label} · ${practiceSet.audience}` : `${state.officialExam?.title || "Goethe-Mock"} · Arbeitsansicht`)
    : (practiceSet ? `${practiceSet.label} · ${practiceSet.audience}` : "Kein offizieller Prüfungssatz");
  els.examWorkspaceSubtitle.textContent = isMock ? `Goethe-Mock der App · ${selectedModule}` : `${resource?.label || "Quelle"} · ${selectedModule}`;
  els.examWorkspaceOpenSource.href = (isMock ? state.officialExam?.practice_page_url : resource?.url) || "#";
  els.examWorkspaceOpenSource.textContent = isMock ? "Offizielle Referenz öffnen" : "Original öffnen";
  els.examWorkspaceOpenSource.classList.toggle("hidden", !(els.examWorkspaceOpenSource.href && els.examWorkspaceOpenSource.href !== "#"));

  if (isMock) {
    renderMockExamWorkspace();
    return;
  }

  if (!practiceSet || !resource) {
    els.examWorkspaceBody.innerHTML = "<div class='exam-inline-note'>Für dieses Niveau konnte kein offizieller Prüfungssatz geladen werden.</div>";
    restoreExamWorkspaceViewport();
    return;
  }

  if (resource.resource_type === "audio") {
    els.examWorkspaceBody.innerHTML = `
      <div class="exam-inline-note"><strong>${escapeHtml(resource.label)}</strong><span>Parallel zur PDF oder Digitalansicht nutzen.</span></div>
      <div class="exam-viewer exam-media-viewer"><audio class="exam-media-player" controls preload="metadata" src="${escapeHtml(resource.url)}"></audio></div>
      ${companionBlock}
    `;
    restoreExamWorkspaceViewport();
    return;
  }
  if (resource.resource_type === "video") {
    els.examWorkspaceBody.innerHTML = `
      <div class="exam-inline-note"><strong>${escapeHtml(resource.label)}</strong><span>Offizielle Hördatei direkt in der Arbeitsfläche.</span></div>
      <div class="exam-viewer exam-media-viewer"><video class="exam-media-player" controls preload="metadata" src="${escapeHtml(resource.url)}"></video></div>
      ${companionBlock}
    `;
    restoreExamWorkspaceViewport();
    return;
  }
  if (resource.resource_type === "pdf") {
    const pdfUrl = getEmbeddedOfficialResourceUrl(resource);
    els.examWorkspaceBody.innerHTML = `
      <div class="exam-inline-note"><strong>${escapeHtml(resource.label)}</strong><span>PDF direkt in der Arbeitsfläche. Wenn die Vorschau leer bleibt, öffnen Sie die Datei im neuen Tab.</span></div>
      <div class="inline-actions exam-viewer-launch-actions">
        <a class="ghost-btn" href="${escapeHtml(pdfUrl)}" target="_blank" rel="noreferrer">PDF im neuen Tab</a>
      </div>
      <div class="exam-viewer exam-document-viewer">
        <iframe
          title="${escapeHtml(resource.label)}"
          src="${escapeHtml(pdfUrl)}#toolbar=1&navpanes=0&view=FitH"
          loading="eager"
          referrerpolicy="no-referrer-when-downgrade"
        ></iframe>
      </div>
      ${companionBlock}
    `;
    restoreExamWorkspaceViewport();
    return;
  }
  const frameUrl = getEmbeddedOfficialResourceUrl(resource);
  els.examWorkspaceBody.innerHTML = `
    <div class="exam-inline-note"><strong>${escapeHtml(resource.label)}</strong><span>Originalmaterial direkt in der Arbeitsfläche.</span></div>
    <div class="exam-viewer"><iframe title="${escapeHtml(resource.label)}" src="${escapeHtml(frameUrl)}" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>
    ${companionBlock}
  `;
  restoreExamWorkspaceViewport();
};

window.openOfficialExamWorkspace = function openOfficialExamWorkspace(setKey, options = {}) {
  if (setKey) state.selectedPracticeSetKey = setKey;
  syncPracticeSelection();
  state.examMode = state.selectedPracticeResourceType === "mock" ? "mock" : "official";
  state.restoreExamViewport = options.restoreViewport === true;
  state.examWorkspaceActive = true;
  const timerContextKey = currentExamTimerContextKey();
  const resumePausedTimer = state.examTimerPaused && state.examTimerContextKey === timerContextKey && state.examRemainingMs > 0;
  const restoreActiveTimer = options.restoreTimer && !state.examTimerPaused && typeof state.examEndsAt === "number";
  const nextEndsAt = resumePausedTimer
    ? Date.now() + state.examRemainingMs
    : (restoreActiveTimer ? state.examEndsAt : null);
  startExamTimer(getSelectedExamDurationMinutes(), nextEndsAt, timerContextKey);
  renderExamWorkspace();
  persistExamUiPreferences();
  renderPausedExamSessionPanel();
  if (options.smoothScroll === false) return;
  window.scrollTo({ top: 0, behavior: "smooth" });
};

window.loadOfficialExam = async function loadOfficialExam() {
  setAppBusyBanner("Offizielle Goethe-Ansicht wird geladen ...");
  // Legacy test contract:
  // startExamTimer(getSelectedExamDurationMinutes(), null, currentExamTimerContextKey())
  try {
    state.officialExam = await apiFetch("/api/exam/official", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      timeoutMs: 15000,
      body: JSON.stringify({ level: els.globalLevel.value, scope: els.examScope.value, module: els.examModule.value }),
    });
    syncPracticeSelection();
    renderOfficialExamOverview();
    renderExamWorkspace();
  } finally {
    setAppBusyBanner("");
  }
};

window.generateExam = async function generateExam() {
  selectOfficialPracticeResource(state.selectedPracticeSetKey);
  openOfficialExamWorkspace(state.selectedPracticeSetKey);
};

window.submitExam = async function submitExam() {
  if (!state.exam || state.examSubmitInFlight || state.examRequestInFlight) return;
  const answersContainer = document.getElementById("examMockQuestions");
  if (!answersContainer) return;
  const { blankCount, totalCount } = getExamSubmissionRisk();
  if (blankCount > 0) {
    const confirmed = await openConfirmModal({
      title: "Mock unvollständig auswerten?", // legacy: Mock unvollstaendig auswerten?
      message: `Noch ${blankCount} von ${totalCount} Antworten sind leer. Wirklich trotzdem Goethe-aligned auswerten?`,
      confirmLabel: "Trotzdem auswerten",
      cancelLabel: "Weiter bearbeiten",
    });
    if (!confirmed) return;
  }
  state.examSubmitInFlight = true;
  state.mockEvaluation = null;
  let evaluationPayload = null;
  const submittedAnswers = getMockExamAnswers();
  const resultTarget = document.getElementById("examMockResults") || els.examResults;
  if (resultTarget) {
    resultTarget.innerHTML = "<strong>Goethe-aligned Auswertung läuft ...</strong><p>Die Antworten werden jetzt nach offizieller Struktur und produktiver Trainingsrubrik ausgewertet.</p>";
  }
  renderMockExamWorkspace();
  setAppBusyBanner("Goethe-aligned Auswertung läuft ...", "warning");
  try {
    evaluationPayload = await apiFetch("/api/exam/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      timeoutMs: 30000,
      body: JSON.stringify({
        exercise_id: state.exam.exercise_id,
        answers: submittedAnswers,
        explanation_language: state.settings?.explanation_language || "es",
      }),
    });
    state.mockEvaluation = evaluationPayload;
    const finalTarget = document.getElementById("examMockResults") || els.examResults;
    renderEvaluation(finalTarget, getFilteredMockEvaluationPayload());
    els.examResults.innerHTML = `<strong>Goethe-Mock ausgewertet</strong><p>${escapeHtml(evaluationPayload.percent)}% · ${escapeHtml(evaluationPayload.summary)}</p>`;
    pushAppToast(`Goethe-Mock ausgewertet: ${evaluationPayload.percent}%`, "success");
    refreshProgress();
    loadExamHistory();
  } catch (error) {
    pushAppToast(error.message || "Die Auswertung ist fehlgeschlagen.", "error", 4200);
    throw error;
  } finally {
    state.examSubmitInFlight = false;
    setAppBusyBanner("");
    if (state.selectedPracticeResourceType === "mock" && state.exam) {
      renderMockExamWorkspace();
      if (evaluationPayload) {
        const finalTarget = document.getElementById("examMockResults") || els.examResults;
        renderEvaluation(finalTarget, getFilteredMockEvaluationPayload());
      }
    }
  }
};

window.bindEvents = function bindEvents() {
  els.primaryNavButtons.forEach((btn) => btn.addEventListener("click", () => openPrimaryTab(btn.dataset.primaryTab)));
  els.tabs.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));
  els.openSettingsBtn?.addEventListener("click", () => openPrimaryTab("profile"));
  els.homeOpenWorkspaceBtn?.addEventListener("click", () => openPrimaryTab("workspace"));
  [els.homeMissionActions, els.homeQuickStart, els.homeCoachBrief].forEach((container) => {
    container?.addEventListener("click", (event) => {
      const primaryButton = event.target.closest("[data-open-primary]");
      if (primaryButton) {
        openPrimaryTab(primaryButton.dataset.openPrimary);
        return;
      }
      const legacyButton = event.target.closest("[data-open-tab]");
      if (legacyButton) {
        switchTab(legacyButton.dataset.openTab);
        return;
      }
      const recommendationButton = event.target.closest("[data-start-recommendation]");
      if (recommendationButton && state.progressOverview?.recommendation_event_id) {
        activateRecommendationLaunch({
          recommendationEventId: state.progressOverview.recommendation_event_id,
          recommendationStrategy: state.progressOverview.recommendation_strategy || "",
          recommendedScope: state.progressOverview.recommended_exam_scope || "full",
          priorityModule: state.progressOverview.priority_module || "",
          source: "home_mission",
        });
      }
    });
  });
  els.chatTtsBtn.addEventListener("click", toggleChatTts);
  els.chatReplayBtn?.addEventListener("click", repeatLastChatReply);
  els.chatVoiceGender?.addEventListener("change", () => {
    state.chatVoiceGender = els.chatVoiceGender.value;
    applyTutorAvatarPreference();
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });
  els.chatVoiceVariant?.addEventListener("change", () => {
    state.chatVoiceVariant = els.chatVoiceVariant.value;
    const regionalOptions = getChatRegionalVoiceOptions();
    if (state.chatVoiceVariant !== "regional" || !regionalOptions.length) {
      state.chatVoiceVariant = "standard";
      state.chatVoiceRegion = "de-DE";
    } else if (!regionalOptions.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = regionalOptions[0].value;
    }
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });
  els.chatVoiceRegion?.addEventListener("change", () => {
    state.chatVoiceRegion = els.chatVoiceRegion.value || "de-DE";
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });
  els.chatSendBtn.addEventListener("click", sendChat);
  els.chatInterruptBtn?.addEventListener("click", () => window.interruptTutorStream?.());
  els.chatFinishBtn.addEventListener("click", finishChat);
  els.chatLoadHistoryBtn.addEventListener("click", loadSelectedConversation);
  els.chatNewBtn.addEventListener("click", requestChatReset);
  els.chatMicBtn.addEventListener("click", () => toggleVoiceInput("chat"));
  els.chatMessages.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chat-action]");
    if (!button) return;
    const action = String(button.dataset.chatAction || "").trim();
    const entryId = String(button.dataset.entryId || "").trim();
    if (!action || !entryId) return;

    if (action === "edit") {
      beginChatEntryEdit(entryId);
      return;
    }
    if (action === "cancel-edit") {
      cancelChatEntryEdit();
      return;
    }
    if (action === "save-edit") {
      saveChatEntryEdit(entryId).catch((error) => {
        setChatStatus(error.message || "Nachricht konnte nicht bearbeitet werden.", "error");
      });
      return;
    }
    if (action === "versions") {
      openChatVersions(entryId).catch((error) => {
        setChatStatus(error.message || "Versionen konnten nicht geladen werden.", "error");
      });
      return;
    }
    if (action === "close-versions") {
      closeChatVersions();
      return;
    }
    if (action === "restore-version") {
      const restoreFromEntryId = String(button.dataset.restoreEntryId || "").trim();
      if (!restoreFromEntryId) return;
      restoreChatEntryVersion(entryId, restoreFromEntryId).catch((error) => {
        setChatStatus(error.message || "Version konnte nicht wiederhergestellt werden.", "error");
      });
    }
  });
  els.chatMessages.addEventListener("keydown", (event) => {
    const textarea = event.target.closest("[data-chat-edit-input]");
    if (!textarea) return;
    const entryId = String(textarea.dataset.chatEditInput || "").trim();
    if (!entryId) return;
    if (event.key === "Escape") {
      event.preventDefault();
      cancelChatEntryEdit();
      return;
    }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      saveChatEntryEdit(entryId).catch((error) => {
        setChatStatus(error.message || "Nachricht konnte nicht bearbeitet werden.", "error");
      });
    }
  });
  els.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });
  els.examScope.addEventListener("change", () => {
    syncExamScopeUi();
    persistExamUiPreferences();
    renderPausedExamSessionPanel();
    loadOfficialExam();
  });
  els.examModule.addEventListener("change", () => {
    state.lastExamModuleUsed = els.examModule.value;
    persistExamUiPreferences();
    renderPausedExamSessionPanel();
    loadOfficialExam();
  });
  els.examGenerateBtn.addEventListener("click", generateExam);
  els.examResumePausedBtn.addEventListener("click", resumePausedExamSession);
  els.examRestartPausedBtn.addEventListener("click", restartExamSessionFromHub);
  els.examHistoryBtn.addEventListener("click", loadExamHistory);
  els.examWorkspaceCloseBtn.addEventListener("click", closeOfficialExamWorkspace);
  els.examWorkspaceChangeBtn.addEventListener("click", closeOfficialExamWorkspace);
  els.examPracticeSets.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-practice-set]");
    if (!button) return;
    state.selectedPracticeSetKey = button.dataset.openPracticeSet;
    state.selectedPracticeResourceType = null;
    syncPracticeSelection();
    renderOfficialExamOverview();
    openOfficialExamWorkspace(button.dataset.openPracticeSet);
  });
  els.examWorkspaceSets.addEventListener("click", (event) => {
    const button = event.target.closest("[data-practice-set]");
    if (!button) return;
    const applyChange = async () => {
      if (state.selectedPracticeResourceType === "mock" && hasStartedMockDraft() && button.dataset.practiceSet !== state.selectedPracticeSetKey) {
        const confirmed = await confirmExamContextSwitch(
          "Sie wechseln zu einem anderen offiziellen Satz. Ihr aktueller Mock-Stand bleibt pausiert. Wirklich wechseln?",
          "Satz wechseln",
        );
        if (!confirmed) return;
      }
      state.selectedPracticeSetKey = button.dataset.practiceSet;
      syncPracticeSelection();
      renderOfficialExamOverview();
      renderExamWorkspace();
    };
    applyChange().catch((error) => pushAppToast(error.message || "Satzwechsel fehlgeschlagen.", "error", 4200));
  });
  els.examWorkspaceAssets.addEventListener("click", (event) => {
    const button = event.target.closest("[data-practice-resource]");
    if (!button) return;
    const applyChange = async () => {
      if (state.selectedPracticeResourceType === "mock" && button.dataset.practiceResource !== "mock" && hasStartedMockDraft()) {
        const confirmed = await confirmExamContextSwitch(
          "Sie verlassen die laufende Mock-Ansicht fuer offizielles Material. Ihr Mock-Stand bleibt pausiert. Wirklich wechseln?",
          "Zur offiziellen Ansicht",
        );
        if (!confirmed) return;
      }
      state.selectedPracticeResourceType = button.dataset.practiceResource;
      persistExamUiPreferences();
      renderOfficialExamOverview();
      renderExamWorkspace();
    };
    applyChange().catch((error) => pushAppToast(error.message || "Ansicht konnte nicht gewechselt werden.", "error", 4200));
  });
  els.examWorkspaceMock.addEventListener("click", (event) => {
    const button = event.target.closest("[data-practice-resource]");
    if (!button) return;
    state.selectedPracticeResourceType = button.dataset.practiceResource;
    persistExamUiPreferences();
    renderOfficialExamOverview();
    renderExamWorkspace();
  });
  els.examWorkspaceBody.addEventListener("click", async (event) => {
    const playMediaButton = event.target.closest("[data-play-mock-media]");
    if (playMediaButton) {
      playMockExamMediaSegment(playMediaButton.dataset.playMockMedia);
      return;
    }
    const stopMediaButton = event.target.closest("[data-stop-mock-media]");
    if (stopMediaButton) {
      stopMockExamSpeech({ message: "Hörtext gestoppt.", tone: "warning", forceStatus: true });
      return;
    }
    const generateButton = event.target.closest("#examMockGenerateBtn");
    if (generateButton) {
      await loadMockExam(generateButton.dataset.forceRegenerate === "1");
      renderMockExamWorkspace();
      return;
    }
    const resumeButton = event.target.closest("#examMockResumeBtn");
    if (resumeButton) {
      renderMockExamWorkspace();
      return;
    }
    const pageButton = event.target.closest("[data-mock-page-index]");
    if (pageButton) {
      setMockExamPageIndex(Number(pageButton.dataset.mockPageIndex || 0));
      return;
    }
    const prevPageButton = event.target.closest("#examMockPrevPageBtn");
    if (prevPageButton) {
      setMockExamPageIndex((state.mockExamPageIndex || 0) - 1);
      return;
    }
    const nextPageButton = event.target.closest("#examMockNextPageBtn");
    if (nextPageButton) {
      setMockExamPageIndex((state.mockExamPageIndex || 0) + 1);
      return;
    }
    const reviewFilterButton = event.target.closest("[data-mock-review-filter]");
    if (reviewFilterButton) {
      setMockReviewFilter(reviewFilterButton.dataset.mockReviewFilter || "all");
      return;
    }
    const reviewJumpButton = event.target.closest("[data-mock-review-jump]");
    if (reviewJumpButton) {
      jumpToMockReviewTarget(reviewJumpButton.dataset.mockReviewJump || "problem");
      return;
    }
    const fullscreenButton = event.target.closest("#examMockFullscreenBtn");
    if (fullscreenButton) {
      await toggleMockExamFullscreen();
      return;
    }
    const regenerateButton = event.target.closest("#examMockRegenerateBtn");
    if (regenerateButton) {
      if (hasStartedMockDraft()) {
        const confirmed = await openConfirmModal({
          title: "Mock-Antworten verwerfen?",
          message: "Ihre aktuellen Antworten in diesem Mock werden verworfen. Wirklich eine neue Variante laden?",
          confirmLabel: "Neuen Mock laden",
          cancelLabel: "Abbrechen",
        });
        if (!confirmed) return;
      }
      await loadMockExam(true);
      renderMockExamWorkspace();
      return;
    }
    const submitButton = event.target.closest("#examMockSubmitBtn");
    if (submitButton) {
      await submitExam();
    }
  });
  els.examWorkspaceBody.addEventListener("change", async (event) => {
    const mockVoiceSelect = event.target.closest("#mockAudioVoiceGenderSelect");
    if (!mockVoiceSelect) return;
    await updateMockAudioVoicePreference(mockVoiceSelect.value);
  });
  const persistMockDraftFromEvent = (event) => {
    if (event.target.closest("[data-answer-input]")) {
      if (state.mockEvaluation) {
        state.mockEvaluation = null;
        state.mockReviewFilter = "all";
      }
      persistCurrentMockDraft();
      scheduleExamWorkspaceViewportPersist(event.target);
    }
  };
  els.examWorkspaceBody.addEventListener("input", persistMockDraftFromEvent);
  els.examWorkspaceBody.addEventListener("change", persistMockDraftFromEvent);
  els.examWorkspaceBody.addEventListener("focusin", (event) => scheduleExamWorkspaceViewportPersist(event.target));
  window.addEventListener("scroll", () => scheduleExamWorkspaceViewportPersist(), { passive: true });
  window.addEventListener("beforeunload", () => persistExamWorkspaceViewport());
  document.addEventListener("fullscreenchange", () => {
    state.mockExamFullscreen = Boolean(document.fullscreenElement);
    els.examWorkspace?.classList.toggle("is-fullscreen", state.mockExamFullscreen);
    if (state.selectedPracticeResourceType === "mock" && !els.examWorkspace.classList.contains("hidden")) {
      captureMockDraftAnswers();
      renderMockExamWorkspace();
    }
  });
  els.placementStartBtn.addEventListener("click", requestPlacementStart);
  els.placementSubmitBtn.addEventListener("click", submitPlacement);
  els.roadmapGenerateBtn.addEventListener("click", generateRoadmap);
  els.roadmapActivateBtn.addEventListener("click", activateRoadmap);
  els.grammarTopicSelect.addEventListener("change", () => loadGrammarTheory(els.grammarTopicSelect.value));
  els.grammarGenerateBtn.addEventListener("click", requestGrammarGenerate);
  els.grammarSubmitBtn.addEventListener("click", submitGrammar);
  els.writingPromptBtn.addEventListener("click", requestWritingPrompt);
  els.writingGradeBtn.addEventListener("click", gradeWriting);
  els.speakingStartBtn.addEventListener("click", requestSpeakingStart);
  els.speakingSendBtn.addEventListener("click", sendSpeakingTurn);
  els.speakingMicBtn.addEventListener("click", () => toggleVoiceInput("speaking"));
  els.vocabGenerateBtn.addEventListener("click", requestVocabGenerate);
  els.vocabCreateDeckBtn.addEventListener("click", importSelectedVocab);
  els.vocabTable.addEventListener("change", (event) => {
    const target = event.target;
    if (!target.matches("[data-vocab-id]")) return;
    if (target.checked) state.selectedVocabIds.add(target.dataset.vocabId);
    else state.selectedVocabIds.delete(target.dataset.vocabId);
  });
  els.deckCreateBtn.addEventListener("click", createDeck);
  els.decksRefreshBtn.addEventListener("click", refreshDecks);
  els.reviewNextBtn.addEventListener("click", requestNextReviewCard);
  els.reviewFlipBtn.addEventListener("click", flipReviewCard);
  els.rateButtons.forEach((btn) => btn.addEventListener("click", () => gradeReview(Number(btn.dataset.quality))));
  els.progressRefreshBtn.addEventListener("click", refreshProgress);
  els.progressRoadmap.addEventListener("click", (event) => {
    const button = event.target.closest("[data-use-recommendation]");
    if (button) useDisplayedRecommendation(button);
  });
  els.settingsSaveBtn.addEventListener("click", saveSettings);
  els.settingsMockAudioVoiceGender?.addEventListener("change", async () => {
    await updateMockAudioVoicePreference(els.settingsMockAudioVoiceGender.value);
  });
  els.uiLanguageSelect.addEventListener("change", () => {
    if (state.settings) {
      state.settings.interface_language = els.uiLanguageSelect.value;
      applyLanguage();
    }
  });
  els.starterDeckList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-import-starter]");
    if (button) importStarterDeck(button.dataset.importStarter);
  });
  els.deckList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-select-deck]");
    if (button) requestReviewDeckSelection(button.dataset.selectDeck);
  });
  els.reviewDeckSelect.addEventListener("change", () => requestReviewDeckSelection(els.reviewDeckSelect.value));
  els.globalLevel.addEventListener("change", () => {
    applyLevelTheme();
    persistExamUiPreferences();
    renderPausedExamSessionPanel();
    loadOfficialExam();
  });
  if (typeof window.bindExamRailResize === "function") {
    window.bindExamRailResize();
  }
};

window.initApp = async function initApp() {
  restoreUiPreferences();
  applyLevelTheme();
  refreshMockAudioVoiceUi();
  bindEvents();
  bindChatTtsVoices();
  resetChat();
  applyTutorAvatarPreference();
  refreshChatTtsUi();
  syncExamScopeUi();
  try {
    await Promise.all([loadSettings(), loadConfig()]);
    refreshVoiceInputButtons();
    updateChatComposerState();
    refreshHeroMetrics();
    await Promise.all([
      refreshChatHistory(),
      loadOfficialExam(),
      loadExamHistory(),
      loadMockExamHealth(),
      loadPlacementHistory(),
      loadGrammarCatalog(),
      refreshStarterDecks(),
      refreshDecks(),
      refreshProgress(),
    ]);
    if (state.restoreExamWorkspace) {
      switchTab("exams");
      const pausedMockSession = state.pausedExamSession?.selectedPracticeResourceType === "mock" && state.examTimerPaused;
      if (!pausedMockSession) selectOfficialPracticeResource(state.selectedPracticeSetKey);
      openOfficialExamWorkspace(state.selectedPracticeSetKey, { restoreTimer: true, restoreViewport: true, smoothScroll: false });
      state.restoreExamWorkspace = false;
    }
    renderPausedExamSessionPanel();
    const activeRoadmap = await apiFetch("/api/roadmap/current");
    if (activeRoadmap) renderRoadmap(activeRoadmap, els.roadmapCurrent);
    if (typeof window.renderHome === "function") window.renderHome();
    if (typeof window.renderReviewOverview === "function") window.renderReviewOverview();
    if (typeof window.syncPrimaryNavigation === "function") window.syncPrimaryNavigation();
  } catch (error) {
    setStatus("Start mit Hinweis: Einige Inhalte konnten nicht geladen werden.");
  }
};

window.renderHome = function renderHome() {
  if (!els.homeMissionCard) return;
  const overview = state.progressOverview || {};
  const mistakes = state.progressMistakes || [];
  const dueDecks = [...(state.decks || [])]
    .filter((deck) => Number(deck.due_cards || 0) > 0)
    .sort((left, right) => Number(right.due_cards || 0) - Number(left.due_cards || 0));
  const recentConversation = (state.chatHistoryItems || [])[0] || null;
  const recommendationScopeLabel = overview.recommended_exam_scope === "module" ? "Modulfokus" : "Gesamtprüfung";
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "Prüfung";
  const probability = overview.full_exam_probability?.probability_percent;
  const activeRoadmap = overview.active_roadmap || null;
  const dueCards = Number(overview.due_flashcards || 0);
  const streakDays = Number(overview.streak_days || 0);
  const dueDeckSummary = dueDecks.length
    ? dueDecks.slice(0, 2).map((deck) => `${deck.name} (${deck.due_cards})`).join(" · ")
    : "Keine fälligen Decks.";
  const topMistake = mistakes[0]
    ? `${mistakes[0].label}${mistakes[0].example ? ` · ${mistakes[0].example}` : ""}`
    : "Noch kein wiederkehrendes Fehlermuster.";
  const roadmapSummary = activeRoadmap
    ? `${activeRoadmap.target_exam} · ${activeRoadmap.target_level}`
    : "Kein aktiver Lernplan";
  const missionProgress = probability == null
    ? Math.min(84, 28 + (dueCards * 4))
    : Math.min(100, Math.max(18, Number(probability) || 0));
  const coachBrief = [
    {
      label: "Heuristisches Übungssignal",
      value: probability == null ? "Im Aufbau" : `${probability}%`,
      copy: probability == null ? "Noch keine Prüfungsdaten auf dem Zielniveau." : "Heuristische Einschätzung; keine validierte Prüfungsprognose.",
    },
    {
      label: "Nächster Fokus",
      value: priorityModuleLabel,
      copy: (overview.weak_skills || []).length
        ? (overview.weak_skills || []).slice(0, 3).map((item) => `${skillLabels[item.skill] || item.skill} ${item.average_percent}%`).join(" · ")
        : dueDeckSummary,
    },
    {
      label: "Plan und Verlauf",
      value: activeRoadmap ? "Lernplan aktiv" : (recentConversation ? `${recentConversation.turns} Züge` : "Noch keine Sitzung"),
      copy: activeRoadmap ? roadmapSummary : (recentConversation ? recentConversation.preview : topMistake),
    },
    {
      label: "Wiederholung",
      value: `${dueCards}`,
      copy: dueDeckSummary,
    },
  ];

  if (els.homeMissionActions) {
    els.homeMissionActions.innerHTML = `
      ${overview.recommendation_event_id ? `<button class="primary-btn" type="button" data-start-recommendation="1">Tagesmission starten</button>` : `<button class="primary-btn" type="button" data-open-primary="tutor">Tutor öffnen</button>`}
      <button class="ghost-btn" type="button" data-open-primary="review">Review</button>
      <button class="ghost-btn" type="button" data-open-tab="progress">Fortschritt</button>
    `;
  }

  els.homeMissionCard.innerHTML = `
    <p class="home-card-kicker">Heute</p>
    <strong class="home-mission-title">${escapeHtml(overview.exam_readiness || "Mit einer kompakten, fokussierten Einheit Schwung aufbauen.")}</strong>
    <p class="home-mission-copy">${escapeHtml(overview.next_session?.action || "Mit Tutor oder Review starten und danach gezielt in den passenden Arbeitsbereich wechseln.")}</p>
    <div class="home-mission-progress">
      <div class="home-progress-bar" aria-hidden="true"><span style="width:${escapeHtml(String(missionProgress))}%"></span></div>
      <p>${probability == null ? "Das Signal wird mit weiterer bewerteter Arbeit präziser." : `${escapeHtml(String(probability))}% aktuelles Gesamtsignal.`}</p>
    </div>
    <div class="home-mission-stats">
      <article>
        <span>Serie</span>
        <strong>${escapeHtml(String(streakDays))}d</strong>
      </article>
      <article>
        <span>Fällig</span>
        <strong>${escapeHtml(String(dueCards))}</strong>
      </article>
      <article>
        <span>Fokus</span>
        <strong>${escapeHtml(priorityModuleLabel)}</strong>
      </article>
    </div>
    <div class="home-chip-row">
      <span class="home-chip">${escapeHtml(recommendationScopeLabel)}</span>
      <span class="home-chip">${escapeHtml(priorityModuleLabel)}</span>
      <span class="home-chip">${escapeHtml(String(dueCards))} Karten</span>
    </div>
  `;

  if (els.homeQuickStart) {
    els.homeQuickStart.innerHTML = [
      {
        kicker: "Gespräch",
        title: "Tutor",
        copy: "Freies Sprechen, schnelle Korrektur und Verlauf in einer Ansicht.",
        action: "tutor",
        kind: "primary",
        tone: "featured",
        label: "Öffnen",
      },
      {
        kicker: "Wiederholung",
        title: "Review",
        copy: "Fällige Karten bearbeiten und Fehler systematisch festigen.",
        action: "review",
        kind: "secondary",
        tone: "support",
        label: "Starten",
      },
      {
        kicker: "Prüfung",
        title: "Goethe-Modus",
        copy: "Offizielle Materialien und Mock-Praxis aus einer geordneten Arbeitsansicht öffnen.",
        tab: "exams",
        kind: "secondary",
        tone: "support",
        label: "Öffnen",
      },
    ].map((item) => `
      <article class="home-action-card ${item.tone === "featured" ? "is-featured" : "is-support"}">
        <p class="home-card-kicker">${escapeHtml(item.kicker)}</p>
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.copy)}</p>
        <button class="${item.kind === "primary" ? "primary-btn" : "ghost-btn"}" type="button" ${item.action ? `data-open-primary="${escapeHtml(item.action)}"` : `data-open-tab="${escapeHtml(item.tab)}"`}>${escapeHtml(item.label)}</button>
      </article>
    `).join("");
  }

  if (els.homeCoachBrief) {
    els.homeCoachBrief.innerHTML = coachBrief.map((item) => `
      <article class="home-brief-item">
        <span class="home-brief-label">${escapeHtml(item.label)}</span>
        <strong>${escapeHtml(item.value)}</strong>
        <p>${escapeHtml(item.copy)}</p>
      </article>
    `).join("");
  }
};

window.renderReviewOverview = function renderReviewOverview() {
  if (!els.reviewHeroStats || !els.reviewQueueSummary) return;
  const dueDecks = [...(state.decks || [])].filter((deck) => Number(deck.due_cards || 0) > 0);
  const dueCards = dueDecks.reduce((sum, deck) => sum + Number(deck.due_cards || 0), 0);
  const selectedDeck = (state.decks || []).find((deck) => deck.id === (els.reviewDeckSelect?.value || ""));
  const activeDeckLabel = selectedDeck?.name || "All decks";

  els.reviewHeroStats.innerHTML = `
    <article class="review-stat-pill">
      <span>Due today</span>
      <strong>${escapeHtml(String(dueCards))}</strong>
      <p>${escapeHtml(String(dueDecks.length))} deck(s) active</p>
    </article>
    <article class="review-stat-pill">
      <span>Current filter</span>
      <strong>${escapeHtml(activeDeckLabel)}</strong>
      <p>${selectedDeck ? "Focused repetition queue" : "Reviewing across all decks"}</p>
    </article>
    <article class="review-stat-pill">
      <span>Session state</span>
      <strong>${state.reviewCard ? "Active card" : (dueCards ? "Ready" : "Clear")}</strong>
      <p>${state.reviewBackVisible ? "Answer visible" : "Front of card"}</p>
    </article>
  `;

  if (state.reviewCard) {
    els.reviewQueueSummary.innerHTML = `
      <p class="review-card-kicker">Active card loaded</p>
      <strong>${escapeHtml(state.reviewCard.front)}</strong>
      <p>Flip the card only after you actively recall the answer, then grade the quality of that recall.</p>
    `;
    return;
  }

  if (selectedDeck) {
    els.reviewQueueSummary.innerHTML = `
      <p class="review-card-kicker">Focused deck</p>
      <strong>${escapeHtml(selectedDeck.name)}</strong>
      <p>${escapeHtml(String(selectedDeck.due_cards || 0))} cards are due in this deck right now.</p>
    `;
    return;
  }

  els.reviewQueueSummary.innerHTML = dueCards
    ? `
      <p class="review-card-kicker">Review is ready</p>
      <strong>Clear ${escapeHtml(String(dueCards))} cards with one uninterrupted block.</strong>
      <p>${escapeHtml(String(dueDecks.length))} deck(s) contain due material. Load the next card to start the session.</p>
    `
    : `
      <p class="review-card-kicker">Queue clear</p>
      <strong>No card is currently due.</strong>
      <p>Your review queue is empty. Import a starter deck or open Workspace to generate more material.</p>
    `;
};

window.renderReviewCard = function renderReviewCard() {
  if (!state.reviewCard) {
    els.reviewCardBox.innerHTML = `
      <div class="review-card-empty-state">
        <p class="review-card-kicker">Review ritual</p>
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
      <div class="review-card-answer-block">
        <p class="review-card-answer">${escapeHtml(state.reviewCard.back)}</p>
        ${extra.example ? `<p class="muted">${escapeHtml(extra.example)}</p>` : ""}
        ${extra.notes ? `<p class="muted">${escapeHtml(extra.notes)}</p>` : ""}
        ${extra.note ? `<p class="muted">${escapeHtml(extra.note)}</p>` : ""}
      </div>
    `
    : `<p class="review-card-hint">Recall the answer first, then flip the card and grade the quality of that recall.</p>`;
  els.reviewCardBox.innerHTML = `
    <div class="review-card-shell ${state.reviewBackVisible ? "is-back" : "is-front"}">
      <div class="review-card-topline">
        <p class="review-card-kicker">${state.reviewBackVisible ? "Answer" : "Prompt"}</p>
        <span class="review-card-state">${state.reviewBackVisible ? "Grade recall" : "Reveal when ready"}</span>
      </div>
      <strong class="review-card-title">${escapeHtml(state.reviewCard.front)}</strong>
      ${tags.length ? `<div class="review-card-tag-row">${tags.map((tag) => `<span class="review-card-tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
      ${back}
    </div>
  `;
};

window.getTutorAvatarMeta = function getTutorAvatarMeta(avatarKey = state.tutorAvatar) {
  const resolvedAvatarKey = typeof window.normalizeTutorIdentityKey === "function"
    ? window.normalizeTutorIdentityKey(avatarKey)
    : String(avatarKey || "").trim().toLowerCase() === "man"
      ? "man"
      : "woman";
  const registry = {
    woman: {
      badge: "FV",
      title: "Female voice",
      copy: "A lighter playback profile for tutor replies and browser fallback audio.",
      voiceGender: "female",
    },
    man: {
      badge: "MV",
      title: "Male voice",
      copy: "A deeper playback profile for tutor replies and browser fallback audio.",
      voiceGender: "male",
    },
  };
  return registry[resolvedAvatarKey] || registry.woman;
};

window.normalizeTutorIdentityKey = function normalizeTutorIdentityKey(avatarKey = state.tutorAvatar) {
  const key = String(avatarKey || "").trim().toLowerCase();
  if (["woman", "female", "studio"].includes(key)) return "woman";
  if (["man", "male", "coach", "examiner"].includes(key)) return "man";
  return "woman";
};

window.getTutorConversationPersonaKey = function getTutorConversationPersonaKey() {
  return "studio";
};

window.getTutorVoicePersonaKey = function getTutorVoicePersonaKey() {
  return state.chatVoiceGender === "male" ? "man" : "woman";
};

window.getTutorPersonaVoiceGender = function getTutorPersonaVoiceGender() {
  return state.chatVoiceGender || getTutorAvatarMeta().voiceGender || "female";
};

window.hasActiveTutorConversation = function hasActiveTutorConversation() {
  return Boolean(state.conversationId || (state.chatTranscriptEntries || []).length);
};

window.commitTutorAvatarPreference = function commitTutorAvatarPreference(nextAvatar) {
  state.tutorAvatar = normalizeTutorIdentityKey(nextAvatar);
  state.chatVoiceGender = state.tutorAvatar === "man" ? "male" : "female";
  writeUiPreferences({
    tutorAvatar: state.tutorAvatar,
    tutorIdentity: state.tutorAvatar,
    chatVoiceGender: state.chatVoiceGender,
  });
  window.logTutorIdentityVoiceDebug?.("identity-selected", {
    visibleIdentity: state.tutorAvatar,
    outgoingTtsPersonaKey: typeof window.getTutorVoicePersonaKey === "function" ? window.getTutorVoicePersonaKey() : state.tutorAvatar,
    browserFallbackGender: state.chatVoiceGender,
  });
  applyTutorAvatarPreference();
  refreshChatTtsUi();
  if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
};

window.requestTutorAvatarChange = async function requestTutorAvatarChange(nextAvatar) {
  const targetAvatar = normalizeTutorIdentityKey(nextAvatar);
  if (targetAvatar === state.tutorAvatar) {
    applyTutorAvatarPreference();
    return true;
  }
  if (["speaking", "fallback", "queueing"].includes(String(state.tutorAudio?.mode || "").trim().toLowerCase())) {
    stopChatSpeech();
  }
  commitTutorAvatarPreference(targetAvatar);
  return true;
};

window.applyTutorAvatarPreference = function applyTutorAvatarPreference() {
  const resolvedIdentity = state.chatVoiceGender === "male"
    ? "man"
    : normalizeTutorIdentityKey(state.tutorAvatar);
  if (state.tutorAvatar !== resolvedIdentity) state.tutorAvatar = resolvedIdentity;
  state.chatVoiceGender = resolvedIdentity === "man" ? "male" : "female";
  const meta = getTutorAvatarMeta(resolvedIdentity);
  const identityLabel = resolvedIdentity === "man" ? "Male voice" : "Female voice";
  if (els.profileAvatarBadge) els.profileAvatarBadge.textContent = meta.badge;
  if (els.tutorAvatarTitle) els.tutorAvatarTitle.textContent = meta.title;
  if (els.tutorAvatarCopy) els.tutorAvatarCopy.textContent = meta.copy;
  if (els.chatTutorIdentityLabel) els.chatTutorIdentityLabel.textContent = identityLabel;
  if (els.profileTutorIdentityLabel) els.profileTutorIdentityLabel.textContent = identityLabel;
  if (els.chatVoiceGender && els.chatVoiceGender.value !== state.chatVoiceGender) {
    els.chatVoiceGender.value = state.chatVoiceGender;
  }
  if (els.profileTutorVoiceGender && els.profileTutorVoiceGender.value !== state.chatVoiceGender) {
    els.profileTutorVoiceGender.value = state.chatVoiceGender;
  }
  document.querySelectorAll("[data-profile-avatar]").forEach((button) => {
    button.classList.toggle("active", button.dataset.profileAvatar === resolvedIdentity);
  });
  document.querySelectorAll("[data-tutor-avatar]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tutorAvatar === resolvedIdentity);
  });
  window.setTutorAvatarPersona?.(resolvedIdentity);
  window.syncTutorAvatarPresentation?.();
};

window.renderLearn = function renderLearn() {
  if (!els.learnHeroSummary) return;
  const overview = state.progressOverview || {};
  const weakSkills = overview.weak_skills || [];
  const dueDecks = [...(state.decks || [])].filter((deck) => Number(deck.due_cards || 0) > 0);
  const activeRoadmap = overview.active_roadmap || null;
  const nextSession = overview.next_session || null;
  const probability = overview.full_exam_probability?.probability_percent;
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "Exam";
  const recentConversation = (state.chatHistoryItems || [])[0] || null;

  els.learnHeroActions.innerHTML = `
    ${overview.recommendation_event_id ? `<button class="primary-btn" type="button" data-start-recommendation="1">Start recommended training</button>` : `<button class="primary-btn" type="button" data-open-tab="exams">Open exam prep</button>`}
    <button class="ghost-btn" type="button" data-open-tab="grammar">Grammar lab</button>
    <button class="ghost-btn" type="button" data-open-tab="writing">Writing coach</button>
  `;

  els.learnHeroSummary.innerHTML = `
    <p class="home-card-kicker">Current study signal</p>
    <strong>${escapeHtml(nextSession?.title || "Structured study starts with one clear track.")}</strong>
    <p>${escapeHtml(nextSession?.action || "Choose a learning lane below and drop into the specialist workspace with more intent.")}</p>
    <div class="learn-hero-metrics">
      <article><span>Readiness</span><strong>${escapeHtml(probability == null ? "Building" : `${probability}%`)}</strong></article>
      <article><span>Focus</span><strong>${escapeHtml(priorityModuleLabel)}</strong></article>
      <article><span>Due review</span><strong>${escapeHtml(String(overview.due_flashcards || 0))}</strong></article>
    </div>
  `;

  els.learnPrimaryPathways.innerHTML = [
    {
      kicker: "Exam track",
      title: "Goethe practice hub",
      copy: "Open official material, mock support, and exam flow management from one place.",
      tab: "exams",
      tone: "featured",
      label: "Open exam prep",
    },
    {
      kicker: "Foundation",
      title: "Grammar lab",
      copy: "Train targeted structures with theory, exercises, and correction.",
      tab: "grammar",
      tone: "support",
      label: "Open grammar",
    },
    {
      kicker: "Output",
      title: "Writing coach",
      copy: "Generate tasks, write, and review rubric-based correction.",
      tab: "writing",
      tone: "support",
      label: "Open writing",
    },
    {
      kicker: "Output",
      title: "Speaking simulation",
      copy: "Use structured speaking rounds when you need more guided oral practice.",
      tab: "speaking",
      tone: "support",
      label: "Open speaking",
    },
  ].map((item) => `
    <article class="learn-pathway-card ${item.tone === "featured" ? "is-featured" : "is-support"}">
      <p class="learn-card-kicker">${escapeHtml(item.kicker)}</p>
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.copy)}</p>
      <button class="${item.tone === "featured" ? "primary-btn" : "ghost-btn"}" type="button" data-open-tab="${escapeHtml(item.tab)}">${escapeHtml(item.label)}</button>
    </article>
  `).join("");

  els.learnCurriculumRail.innerHTML = `
    <article class="learn-guide-item">
      <span class="learn-card-kicker">Weakest cluster</span>
      <strong>${escapeHtml(priorityModuleLabel)}</strong>
      <p>${escapeHtml(weakSkills.length ? weakSkills.slice(0, 3).map((item) => `${skillLabels[item.skill] || item.skill} ${item.average_percent}%`).join(" / ") : "No weak-skill cluster detected yet.")}</p>
    </article>
    <article class="learn-guide-item">
      <span class="learn-card-kicker">Roadmap</span>
      <strong>${escapeHtml(activeRoadmap?.title || "No active roadmap")}</strong>
      <p>${escapeHtml(activeRoadmap?.next_checkpoint || "Activate a roadmap in Workspace to keep the long-range structure visible here.")}</p>
    </article>
    <article class="learn-guide-item">
      <span class="learn-card-kicker">Tutor memory</span>
      <strong>${escapeHtml(recentConversation ? `${recentConversation.turns} turns stored` : "No recent tutor session")}</strong>
      <p>${escapeHtml(recentConversation?.preview || "Tutor transcripts will appear here as soon as you build recent conversation history.")}</p>
    </article>
  `;

  els.learnPracticeRack.innerHTML = [
    ["placement", "Placement check", "Use a diagnostic run to reset the next focus."],
    ["roadmap", "Roadmap builder", "Turn the target exam into a week-by-week study plan."],
    ["vocab", "Vocabulary builder", "Generate themed word lists and push them into decks."],
    ["speaking", "Speaking sim", "Practice guided oral turns with feedback."],
    ["writing", "Writing coach", "Practice productive output with correction."],
    ["grammar", "Grammar drills", "Train one structure at a time."],
  ].map(([tab, title, copy]) => `
    <article class="learn-practice-card">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(copy)}</p>
      <button class="ghost-btn" type="button" data-open-tab="${escapeHtml(tab)}">Open</button>
    </article>
  `).join("");

  els.learnWorkspaceLinks.innerHTML = [
    ["exams", `Exam prep${overview.recommendation_event_id ? " recommended" : ""}`],
    ["placement", "Placement"],
    ["roadmap", "Roadmap"],
    ["grammar", "Grammar"],
    ["writing", "Writing"],
    ["speaking", "Speaking"],
    ["vocab", `Vocabulary${dueDecks.length ? ` / ${dueDecks.length} active deck(s)` : ""}`],
  ].map(([tab, label]) => `<button class="ghost-btn learn-workspace-link" type="button" data-open-tab="${escapeHtml(tab)}">${escapeHtml(label)}</button>`).join("");
};

window.renderProgressSurface = function renderProgressSurface() {
  if (!els.progressHeroStats) return;
  const overview = state.progressOverview || {};
  const probability = overview.full_exam_probability?.probability_percent;
  const weakSkill = (overview.weak_skills || [])[0] || null;
  const weakLabel = weakSkill ? `${weakSkill.skill} ${weakSkill.average_percent}%` : "No weak skill yet";
  const roadmap = overview.active_roadmap || null;
  const nextSession = overview.next_session || null;
  const recommendationLabel = overview.recommended_exam_scope === "module" ? "Module focus" : "Full exam";
  const placementLabel = overview.latest_placement_level || "Placement signal pending";

  els.progressHeroStats.innerHTML = `
    <article class="progress-hero-pill">
      <span>Readiness</span>
      <strong>${escapeHtml(probability == null ? "Building" : `${probability}%`)}</strong>
      <p>${escapeHtml(recommendationLabel)}</p>
    </article>
    <article class="progress-hero-pill">
      <span>Streak</span>
      <strong>${escapeHtml(String(overview.streak_days || 0))} days</strong>
      <p>${escapeHtml(nextSession?.title || "Keep momentum visible.")}</p>
    </article>
    <article class="progress-hero-pill">
      <span>Weakest point</span>
      <strong>${escapeHtml(weakLabel)}</strong>
      <p>${escapeHtml(nextSession?.action || "Use the plan below to choose the next block.")}</p>
    </article>
  `;

  if (els.progressStoryCard) {
    els.progressStoryCard.innerHTML = `
      <p class="learn-card-kicker">Trajectory</p>
      <strong>${escapeHtml(nextSession?.title || "Build a clearer signal with a few tracked sessions.")}</strong>
      <p>${escapeHtml(nextSession?.action || "Progress becomes more useful after tutor, review, and structured practice all feed into the same loop.")}</p>
      <div class="inline-actions">
        <button class="primary-btn" type="button" data-open-primary="learn">Open Learn</button>
        <button class="ghost-btn" type="button" data-open-primary="review">Open Review</button>
      </div>
      <div class="progress-story-meta">
        <article>
          <span>Direction</span>
          <strong>${escapeHtml(roadmap?.title || recommendationLabel)}</strong>
        </article>
        <article>
          <span>Placement</span>
          <strong>${escapeHtml(placementLabel)}</strong>
        </article>
      </div>
    `;
  }

  const recommendationCta = overview.recommendation_event_id
    ? `<button class="primary-btn" type="button" data-use-recommendation="1" data-recommendation-event-id="${escapeHtml(overview.recommendation_event_id)}" data-recommendation-strategy="${escapeHtml(overview.recommendation_strategy || "")}" data-scope="${escapeHtml(overview.recommended_exam_scope || "full")}" data-priority-module="${escapeHtml(overview.priority_module || "")}">Start recommendation</button>`
    : `<button class="ghost-btn" type="button" data-open-tab="exams">Open exam prep</button>`;

  if (els.progressRoadmap) {
    els.progressRoadmap.innerHTML = `
      <p class="learn-card-kicker">Active roadmap</p>
      <strong>${escapeHtml(roadmap?.title || overview.exam_readiness || "No active roadmap yet")}</strong>
      <p>${escapeHtml(roadmap?.next_checkpoint || nextSession?.action || "Your next best training move will appear here as more tracked work accumulates.")}</p>
      <div class="inline-actions">
        ${recommendationCta}
        <button class="ghost-btn" type="button" data-open-tab="roadmap">Open roadmap</button>
      </div>
    `;
  }

  if (els.progressPlacement) {
    els.progressPlacement.innerHTML = `
      <p class="learn-card-kicker">Placement and direction</p>
      <strong>${escapeHtml(overview.latest_placement_level || "No placement result stored")}</strong>
      <p>${escapeHtml(weakSkill ? `Weakest measured lane: ${weakSkill.skill}.` : "Run placement or more tracked work to sharpen the signal.")}</p>
      <div class="inline-actions">
        <button class="ghost-btn" type="button" data-open-tab="placement">Open placement</button>
      </div>
    `;
  }
};

window.renderProfileSurface = function renderProfileSurface() {
  if (!els.profileHeroSummary) return;
  const settings = state.settings || {};
  const regionalOptions = typeof window.getChatRegionalVoiceOptions === "function"
    ? window.getChatRegionalVoiceOptions()
    : [];
  const regionOptions = state.chatVoiceVariant === "regional" && regionalOptions.length
    ? regionalOptions
    : [{ value: "de-DE", label: "Hochdeutsch" }];

  applyTutorAvatarPreference();

  if (els.profileGlobalLevelSelect && els.profileGlobalLevelSelect.value !== (els.globalLevel?.value || "B2")) {
    els.profileGlobalLevelSelect.value = els.globalLevel?.value || "B2";
  }
  if (els.profileTutorVoiceGender && els.profileTutorVoiceGender.value !== state.chatVoiceGender) {
    els.profileTutorVoiceGender.value = state.chatVoiceGender;
  }
  if (els.profileTutorVoiceVariant && els.profileTutorVoiceVariant.value !== state.chatVoiceVariant) {
    els.profileTutorVoiceVariant.value = state.chatVoiceVariant;
  }
  if (els.profileTutorVoiceRegion) {
    els.profileTutorVoiceRegion.innerHTML = regionOptions
      .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
      .join("");
    if (!regionOptions.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = regionOptions[0].value;
      persistChatVoicePreferences();
    }
    els.profileTutorVoiceRegion.value = state.chatVoiceRegion;
    els.profileTutorVoiceRegion.disabled = !(state.chatVoiceVariant === "regional" && regionalOptions.length);
  }
  if (els.profileTutorTtsToggle) {
    els.profileTutorTtsToggle.textContent = state.chatTtsEnabled ? "Tutor-Wiedergabe an" : "Tutor-Wiedergabe aus";
  }

  const goalExam = settings.default_goal_exam ? settings.default_goal_exam.replace(/_/g, " ").toUpperCase() : "GOETHE B2";
  const voiceLabel = state.chatVoiceGender === "male" ? "Männliche Stimme" : "Weibliche Stimme";
  const variantLabel = state.chatVoiceVariant === "regional" ? "Regional" : "Hochdeutsch";
  const localVoiceLabel = String(state.config?.tutor_tts_voice_label || "").trim();
  const localVoiceSummary = state.config?.tutor_local_tts_available
    ? `Lokale Wiedergabe verfügbar${localVoiceLabel ? ` (${localVoiceLabel})` : ""}.`
    : "Lokale Wiedergabe nicht verfügbar.";
  const browserVoiceSummary = typeof window.describeTutorBrowserVoiceResolution === "function" && typeof window.resolveTutorBrowserVoice === "function"
    ? window.describeTutorBrowserVoiceResolution(window.resolveTutorBrowserVoice(window.getTutorVoicePersonaKey?.() || state.chatVoiceGender))
    : "Systemstimme ohne Detailinfo.";
  const tutorVoiceSummary = `${localVoiceSummary} Systemstimme: ${browserVoiceSummary}`;

  els.profileHeroSummary.innerHTML = `
    <article class="profile-summary-card">
      <span>Ziel</span>
      <strong>${escapeHtml(goalExam)}</strong>
      <p>${escapeHtml(settings.default_goal_level || els.globalLevel?.value || "B2")}</p>
    </article>
    <article class="profile-summary-card">
      <span>Sprache</span>
      <strong>${escapeHtml((settings.interface_language || "de").toUpperCase())}</strong>
      <p>${escapeHtml((settings.explanation_language || "es").toUpperCase())} für Erklärungen</p>
    </article>
    <article class="profile-summary-card">
      <span>Tutor</span>
      <strong>${escapeHtml(voiceLabel)}</strong>
      <p>${escapeHtml(variantLabel)}</p>
    </article>
  `;

  if (els.profileTutorSummary) {
    els.profileTutorSummary.innerHTML = `
      <strong>${escapeHtml(voiceLabel)} · ${escapeHtml(variantLabel)}</strong>
      <p>${escapeHtml(tutorVoiceSummary)}</p>
      <p class="muted">${state.chatTtsEnabled ? "Wiedergabe für Tutor-Antworten ist aktiviert." : "Wiedergabe für Tutor-Antworten ist deaktiviert."}</p>
    `;
  }
};

window.renderHome = function renderHome() {
  if (!els.homeMissionCard) return;
  const overview = state.progressOverview || {};
  const mistakes = state.progressMistakes || [];
  const dueDecks = [...(state.decks || [])]
    .filter((deck) => Number(deck.due_cards || 0) > 0)
    .sort((left, right) => Number(right.due_cards || 0) - Number(left.due_cards || 0));
  const recentConversation = (state.chatHistoryItems || [])[0] || null;
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "Prüfung";
  const probability = overview.full_exam_probability?.probability_percent;
  const activeRoadmap = overview.active_roadmap || null;
  const dueCards = Number(overview.due_flashcards || 0);
  const streakDays = Number(overview.streak_days || 0);
  const dueDeckSummary = dueDecks.length
    ? dueDecks.slice(0, 2).map((deck) => `${deck.name} (${deck.due_cards})`).join(" · ")
    : "Keine fälligen Decks.";
  const topMistake = mistakes[0]
    ? `${mistakes[0].label}${mistakes[0].example ? ` · ${mistakes[0].example}` : ""}`
    : "Noch kein wiederkehrendes Fehlermuster.";
  const roadmapSummary = activeRoadmap
    ? `${activeRoadmap.target_exam} · ${activeRoadmap.target_level}`
    : "Kein aktiver Lernplan";

  if (els.homeMissionActions) {
    els.homeMissionActions.innerHTML = `
      <strong>Nächster Schritt</strong>
      <div class="home-ops-action-row">
        ${overview.recommendation_event_id ? `<button class="primary-btn" type="button" data-start-recommendation="1">Empfehlung</button>` : `<button class="primary-btn" type="button" data-open-primary="tutor">Tutor</button>`}
        <button class="ghost-btn" type="button" data-open-primary="exam-prep">Prüfung</button>
      </div>
    `;
  }

  els.homeMissionCard.innerHTML = `
    <strong>Ziel</strong>
    <p class="home-ops-mainline">${escapeHtml(overview.exam_readiness || "Eine kurze, fokussierte Einheit starten.")}</p>
    <p class="muted">${escapeHtml(overview.next_session?.action || "Tutor öffnen oder direkt in die Prüfungseinheit wechseln.")}</p>
  `;

  if (els.homeQuickStart) {
    els.homeQuickStart.innerHTML = `
      <strong>Schnellzugriff</strong>
      <div class="home-ops-quick-row">
        <button class="ghost-btn" type="button" data-open-primary="tutor">Tutor</button>
        <button class="ghost-btn" type="button" data-open-primary="exam-prep">Prüfung</button>
        <button class="ghost-btn" type="button" data-open-tab="flashcards">Karteikarten</button>
      </div>
    `;
  }

  if (els.homeCoachBrief) {
    els.homeCoachBrief.innerHTML = `
      <strong>Status</strong>
      <div class="home-ops-status-list">
        <span>${escapeHtml(probability == null ? "Signal im Aufbau" : `${probability}% Signal`)}</span>
        <span>${escapeHtml(priorityModuleLabel)}</span>
        <span>${escapeHtml(String(dueCards))} Karten</span>
        <span>${escapeHtml(String(streakDays))} Tage</span>
      </div>
      <p class="muted">${escapeHtml(activeRoadmap ? roadmapSummary : (recentConversation ? recentConversation.preview : topMistake || dueDeckSummary))}</p>
      <div class="home-brief-tools">
        <button class="ghost-btn" type="button" data-open-tab="progress">Fortschritt</button>
        <button class="ghost-btn" type="button" data-open-tab="roadmap">Lernplan</button>
      </div>
    `;
  }
};

window.renderProfileSurface = function renderProfileSurface() {
  if (!els.profileTutorSummary) return;
  const settings = state.settings || {};
  const regionalOptions = typeof window.getChatRegionalVoiceOptions === "function"
    ? window.getChatRegionalVoiceOptions()
    : [];
  const regionOptions = state.chatVoiceVariant === "regional" && regionalOptions.length
    ? regionalOptions
    : [{ value: "de-DE", label: "Hochdeutsch" }];

  if (els.profileGlobalLevelSelect && els.profileGlobalLevelSelect.value !== (els.globalLevel?.value || "B2")) {
    els.profileGlobalLevelSelect.value = els.globalLevel?.value || "B2";
  }
  if (els.profileTutorVoiceGender && els.profileTutorVoiceGender.value !== state.chatVoiceGender) {
    els.profileTutorVoiceGender.value = state.chatVoiceGender;
  }
  if (els.profileTutorVoiceVariant && els.profileTutorVoiceVariant.value !== state.chatVoiceVariant) {
    els.profileTutorVoiceVariant.value = state.chatVoiceVariant;
  }
  if (els.profileTutorVoiceRegion) {
    els.profileTutorVoiceRegion.innerHTML = regionOptions
      .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
      .join("");
    if (!regionOptions.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = regionOptions[0].value;
      persistChatVoicePreferences();
    }
    els.profileTutorVoiceRegion.value = state.chatVoiceRegion;
    els.profileTutorVoiceRegion.disabled = !(state.chatVoiceVariant === "regional" && regionalOptions.length);
  }
  if (els.profileTutorTtsToggle) {
    els.profileTutorTtsToggle.textContent = state.chatTtsEnabled ? "Tutor-Wiedergabe an" : "Tutor-Wiedergabe aus";
  }

  const goalExam = settings.default_goal_exam ? settings.default_goal_exam.replace(/_/g, " ").toUpperCase() : "GOETHE B2";
  const voiceLabel = state.chatVoiceGender === "male" ? "Männliche Stimme" : "Weibliche Stimme";
  const variantLabel = state.chatVoiceVariant === "regional" ? "Regional" : "Hochdeutsch";
  const localVoiceLabel = String(state.config?.tutor_tts_voice_label || "").trim();
  const localVoiceSummary = state.config?.tutor_local_tts_available
    ? `Lokale Wiedergabe verfügbar${localVoiceLabel ? ` (${localVoiceLabel})` : ""}.`
    : "Lokale Wiedergabe nicht verfügbar.";
  const browserVoiceSummary = typeof window.describeTutorBrowserVoiceResolution === "function" && typeof window.resolveTutorBrowserVoice === "function"
    ? window.describeTutorBrowserVoiceResolution(window.resolveTutorBrowserVoice(window.getTutorVoicePersonaKey?.() || state.chatVoiceGender))
    : "Systemstimme ohne Detailinfo.";

  els.profileHeroSummary.innerHTML = `
    <article class="profile-summary-card">
      <span>Ziel</span>
      <strong>${escapeHtml(goalExam)}</strong>
      <p>${escapeHtml(settings.default_goal_level || els.globalLevel?.value || "B2")}</p>
    </article>
    <article class="profile-summary-card">
      <span>Sprache</span>
      <strong>${escapeHtml((settings.interface_language || "de").toUpperCase())}</strong>
      <p>${escapeHtml((settings.explanation_language || "es").toUpperCase())} für Erklärungen</p>
    </article>
    <article class="profile-summary-card">
      <span>Tutor</span>
      <strong>${escapeHtml(voiceLabel)}</strong>
      <p>${escapeHtml(variantLabel)}</p>
    </article>
  `;

  if (els.profileTutorSummary) {
    els.profileTutorSummary.innerHTML = `
      <strong>${escapeHtml(voiceLabel)} · ${escapeHtml(variantLabel)}</strong>
      <p>${escapeHtml(localVoiceSummary)}</p>
      <p class="muted">Systemstimme: ${escapeHtml(browserVoiceSummary)}</p>
    `;
  }
};

window.renderReviewOverview = function renderReviewOverview() {
  if (!els.reviewHeroStats || !els.reviewQueueSummary) return;
  const dueDecks = [...(state.decks || [])].filter((deck) => Number(deck.due_cards || 0) > 0);
  const dueCards = dueDecks.reduce((sum, deck) => sum + Number(deck.due_cards || 0), 0);
  const selectedDeck = (state.decks || []).find((deck) => deck.id === (els.reviewDeckSelect?.value || ""));
  const activeDeckLabel = selectedDeck?.name || "Alle Kartensätze";

  els.reviewHeroStats.innerHTML = `
    <article class="review-stat-pill">
      <span>Heute fällig</span>
      <strong>${escapeHtml(String(dueCards))}</strong>
      <p>${escapeHtml(String(dueDecks.length))} aktive Sätze</p>
    </article>
    <article class="review-stat-pill">
      <span>Aktiver Satz</span>
      <strong>${escapeHtml(activeDeckLabel)}</strong>
      <p>${selectedDeck ? "Gezielte Wiederholung" : "Satzübergreifende Wiederholung"}</p>
    </article>
    <article class="review-stat-pill">
      <span>Status</span>
      <strong>${state.reviewCard ? "Aktive Karte" : (dueCards ? "Bereit" : "Leer")}</strong>
      <p>${state.reviewBackVisible ? "Antwort sichtbar" : "Vorderseite aktiv"}</p>
    </article>
  `;

  if (state.reviewCard) {
    els.reviewQueueSummary.innerHTML = `
      <p class="review-card-kicker">Aktuelle Karte</p>
      <strong>${escapeHtml(state.reviewCard.front)}</strong>
      <p>Erst aktiv erinnern, dann aufdecken und die Erinnerung bewerten.</p>
    `;
    return;
  }

  if (selectedDeck) {
    els.reviewQueueSummary.innerHTML = `
      <p class="review-card-kicker">Gewählter Satz</p>
      <strong>${escapeHtml(selectedDeck.name)}</strong>
      <p>${escapeHtml(selectedDeck.description || "Gezielte Wiederholung aus einem Kartensatz.")}</p>
    `;
    return;
  }

  els.reviewQueueSummary.innerHTML = `
    <p class="review-card-kicker">Wiederholung</p>
    <strong>${dueCards ? "Bereit für die nächste Karte" : "Keine fälligen Karten"}</strong>
    <p>${dueCards ? "Satz wählen und direkt mit der aktiven Wiederholung starten." : "Neue Karten hinzufügen oder einen anderen Satz wählen."}</p>
  `;
};

window.renderProgressSurface = function renderProgressSurface() {
  if (!els.progressHeroStats) return;
  const overview = state.progressOverview || {};
  const probability = overview.full_exam_probability?.probability_percent;
  const weakSkill = (overview.weak_skills || [])[0] || null;
  const weakLabel = weakSkill ? `${weakSkill.skill} ${weakSkill.average_percent}%` : "Noch kein Schwerpunkt";
  const roadmap = overview.active_roadmap || null;
  const nextSession = overview.next_session || null;
  const recommendationLabel = overview.recommended_exam_scope === "module" ? "Modulfokus" : "Gesamtprüfung";
  const placementLabel = overview.latest_placement_level || "Noch keine Einstufung";

  els.progressHeroStats.innerHTML = `
    <article class="progress-hero-pill">
      <span>Signal</span>
      <strong>${escapeHtml(probability == null ? "Im Aufbau" : `${probability}%`)}</strong>
      <p>${escapeHtml(recommendationLabel)}</p>
    </article>
    <article class="progress-hero-pill">
      <span>Serie</span>
      <strong>${escapeHtml(String(overview.streak_days || 0))} Tage</strong>
      <p>${escapeHtml(nextSession?.title || "Rhythmus sichtbar halten.")}</p>
    </article>
    <article class="progress-hero-pill">
      <span>Schwachpunkt</span>
      <strong>${escapeHtml(weakLabel)}</strong>
      <p>${escapeHtml(nextSession?.action || "Nächsten Block aus dem Plan wählen.")}</p>
    </article>
  `;

  if (els.progressStoryCard) {
    els.progressStoryCard.innerHTML = `
      <p class="learn-card-kicker">Verlauf</p>
      <strong>${escapeHtml(nextSession?.title || "Das Signal wird mit jeder gespeicherten Einheit klarer.")}</strong>
      <p>${escapeHtml(nextSession?.action || "Tutor, Prüfung und Wiederholung verdichten sich hier zu einer klaren Lage.")}</p>
      <div class="inline-actions">
        <button class="primary-btn" type="button" data-open-primary="tutor">Tutor</button>
        <button class="ghost-btn" type="button" data-open-tab="flashcards">Karteikarten</button>
      </div>
      <div class="progress-story-meta">
        <article>
          <span>Richtung</span>
          <strong>${escapeHtml(roadmap?.title || recommendationLabel)}</strong>
        </article>
        <article>
          <span>Einstufung</span>
          <strong>${escapeHtml(placementLabel)}</strong>
        </article>
      </div>
    `;
  }

  const recommendationCta = overview.recommendation_event_id
    ? `<button class="primary-btn" type="button" data-use-recommendation="1" data-recommendation-event-id="${escapeHtml(overview.recommendation_event_id)}" data-recommendation-strategy="${escapeHtml(overview.recommendation_strategy || "")}" data-scope="${escapeHtml(overview.recommended_exam_scope || "full")}" data-priority-module="${escapeHtml(overview.priority_module || "")}">Empfehlung starten</button>`
    : `<button class="ghost-btn" type="button" data-open-tab="exams">Prüfung öffnen</button>`;

  if (els.progressRoadmap) {
    els.progressRoadmap.innerHTML = `
      <p class="learn-card-kicker">Aktiver Plan</p>
      <strong>${escapeHtml(roadmap?.title || overview.exam_readiness || "Noch kein aktiver Lernplan")}</strong>
      <p>${escapeHtml(roadmap?.next_checkpoint || nextSession?.action || "Der nächste sinnvolle Block erscheint hier.")}</p>
      <div class="inline-actions">
        ${recommendationCta}
        <button class="ghost-btn" type="button" data-open-tab="roadmap">Lernplan öffnen</button>
      </div>
    `;
  }

  if (els.progressPlacement) {
    els.progressPlacement.innerHTML = `
      <p class="learn-card-kicker">Einstufung</p>
      <strong>${escapeHtml(placementLabel)}</strong>
      <p>${escapeHtml(weakSkill ? `Schwächste gemessene Spur: ${weakSkill.skill}.` : "Mehr Daten oder eine Einstufung schärfen das Bild.")}</p>
      <div class="inline-actions">
        <button class="ghost-btn" type="button" data-open-tab="placement">Einstufung öffnen</button>
      </div>
    `;
  }
};

window.renderExamWorkspace = ((originalRenderExamWorkspace) => function renderExamWorkspaceWrapped() {
  originalRenderExamWorkspace();
  els.examWorkspace?.classList.toggle("is-session-active", state.examWorkspaceActive === true);
  els.examWorkspaceCloseBtn?.classList.toggle("hidden", state.examWorkspaceActive !== true);
  if (els.examWorkspaceChangeBtn) {
    els.examWorkspaceChangeBtn.textContent = state.examWorkspaceActive ? "Zur Auswahl" : "Auswahl";
  }
})(window.renderExamWorkspace);

const simplifiedBindEventsBase = window.bindEvents;
window.bindEvents = function bindEventsWrapped() {
  simplifiedBindEventsBase();
  els.examSecondaryTools?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-tab]");
    if (!button) return;
    switchTab(button.dataset.openTab);
  });
};

const baseRefreshProgress = window.refreshProgress;
window.refreshProgress = async function refreshProgressWrapped() {
  await baseRefreshProgress();
  if (typeof window.renderLearn === "function") window.renderLearn();
  if (typeof window.renderProgressSurface === "function") window.renderProgressSurface();
  if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
};

const baseRefreshChatHistory = window.refreshChatHistory;
window.refreshChatHistory = async function refreshChatHistoryWrapped() {
  const result = await baseRefreshChatHistory();
  if (typeof window.renderLearn === "function") window.renderLearn();
  return result;
};

const baseRefreshDecks = window.refreshDecks;
window.refreshDecks = async function refreshDecksWrapped() {
  const result = await baseRefreshDecks();
  if (typeof window.renderLearn === "function") window.renderLearn();
  if (typeof window.renderProgressSurface === "function") window.renderProgressSurface();
  return result;
};

const baseRefreshStarterDecks = window.refreshStarterDecks;
window.refreshStarterDecks = async function refreshStarterDecksWrapped() {
  const result = await baseRefreshStarterDecks();
  if (typeof window.renderLearn === "function") window.renderLearn();
  return result;
};

const baseRefreshChatTtsUi = window.refreshChatTtsUi;
window.refreshChatTtsUi = function refreshChatTtsUiWrapped() {
  baseRefreshChatTtsUi();
  if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
};

const baseRefreshMockAudioVoiceUi = window.refreshMockAudioVoiceUi;
window.refreshMockAudioVoiceUi = function refreshMockAudioVoiceUiWrapped() {
  baseRefreshMockAudioVoiceUi();
  if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
};

const baseBindEvents = window.bindEvents;
window.bindEvents = function bindEventsWrapped() {
  baseBindEvents();
  if (window.__premiumSurfaceEventsBound) return;
  window.__premiumSurfaceEventsBound = true;

  const handlePremiumLaunch = (event) => {
    const primaryButton = event.target.closest("[data-open-primary]");
    if (primaryButton) {
      openPrimaryTab(primaryButton.dataset.openPrimary);
      return;
    }
    const workspaceButton = event.target.closest("[data-open-tab]");
    if (workspaceButton) {
      switchTab(workspaceButton.dataset.openTab);
      return;
    }
    const recommendationButton = event.target.closest("[data-start-recommendation]");
    if (recommendationButton && state.progressOverview?.recommendation_event_id) {
      activateRecommendationLaunch({
        recommendationEventId: state.progressOverview.recommendation_event_id,
        recommendationStrategy: state.progressOverview.recommendation_strategy || "",
        recommendedScope: state.progressOverview.recommended_exam_scope || "full",
        priorityModule: state.progressOverview.priority_module || "",
        source: "learn_or_profile",
      });
    }
  };

  [
    els.learnHeroActions,
    els.learnPrimaryPathways,
    els.learnCurriculumRail,
    els.learnPracticeRack,
    els.learnWorkspaceLinks,
    els.progressStoryCard,
    els.progressRoadmap,
    els.progressPlacement,
  ].forEach((container) => {
    container?.addEventListener("click", handlePremiumLaunch);
  });

  els.openWorkspaceShellBtn?.addEventListener("click", () => openPrimaryTab("workspace"));
  els.profileOpenWorkspaceBtn?.addEventListener("click", () => openPrimaryTab("workspace"));

  els.profileGlobalLevelSelect?.addEventListener("change", () => {
    if (!els.globalLevel) return;
    els.globalLevel.value = els.profileGlobalLevelSelect.value;
    els.globalLevel.dispatchEvent(new Event("change", { bubbles: true }));
    if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
  });

  els.profileTutorVoiceGender?.addEventListener("change", () => {
    state.chatVoiceGender = els.profileTutorVoiceGender.value;
    if (els.chatVoiceGender) els.chatVoiceGender.value = state.chatVoiceGender;
    applyTutorAvatarPreference();
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });

  els.profileTutorVoiceVariant?.addEventListener("change", () => {
    state.chatVoiceVariant = els.profileTutorVoiceVariant.value;
    const regionalOptions = getChatRegionalVoiceOptions();
    if (state.chatVoiceVariant !== "regional" || !regionalOptions.length) {
      state.chatVoiceVariant = "standard";
      state.chatVoiceRegion = "de-DE";
    } else if (!regionalOptions.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = regionalOptions[0].value;
    }
    if (els.chatVoiceVariant) els.chatVoiceVariant.value = state.chatVoiceVariant;
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });

  els.profileTutorVoiceRegion?.addEventListener("change", () => {
    state.chatVoiceRegion = els.profileTutorVoiceRegion.value || "de-DE";
    if (els.chatVoiceRegion) els.chatVoiceRegion.value = state.chatVoiceRegion;
    stopChatSpeech();
    persistChatVoicePreferences();
    refreshChatTtsUi();
    updateChatComposerState();
  });

  els.profileTutorTtsToggle?.addEventListener("click", () => {
    toggleChatTts();
    if (typeof window.renderProfileSurface === "function") window.renderProfileSurface();
  });

  document.querySelectorAll("[data-profile-avatar]").forEach((button) => {
    button.addEventListener("click", () => {
      requestTutorAvatarChange(button.dataset.profileAvatar || "woman").catch((error) => {
        setStatus(`Tutor-Identitaet konnte nicht gewechselt werden: ${error.message}`);
        applyTutorAvatarPreference();
      });
    });
  });

  document.querySelectorAll("[data-tutor-avatar]").forEach((button) => {
    button.addEventListener("click", () => {
      requestTutorAvatarChange(button.dataset.tutorAvatar || "woman").catch((error) => {
        setStatus(`Tutor-Identitaet konnte nicht gewechselt werden: ${error.message}`);
        applyTutorAvatarPreference();
      });
    });
  });
};

window.saveSettings = async function saveSettings() {
  setStatus("Einstellungen werden gespeichert ...");
  state.settings = await apiFetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      interface_language: els.uiLanguageSelect.value,
      explanation_language: els.explanationLanguageSelect.value,
      default_goal_exam: els.settingsGoalExam.value,
      default_goal_level: els.settingsGoalLevel.value,
    }),
  });
  const languageLabels = {
    de: "Deutsch",
    en: "Englisch",
    es: "Spanisch",
    fr: "Französisch",
    it: "Italienisch",
    pt: "Portugiesisch",
  };
  const interfaceLabel = languageLabels[state.settings.interface_language] || state.settings.interface_language;
  const explanationLabel = languageLabels[state.settings.explanation_language] || state.settings.explanation_language;
  els.settingsState.textContent = `Oberfläche: ${interfaceLabel} · Erklärungen: ${explanationLabel}.`;
  refreshMockAudioVoiceUi();
  applyLanguage();
  refreshHeroMetrics();
  setStatus("Einstellungen gespeichert.");
};

window.describeMockAudioState = function describeMockAudioState(segments = getMockMediaSegments()) {
  const preferenceLabel = getMockAudioVoicePreferenceLabel();
  if (!segments.length) {
    return `Mock-Stimme: ${preferenceLabel}. Offizielle Audios bleiben unverändert.`;
  }
  const serverSegments = segments.filter((segment) => Boolean(segment.audio_url));
  const voiceLabels = [...new Set(serverSegments.map((segment) => String(segment.voice_label || "").trim()).filter(Boolean))];
  if (serverSegments.length) {
    const voiceSuffix = voiceLabels.length ? ` Audiodatei: ${voiceLabels.join(", ")}.` : "";
    return `${serverSegments.length}/${segments.length} Hörteile mit Audiodatei. Stimme: ${preferenceLabel}.${voiceSuffix}`;
  }
  if (chatSpeechSupported()) {
    return `Mock mit Systemstimme. Auswahl: ${preferenceLabel}.`;
  }
  return `Mock ohne Wiedergabe. Auswahl: ${preferenceLabel}.`;
};

window.renderHome = function renderHome() {
  if (!els.homeMissionCard) return;
  const overview = state.progressOverview || {};
  const skillLabels = { lesen: "Lesen", hoeren: "Hören", schreiben: "Schreiben", sprechen: "Sprechen" };
  const compactLine = (value, fallback, maxLength = 68) => {
    const source = String(value || fallback || "").replace(/\s+/g, " ").trim();
    if (!source) return fallback;
    const firstSentence = source.split(/(?<=[.!?])\s+/)[0].trim();
    const normalized = firstSentence || source;
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1).trimEnd()}…` : normalized;
  };
  const probability = overview.full_exam_probability?.probability_percent;
  const dueCards = Number(overview.due_flashcards || 0);
  const streakDays = Number(overview.streak_days || 0);
  const activeRoadmap = overview.active_roadmap || null;
  const priorityModuleLabel = skillLabels[overview.priority_module] || overview.priority_module || "Prüfung";
  const goalLine = activeRoadmap
    ? `${formatGoalExamLabel(activeRoadmap.target_exam)} · ${activeRoadmap.target_level}`
    : "";
  const statusLine = activeRoadmap
    ? compactLine(goalLine, "Plan aktiv.", 42)
    : state.examTimerPaused
      ? "Pausierte Prüfung bereit."
      : "Bereit für Tutor oder Prüfung.";
  const utilityAction = state.examTimerPaused
    ? { label: "Fortsetzen", primary: "exam-prep" }
    : { label: "Einstellungen", primary: "settings" };
  const missionLine = compactLine(overview.exam_readiness, "Heute eine kurze, klare Einheit.", 54);
  const missionSupport = compactLine(
    overview.next_session?.action,
    state.examTimerPaused ? "Jetzt fortsetzen oder direkt starten." : "Tutor öffnen oder direkt starten.",
    46,
  );

  els.homeMissionCard.innerHTML = `
    <strong>Ziel</strong>
    <p class="home-ops-mainline">${escapeHtml(missionLine)}</p>
    <p class="muted">${escapeHtml(missionSupport)}</p>
  `;

  if (els.homeMissionActions) {
    els.homeMissionActions.innerHTML = `
      <strong>Nächster Schritt</strong>
      <div class="home-ops-action-row">
        ${overview.recommendation_event_id ? `<button class="primary-btn" type="button" data-start-recommendation="1">Empfehlung</button>` : `<button class="primary-btn" type="button" data-open-primary="tutor">Tutor</button>`}
        <button class="ghost-btn" type="button" data-open-primary="exam-prep">Prüfung</button>
      </div>
    `;
  }

  if (els.homeQuickStart) {
    els.homeQuickStart.innerHTML = `
      <strong>Schnellzugriff</strong>
      <div class="home-ops-quick-row">
        <button class="ghost-btn" type="button" data-open-primary="tutor">Tutor</button>
        <button class="ghost-btn" type="button" data-open-primary="exam-prep">Prüfung</button>
        <button class="ghost-btn" type="button" data-open-primary="${escapeHtml(utilityAction.primary)}">${escapeHtml(utilityAction.label)}</button>
      </div>
    `;
  }

  if (els.homeCoachBrief) {
    els.homeCoachBrief.innerHTML = `
      <strong>Status</strong>
      <div class="home-ops-status-list">
        <span>${escapeHtml(probability == null ? "Signal im Aufbau" : `${probability}% Signal`)}</span>
        <span>${escapeHtml(priorityModuleLabel)}</span>
        <span>${escapeHtml(String(streakDays))} Tage</span>
        ${dueCards > 0 ? `<span>${escapeHtml(String(dueCards))} Karten</span>` : ""}
      </div>
      <p class="muted">${escapeHtml(statusLine)}</p>
    `;
  }
};

window.renderLearn = function renderLearn() {};

window.renderProfileSurface = function renderProfileSurface() {
  if (!els.profileHeroSummary) return;
  const settings = state.settings || {};
  const regionalOptions = typeof window.getChatRegionalVoiceOptions === "function"
    ? window.getChatRegionalVoiceOptions()
    : [];
  const regionOptions = state.chatVoiceVariant === "regional" && regionalOptions.length
    ? regionalOptions
    : [{ value: "de-DE", label: "Hochdeutsch" }];

  if (els.profileGlobalLevelSelect && els.profileGlobalLevelSelect.value !== (els.globalLevel?.value || "B2")) {
    els.profileGlobalLevelSelect.value = els.globalLevel?.value || "B2";
  }
  if (els.profileTutorVoiceGender && els.profileTutorVoiceGender.value !== state.chatVoiceGender) {
    els.profileTutorVoiceGender.value = state.chatVoiceGender;
  }
  if (els.profileTutorVoiceVariant && els.profileTutorVoiceVariant.value !== state.chatVoiceVariant) {
    els.profileTutorVoiceVariant.value = state.chatVoiceVariant;
  }
  if (els.profileTutorVoiceRegion) {
    els.profileTutorVoiceRegion.innerHTML = regionOptions
      .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
      .join("");
    if (!regionOptions.some((option) => option.value === state.chatVoiceRegion)) {
      state.chatVoiceRegion = regionOptions[0].value;
      persistChatVoicePreferences();
    }
    els.profileTutorVoiceRegion.value = state.chatVoiceRegion;
    els.profileTutorVoiceRegion.disabled = !(state.chatVoiceVariant === "regional" && regionalOptions.length);
  }
  if (els.profileTutorTtsToggle) {
    els.profileTutorTtsToggle.textContent = state.chatTtsEnabled ? "Wiedergabe an" : "Wiedergabe aus";
  }

  if (els.profileHeroSummary) {
    els.profileHeroSummary.innerHTML = "";
  }

  if (els.profileTutorSummary) {
    const voiceLabel = state.chatVoiceGender === "male" ? "Männliche Stimme" : "Weibliche Stimme";
    const variantLabel = state.chatVoiceVariant === "regional" ? "Regional" : "Hochdeutsch";
    const localVoiceLabel = String(state.config?.tutor_tts_voice_label || "").trim();
    const localVoiceSummary = state.config?.tutor_local_tts_available
      ? `Lokale Wiedergabe verfügbar${localVoiceLabel ? ` (${localVoiceLabel})` : ""}.`
      : "Lokale Wiedergabe nicht verfügbar.";
    const goalSummary = `${settings.default_goal_exam ? settings.default_goal_exam.replace(/_/g, " ").toUpperCase() : "GOETHE B2"} · ${settings.default_goal_level || els.globalLevel?.value || "B2"}`;
    els.profileTutorSummary.innerHTML = `
      <strong>${escapeHtml(goalSummary)}</strong>
      <p>${escapeHtml(voiceLabel)} · ${escapeHtml(variantLabel)}</p>
      <p class="muted">${escapeHtml(localVoiceSummary)}</p>
    `;
  }
};

window.renderExamWorkspace = ((baseRenderExamWorkspace) => function renderExamWorkspaceSimplified() {
  baseRenderExamWorkspace();
  const active = state.examWorkspaceActive === true;
  const isMock = state.selectedPracticeResourceType === "mock";
  const activeSetLabel = els.examWorkspaceSets?.querySelector(".is-active strong")?.textContent?.trim() || "Satz links wählen";

  els.examWorkspace?.classList.toggle("is-session-active", active);
  els.examWorkspace?.classList.toggle("is-session-idle", !active);

  [els.examWorkspaceMeta, els.examResults, els.examWorkspaceGuide].forEach((node) => {
    if (!node) return;
    node.classList.add("hidden");
    node.hidden = true;
    node.setAttribute("aria-hidden", "true");
  });

  if (els.examWorkspaceCloseBtn) {
    els.examWorkspaceCloseBtn.classList.add("hidden");
  }
  if (els.examWorkspaceChangeBtn) {
    els.examWorkspaceChangeBtn.classList.toggle("hidden", !active);
    els.examWorkspaceChangeBtn.textContent = "Zur Auswahl";
  }
  if (els.examWorkspaceOpenSource) {
    const hasSource = Boolean(els.examWorkspaceOpenSource.href && els.examWorkspaceOpenSource.href !== "#");
    els.examWorkspaceOpenSource.classList.toggle("hidden", !active || !hasSource);
  }

  if (els.examWorkspaceMock) {
    els.examWorkspaceMock.innerHTML = `
      <button class="exam-choice-btn exam-choice-btn-compact exam-choice-btn-mock${isMock ? " is-active" : ""}" data-practice-resource="mock">
        <span class="exam-choice-kicker">Mock</span>
        <strong>App-Variante</strong>
        <span class="exam-choice-meta">${escapeHtml(isMock ? "Aktiv" : "Optional")}</span>
      </button>
    `;
  }

  els.examWorkspaceBody?.querySelectorAll(".exam-resource-grid-inline, .exam-choice-btn-mock-note").forEach((node) => node.remove());

  if (!active && els.examWorkspaceBody) {
    els.examWorkspaceTitle.textContent = "Arbeitsfläche";
    els.examWorkspaceSubtitle.textContent = activeSetLabel;
    els.examWorkspaceBody.innerHTML = `
      <section class="exam-canvas-empty">
        <strong>Bereit zum Arbeiten</strong>
        <p>Format, Modul und Satz links wählen. Danach startet das offizielle Material oder der Mock direkt in dieser Fläche.</p>
      </section>
    `;
  }
  if (typeof window.syncPersistedExamTimerBadge === "function") {
    window.syncPersistedExamTimerBadge();
  }
})(window.renderExamWorkspace);
