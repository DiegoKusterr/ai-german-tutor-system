from pathlib import Path

import pytest

import learning_app.db as db_module
from learning_app.db import connection_scope, init_db
from learning_app.goethe_blueprints import GOETHE_BLUEPRINT_VERSION, build_part_blueprint
from learning_app.goethe_official import GOETHE_OFFICIAL_EXAMS
from learning_app.schemas import (
    EvaluationPayload,
    ExamGenerateRequest,
    ExamPayload,
    ExamSubmitRequest,
    FlashcardImportPayload,
    FlashcardImportRequest,
    GrammarGenerateRequest,
    GrammarPayload,
    GrammarSubmitRequest,
    GrammarTheoryPayload,
    GrammarTopicSummary,
    MockGenerationHealthPayload,
    OfficialExamPayload,
    OfficialExamRequest,
    RoadmapGenerateRequest,
    ReviewNextPayload,
    ReviewNextRequest,
    SpeakingSimulateRequest,
    SpeakingSimulationPayload,
    VocabFromTopicRequest,
    VocabPayload,
    WritingPromptPayload,
    WritingPromptRequest,
)
from learning_app.services import exam_mock_generation as exam_mock_generation_module
from learning_app.services.common import build_study_plan, ensure_local_user
from learning_app.services.flashcards import import_flashcards, next_review_card
from learning_app.services.learning import (
    generate_exam,
    generate_grammar,
    generate_speaking_session,
    generate_vocab,
    generate_writing_prompt,
    get_official_exam,
    get_grammar_catalog,
    get_grammar_theory,
    submit_exam,
    submit_grammar,
)
from learning_app.services.progress import get_progress_overview
from learning_app.services.roadmap import generate_roadmap, get_current_roadmap
from learning_app.services.mock_telemetry import get_mock_generation_health


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "learning_app_test.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()
    ensure_local_user()
    return db_path


def test_structured_generation_payloads_validate(isolated_db: Path) -> None:
    grammar = generate_grammar(GrammarGenerateRequest(focus="Dativ mit Präpositionen"))
    exam = generate_exam(ExamGenerateRequest(scope="module", module="lesen"))
    hearing_exam = generate_exam(ExamGenerateRequest(scope="module", module="hoeren", mock_audio_voice_gender="female"))
    writing_exam = generate_exam(ExamGenerateRequest(scope="module", module="schreiben"))
    speaking_exam = generate_exam(ExamGenerateRequest(scope="module", module="sprechen"))
    full_exam = generate_exam(ExamGenerateRequest(scope="full", module="lesen"))
    official = get_official_exam(OfficialExamRequest(level="B2", scope="module", module="lesen"))
    official_c2 = get_official_exam(OfficialExamRequest(level="C2", scope="module", module="lesen"))
    writing = generate_writing_prompt(WritingPromptRequest())
    speaking = generate_speaking_session(SpeakingSimulateRequest())
    vocab = generate_vocab(VocabFromTopicRequest(topic="Airport"))
    catalog = get_grammar_catalog()
    theory = get_grammar_theory(catalog[0].key)
    imported = import_flashcards(FlashcardImportRequest(deck_name="Airport deck", items=vocab.items[:3]))
    review = next_review_card(ReviewNextRequest(deck_id=imported.deck.id))

    assert GrammarPayload.model_validate_json(grammar.model_dump_json()).focus
    assert ExamPayload.model_validate_json(exam.model_dump_json()).module == "lesen"
    assert ExamPayload.model_validate_json(hearing_exam.model_dump_json()).mock_media_pack
    assert hearing_exam.mock_audio_voice_gender == "female"
    assert hearing_exam.generation_elapsed_ms >= 0
    assert isinstance(hearing_exam.module_brief_used, bool)
    assert ExamPayload.model_validate_json(writing_exam.model_dump_json()).module == "schreiben"
    assert ExamPayload.model_validate_json(speaking_exam.model_dump_json()).module == "sprechen"
    assert ExamPayload.model_validate_json(full_exam.model_dump_json()).module == "full"
    assert exam.generator_version
    assert exam.generation_mode
    assert exam.source_framework
    assert exam.calibration_notes
    assert exam.variant_seed
    assert OfficialExamPayload.model_validate_json(official.model_dump_json()).institution == "goethe"
    assert OfficialExamPayload.model_validate_json(official_c2.model_dump_json()).level == "C2"
    assert official.official_page_url == official.page_url
    assert official.practice_page_url
    assert official.practice_sets
    assert official.practice_sets[0].resources
    assert all(resource.official for resource in official.practice_sets[0].resources)
    assert official.mock_calibration
    assert official.modules[0].parts
    assert official_c2.modules[0].parts
    assert WritingPromptPayload.model_validate_json(writing.model_dump_json()).prompt_id == writing.prompt_id
    assert SpeakingSimulationPayload.model_validate_json(speaking.model_dump_json()).session_id == speaking.session_id
    assert VocabPayload.model_validate_json(vocab.model_dump_json()).items
    assert GrammarTopicSummary.model_validate_json(catalog[0].model_dump_json()).key
    validated_theory = GrammarTheoryPayload.model_validate_json(theory.model_dump_json())
    assert validated_theory.deep_dive
    assert validated_theory.references
    assert FlashcardImportPayload.model_validate_json(imported.model_dump_json()).imported_cards == 3
    assert ReviewNextPayload.model_validate_json(review.model_dump_json()).due_count >= 0
    assert review.message == "Karte für die nächste Wiederholung bereit."


def test_evaluation_payloads_validate(isolated_db: Path) -> None:
    grammar = generate_grammar(GrammarGenerateRequest(focus="Nebensätze", count=4))
    answers = {item.id: item.answer for item in grammar.items}
    evaluation = submit_grammar(GrammarSubmitRequest(exercise_id=grammar.exercise_id, answers=answers))

    validated = EvaluationPayload.model_validate_json(evaluation.model_dump_json())
    assert validated.percent == pytest.approx(100.0)
    assert len(validated.results) == 4


def test_official_support_materials_include_verified_goethe_references() -> None:
    assert any("Wortliste A1" in resource["label"] for resource in GOETHE_OFFICIAL_EXAMS["A1"]["resources"])
    assert any("Wortliste B1" in resource["label"] for resource in GOETHE_OFFICIAL_EXAMS["B1"]["resources"])
    assert any("Literaturliste C2" in resource["label"] for resource in GOETHE_OFFICIAL_EXAMS["C2"]["resources"])


def test_official_goethe_links_use_current_verified_targets() -> None:
    expected_page_urls = {
        "A1": "https://www.goethe.de/ins/de/en/prf/prf/gzsd1.html",
        "A2": "https://www.goethe.de/ins/de/en/prf/prf/gzsd2.html",
        "B1": "https://www.goethe.de/ins/de/en/prf/prf/gzb1.html",
        "B2": "https://www.goethe.de/ins/de/en/prf/prf/gzb2.html",
        "C1": "https://www.goethe.de/ins/de/en/prf/prf/gzc1.html",
        "C2": "https://www.goethe.de/ins/de/en/prf/prf/gzc2.html",
    }
    resource_urls = {
        resource["url"]
        for exam in GOETHE_OFFICIAL_EXAMS.values()
        for resource in exam["resources"]
    }

    for level, expected_url in expected_page_urls.items():
        exam = GOETHE_OFFICIAL_EXAMS[level]
        assert exam["page_url"] == expected_url
        assert any(resource["url"] == expected_url for resource in exam["resources"] if "Prüfungsseite" in resource["label"])

    assert "https://www.goethe.de/pro/relaunch/prf/de/A1_SD1_Wortliste_02.pdf" in resource_urls
    assert "https://www.goethe.de/pro/relaunch/prf/de/Goethe-Zertifikat_B1_Wortliste.pdf" in resource_urls
    assert "https://www.goethe.de/pro/relaunch/prf/en/Pruefungsziele_Testbeschreibung_B2.pdf" in resource_urls
    assert "https://www.goethe.de/pro/relaunch/prf/Literaturliste_C2/Goethe_Zertifikat_C2_Literaturliste.pdf" in resource_urls

    banned_urls = {
        "https://www.goethe.de/en/spr/kup/prf/prf/gzsd1.html",
        "https://www.goethe.de/en/spr/kup/prf/prf/gzsd2.html",
        "https://www.goethe.de/en/spr/kup/prf/prf/gb1.html",
        "https://www.goethe.de/en/spr/kup/prf/prf/gb2.html",
        "https://www.goethe.de/en/spr/kup/prf/prf/gc1.html",
        "https://www.goethe.de/en/spr/kup/prf/prf/gc2.html",
        "https://www.goethe.de/pro/relaunch/prf/materialien/A1_sd1/Wortliste_A1.pdf",
        "https://www.goethe.de/pro/relaunch/prf/materialien/B1/Wortliste_B1_1.pdf",
        "https://www.goethe.de/pro/relaunch/prf/de/Goethe-Zertifikat_B2_Beschreibung_der_Pruefung.pdf",
        "https://www.goethe.de/pro/relaunch/prf/materialien/C2/Literaturliste_C2_GDS_010125.pdf",
    }
    assert resource_urls.isdisjoint(banned_urls)


def test_official_exam_copy_is_germanized_for_visible_ui_fields() -> None:
    b2 = GOETHE_OFFICIAL_EXAMS["B2"]
    practice_set = b2["practice_sets"][0]

    assert b2["pass_rule"].startswith("Modulare Prüfung.")
    assert "Die offizielle Struktur bleibt modular" in b2["notes"][0]
    assert practice_set["label"].startswith("Prüfungstraining")
    assert practice_set["audience"] == "Erwachsene"
    assert practice_set["description"].startswith("Offizieller Goethe-B2-Trainingssatz")
    assert practice_set["resources"][0]["label"] == "Offizielles PDF"
    assert practice_set["resources"][1]["label"] == "Offizielle Hördatei"
    assert "Exam training" not in practice_set["label"]
    assert "Adults" not in practice_set["audience"]


def test_level_request_defaults_target_b2() -> None:
    assert ExamGenerateRequest().level == "B2"
    assert ExamGenerateRequest().scope == "full"
    assert GrammarGenerateRequest(focus="Nebensätze").level == "B2"
    assert OfficialExamRequest().level == "B2"
    assert OfficialExamRequest().scope == "full"
    assert SpeakingSimulateRequest().level == "B2"
    assert VocabFromTopicRequest(topic="Arbeit").level == "B2"
    assert WritingPromptRequest().level == "B2"


def test_exam_frontend_uses_single_workspace_flow() -> None:
    frontend = Path("static/assets/app-features.js").read_text(encoding="utf-8")
    helper_state = Path("static/assets/app-helpers.js").read_text(encoding="utf-8")

    assert frontend.count("window.renderOfficialExamOverview = function") == 1
    assert frontend.count("window.renderExamWorkspace = function") == 1
    assert frontend.count("window.openOfficialExamWorkspace = function") == 1
    assert "loadOfficialExamLegacy" not in frontend
    assert "generateExamLegacy" not in frontend
    assert "submitExamLegacyWorkspace" not in frontend
    assert 'state.lastExamModuleUsed = els.examModule.value' in frontend
    assert 'els.examModule.value = state.lastExamModuleUsed' in frontend
    assert 'lastExamModuleUsed: "lesen"' in helper_state


def test_exam_frontend_persists_ui_preferences_and_uses_scope_aware_duration() -> None:
    frontend = Path("static/assets/app-features.js").read_text(encoding="utf-8")
    helpers = Path("static/assets/app-helpers.js").read_text(encoding="utf-8")
    html = Path("static/index.html").read_text(encoding="utf-8")

    assert 'deutschlernstudio:ui:v1' in helpers
    assert "window.restoreUiPreferences = function restoreUiPreferences()" in helpers
    assert "window.persistExamUiPreferences = function persistExamUiPreferences()" in helpers
    assert "window.localStorage?.setItem(UI_PREFERENCES_STORAGE_KEY" in helpers
    assert "examWorkspaceOpen" in helpers
    assert "examEndsAt" in helpers
    assert "examRemainingMs" in helpers
    assert "examTimerPaused" in helpers
    assert "examTimerContextKey" in helpers
    assert "pausedExamSession" in helpers
    assert "mockVariantCounter" in helpers
    assert "mockDraftAnswers" in helpers
    assert "window.applyAnswerDrafts = function applyAnswerDrafts(container, answers = {})" in helpers
    assert "examWorkspaceScrollY" in helpers
    assert "examFocusedAnswerId" in helpers
    assert "window.persistExamWorkspaceViewport = function persistExamWorkspaceViewport(target = null)" in helpers
    assert "window.restoreExamWorkspaceViewport = function restoreExamWorkspaceViewport()" in helpers
    assert "window.renderExamTimerBadge = function renderExamTimerBadge(milliseconds = 0, paused = false)" in helpers
    assert "window.pauseExamTimer = function pauseExamTimer()" in helpers
    assert "window.syncPersistedExamTimerBadge = function syncPersistedExamTimerBadge()" in helpers
    assert "window.openConfirmModal = function openConfirmModal({" in helpers
    assert "window.closeConfirmModal = function closeConfirmModal(confirmed = false)" in helpers
    assert "window.bindConfirmModal = function bindConfirmModal()" in helpers
    assert 'examRequestInFlight: false' in helpers
    assert 'examSubmitInFlight: false' in helpers
    assert 'mockExamPageIndex: 0' in helpers
    assert 'mockEvaluation: null' in helpers
    assert 'mockExamFullscreen: false' in helpers
    assert 'window.setAppBusyBanner = function setAppBusyBanner(message = "", tone = "neutral")' in helpers
    assert 'window.pushAppToast = function pushAppToast(message, tone = "neutral", timeoutMs = 3200)' in helpers
    assert "window.countBlankExamAnswers = function countBlankExamAnswers(container)" in helpers
    assert "Pausiert" in helpers
    assert "Karteikarten-Wiederholung" in helpers
    assert "Noch kein Lernplan vorhanden." in helpers
    assert 'tab_roadmap: "Plan"' in helpers
    assert "plan de estudio" in helpers
    assert 'tab_exams: "Exams"' in helpers
    assert 'tab_exams: "Examens"' in helpers
    assert 'tab_exams: "Esami"' in helpers
    assert 'tab_exams: "Exames"' in helpers
    assert "persistExamUiPreferences();" in frontend
    assert "window.getSelectedExamDurationMinutes = function getSelectedExamDurationMinutes()" in frontend
    assert "window.selectOfficialPracticeResource = function selectOfficialPracticeResource(setKey = null)" in frontend
    assert "window.currentExamTimerContextKey = function currentExamTimerContextKey()" in frontend
    assert "window.currentExamSessionSnapshot = function currentExamSessionSnapshot()" in frontend
    assert "window.applyExamSessionSnapshot = function applyExamSessionSnapshot(snapshot)" in frontend
    assert "window.renderPausedExamSessionPanel = function renderPausedExamSessionPanel()" in frontend
    assert "window.resumePausedExamSession = async function resumePausedExamSession()" in frontend
    assert "window.willRestartReplacePausedSession = function willRestartReplacePausedSession()" in frontend
    assert "window.restartExamSessionFromHub = async function restartExamSessionFromHub()" in frontend
    assert "window.hasChatResetRisk = function hasChatResetRisk()" in frontend
    assert "window.requestChatReset = async function requestChatReset()" in frontend
    assert "window.hasStartedMockDraft = function hasStartedMockDraft()" in frontend
    assert "window.hasQuestionDraft = function hasQuestionDraft(container)" in frontend
    assert "window.hasPlacementRestartRisk = function hasPlacementRestartRisk()" in frontend
    assert "window.requestPlacementStart = async function requestPlacementStart()" in frontend
    assert "window.hasGrammarRestartRisk = function hasGrammarRestartRisk()" in frontend
    assert "window.requestGrammarGenerate = async function requestGrammarGenerate()" in frontend
    assert "window.hasWritingRestartRisk = function hasWritingRestartRisk()" in frontend
    assert "window.requestWritingPrompt = async function requestWritingPrompt()" in frontend
    assert "window.hasSpeakingRestartRisk = function hasSpeakingRestartRisk()" in frontend
    assert "window.requestSpeakingStart = async function requestSpeakingStart()" in frontend
    assert "window.hasVocabGenerationRisk = function hasVocabGenerationRisk()" in frontend
    assert "window.requestVocabGenerate = async function requestVocabGenerate()" in frontend
    assert "window.hasReviewAdvanceRisk = function hasReviewAdvanceRisk()" in frontend
    assert "window.requestNextReviewCard = async function requestNextReviewCard()" in frontend
    assert "window.applyReviewDeckSelection = function applyReviewDeckSelection(deckId)" in frontend
    assert "window.hasReviewDeckSwitchRisk = function hasReviewDeckSwitchRisk(nextDeckId)" in frontend
    assert "window.requestReviewDeckSelection = async function requestReviewDeckSelection(nextDeckId)" in frontend
    assert "pauseExamTimer();" in frontend
    assert "state.pausedExamSession = currentExamSessionSnapshot();" in frontend
    assert "await openConfirmModal({" in frontend
    assert "window.confirm(`Die pausierte Sitzung" not in frontend
    assert "Chatsitzung verwerfen?" in frontend
    assert "Mock-Antworten verwerfen?" in frontend
    assert "Mock unvollstaendig auswerten?" in frontend
    assert "Arbeitsansicht verlassen?" in frontend
    assert "Einstufung neu starten?" in frontend
    assert "Grammatikübung ersetzen?" in frontend
    assert "Schreibaufgabe ersetzen?" in frontend
    assert "Sprechsimulation ersetzen?" in frontend
    assert "Wortschatzliste ersetzen?" in frontend
    assert "Aktuelle Karte überspringen?" in frontend
    assert "Kartensatz wechseln?" in frontend
    assert 'els.grammarResults.textContent = "Nach der Korrektur sehen Sie Fehler, Mini-Drills und den nächsten Schritt.";'
    assert 'els.writingResults.textContent = "Die Rubrik erscheint hier.";'
    assert 'els.speakingFeedback.textContent = "Das Feedback zu jeder Runde erscheint hier.";'
    assert 'els.vocabImportResult.textContent = "Wählen Sie Wörter aus und speichern Sie sie als Kartensatz.";'
    assert "startExamTimer(getSelectedExamDurationMinutes(), nextEndsAt, timerContextKey)" in frontend
    assert "startExamTimer(getSelectedExamDurationMinutes(), null, currentExamTimerContextKey())" in frontend
    assert "Date.now() + state.examRemainingMs" in frontend
    assert "renderPausedExamSessionPanel();" in frontend
    assert 'els.chatNewBtn.addEventListener("click", requestChatReset);' in frontend
    assert 'els.examResumePausedBtn.addEventListener("click", resumePausedExamSession);' in frontend
    assert 'els.examRestartPausedBtn.addEventListener("click", restartExamSessionFromHub);' in frontend
    assert 'els.placementStartBtn.addEventListener("click", requestPlacementStart);' in frontend
    assert 'els.examWorkspaceMock.addEventListener("click", (event) => {' in frontend
    assert 'els.grammarGenerateBtn.addEventListener("click", requestGrammarGenerate);' in frontend
    assert 'els.writingPromptBtn.addEventListener("click", requestWritingPrompt);' in frontend
    assert 'els.speakingStartBtn.addEventListener("click", requestSpeakingStart);' in frontend
    assert 'els.vocabGenerateBtn.addEventListener("click", requestVocabGenerate);' in frontend
    assert 'els.reviewNextBtn.addEventListener("click", requestNextReviewCard);' in frontend
    assert 'if (button) requestReviewDeckSelection(button.dataset.selectDeck);' in frontend
    assert 'els.reviewDeckSelect.addEventListener("change", () => requestReviewDeckSelection(els.reviewDeckSelect.value));' in frontend
    assert 'openOfficialExamWorkspace(state.selectedPracticeSetKey, { restoreTimer: true, restoreViewport: true, smoothScroll: false })' in frontend
    assert 'selectOfficialPracticeResource(state.selectedPracticeSetKey);' in frontend
    assert "window.currentMockDraftKey = function currentMockDraftKey()" in frontend
    assert "window.renderMockLoadingPanel = function renderMockLoadingPanel(forceRegenerate = false)" in frontend
    assert "window.resetMockExamSessionState = function resetMockExamSessionState(options = {})" in frontend
    assert "window.captureMockDraftAnswers = function captureMockDraftAnswers()" in frontend
    assert "window.getMockExamPages = function getMockExamPages()" in frontend
    assert "window.toggleMockExamFullscreen = async function toggleMockExamFullscreen()" in frontend
    assert "window.renderMockExamPreparationPanel = function renderMockExamPreparationPanel()" in frontend
    assert "window.renderMockExamSessionShell = function renderMockExamSessionShell()" in frontend
    assert "window.renderMockExamQuestionCard = function renderMockExamQuestionCard(item, itemIndex, evaluationMap)" in frontend
    assert "window.getMockReviewResultsByFilter = function getMockReviewResultsByFilter(filter = state.mockReviewFilter || \"all\")" in frontend
    assert "window.getFilteredMockEvaluationPayload = function getFilteredMockEvaluationPayload()" in frontend
    assert "window.setMockReviewFilter = function setMockReviewFilter(nextFilter = \"all\")" in frontend
    assert "window.jumpToMockReviewTarget = function jumpToMockReviewTarget(filter = \"problem\")" in frontend
    assert "window.getExamSubmissionRisk = function getExamSubmissionRisk()" in frontend
    assert 'window.confirmExamContextSwitch = async function confirmExamContextSwitch(message, confirmLabel = "Wechseln")' in frontend
    assert "window.persistCurrentMockDraft = function persistCurrentMockDraft()" in frontend
    assert "state.mockVariantCounter += 1;" in frontend
    assert "await loadMockExam(true);" in frontend
    assert "state.mockDraftAnswers = {" in frontend
    assert "...collectAnswers(answersContainer)," in frontend
    assert "if (state.mockDraftKey === currentMockDraftKey()) applyAnswerDrafts(mockQuestions, state.mockDraftAnswers);" in frontend
    assert "state.exam?.variant_seed" in frontend
    assert "state.exam?.generation_mode" in frontend
    assert "state.exam?.generator_version" in frontend
    assert "state.exam?.validation_notes" in frontend
    assert "window.renderMockMediaPack = function renderMockMediaPack()" in frontend
    assert "window.renderExamModuleGuide = function renderExamModuleGuide()" in frontend
    assert 'part.points ? `${escapeHtml(part.points)} Punkte` : ""' in frontend
    assert "window.renderExamModeStrip = function renderExamModeStrip(" in frontend
    assert "window.playMockExamMediaSegment = function playMockExamMediaSegment(partKey)" in frontend
    assert "window.stopMockExamSpeech = function stopMockExamSpeech(options = {})" in frontend
    assert "window.stopMockMediaPlayers = function stopMockMediaPlayers(reset = false)" in frontend
    assert "window.bindMockMediaPlayers = function bindMockMediaPlayers()" in frontend
    assert "window.updateMockAudioVoicePreference = async function updateMockAudioVoicePreference(nextGender)" in frontend
    assert "window.refreshMockAudioVoiceUi = function refreshMockAudioVoiceUi()" in frontend
    assert "window.describeMockAudioState = function describeMockAudioState(segments = getMockMediaSegments())" in frontend
    assert "window.loadMockExamHealth = async function loadMockExamHealth()" in frontend
    assert "window.renderMockExamHealth = function renderMockExamHealth()" in frontend
    assert "document.addEventListener(\"fullscreenchange\"" in frontend
    assert "Mock-Session vorbereiten" in frontend
    assert "Aktuellen Mock fortsetzen" in frontend
    assert "Neue Variante erzeugen" in frontend
    assert "state.exam?.mock_media_pack" in frontend
    assert "state.exam?.generation_elapsed_ms" in frontend
    assert "state.exam?.module_brief_used" in frontend
    assert "exam-module-guide exam-module-guide-inline" in frontend
    assert "segment.audio_url" in frontend
    assert "data-server-mock-media" in frontend
    assert "evaluation-inline-pill" in frontend
    assert "exam-mock-session-stats" in frontend
    assert "exam-mock-result-flags" in frontend
    assert "exam-mock-review-tags" in frontend
    assert "exam-mock-review-filter-copy" in frontend
    assert "data-mock-review-filter" in frontend
    assert "data-mock-review-jump" in frontend
    assert "mock_audio_voice_gender: state.mockAudioVoiceGender" in frontend
    assert 'id="mockAudioVoiceGenderSelect"' in frontend
    assert "window.getTutorPersonaVoiceGender = function getTutorPersonaVoiceGender()" in frontend
    assert "getChatTtsVoice(personaVoiceGender)" in frontend
    assert 'els.settingsMockAudioVoiceGender?.addEventListener("change", async () => {' in frontend
    assert 'window.persistMockAudioVoicePreference = function persistMockAudioVoicePreference()' in helpers
    assert "window.renderActiveTabContext = function renderActiveTabContext()" in helpers
    assert "window.getEvaluationStatusMeta = function getEvaluationStatusMeta(status)" in helpers
    assert "window.getEvaluationActionHint = function getEvaluationActionHint(status, errorTags = [])" in helpers
    assert 'window.renderEvaluationErrorTags = function renderEvaluationErrorTags(errorTags = [], className = "evaluation-review-tag")' in helpers
    assert "evaluation-breakdown-grid" in helpers
    assert "evaluation-review-filter-note" in helpers
    assert "Was jetzt am meisten zaehlt" in helpers
    assert 'mockAudioVoiceGender: "auto"' in helpers
    assert 'mockExamHealth: null' in helpers
    assert "restoreExamWorkspaceViewport();" in frontend
    assert 'window.addEventListener("scroll", () => scheduleExamWorkspaceViewportPersist(), { passive: true });' in frontend
    assert 'state.selectedPracticeResourceType === "mock" ? "mock"' in frontend
    assert "Die offiziellen Ansichten bleiben links jederzeit verfügbar." in frontend
    assert "nicht offiziell" in frontend
    assert "non-official" not in frontend
    assert "Arbeitsansicht öffnen" in html
    assert "Goethe-Prüfungssatz" in html
    assert "Goethe-Prüfungsworkspace" in html
    assert "Goethe-Arbeitsansicht" in html
    assert "Offizielle Ansichten" in html
    assert "AI-Mock Praxis" in html
    assert "Stellen Sie zuerst Format und Modul ein." in html
    assert "Verfuegbare Trainingssaetze" in html
    assert "Offizielle Ressourcen und Begleitmaterial" in html
    assert 'id="examWorkspaceMock"' in html
    assert 'id="tabContextBar"' in html
    assert "Lernplan" in html
    assert "GER-orientierte Diagnose" in html
    assert "Die Diagnose verteilt sich ueber mehrere Fertigkeiten." in html
    assert "Die App verdichtet daraus einen umsetzbaren Plan fuer die naechsten Wochen." in html
    assert "Hier steuern Sie Sprache, Zielpruefung und Mock-Audio zentral." in html
    assert "Die rechte Seite sammelt Feedback pro Runde" in html
    assert "welche globalen Einstellungen gerade gespeichert sind" in html
    assert "support-status-panel" in html
    assert "Kartensatz auswählen" in html
    assert '<option value="en">English</option>' in html
    assert '<option value="fr">Français</option>' in html
    assert '<option value="it">Italiano</option>' in html
    assert '<option value="pt">Português</option>' in html
    assert 'id="settingsMockAudioVoiceGender"' in html
    assert 'id="settingsMockAudioState"' in html
    assert 'id="examMockHealth"' in html
    assert "Pausierte Sitzung" in html
    assert "Fortsetzen" in html
    assert "Neu starten" in html
    assert 'id="confirmModal"' in html
    assert 'id="confirmModalConfirmBtn"' in html
    assert 'id="confirmModalCancelBtn"' in html
    assert 'id="appBusyBanner"' in html
    assert 'id="appToastRail"' in html


def test_study_plan_expands_to_seven_days_with_exam_focus() -> None:
    plan = build_study_plan(
        ["grammatik", "wortschatz"],
        "goethe_b2",
        priority_module="hoeren",
        recommended_scope="module",
    )

    assert len(plan) == 7
    assert "Prüfungspriorität" in plan[0].title
    assert "Hören" in plan[0].action
    assert any("Zeittraining" in item.title for item in plan)


def test_progress_overview_defaults_to_full_exam_when_no_attempts(isolated_db: Path) -> None:
    overview = get_progress_overview("goethe_b2")

    assert overview.recommended_exam_scope == "full"
    assert overview.next_session is not None
    assert len(overview.weekly_plan) == 7
    assert overview.full_exam_probability is not None
    assert len(overview.module_probabilities) == 4


def test_progress_overview_includes_empirical_pass_probability_after_exam_attempts(isolated_db: Path) -> None:
    reading_exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="lesen"))
    submit_exam(
        ExamSubmitRequest(
            exercise_id=reading_exam.exercise_id,
            answers={item.id: item.answer for item in reading_exam.items},
        )
    )
    full_exam = generate_exam(ExamGenerateRequest(level="B2", scope="full", module="lesen"))
    submit_exam(
        ExamSubmitRequest(
            exercise_id=full_exam.exercise_id,
            answers={item.id: item.answer for item in full_exam.items},
        )
    )

    overview = get_progress_overview("goethe_b2")
    reading_probability = next(item for item in overview.module_probabilities if item.module == "lesen")

    assert overview.full_exam_probability is not None
    assert overview.full_exam_probability.probability_percent is not None
    assert overview.full_exam_probability.attempts >= 1
    assert reading_probability.probability_percent is not None
    assert reading_probability.attempts >= 1
    assert reading_probability.basis in {"empirisch", "geschaetzt"}


def test_pass_probability_rewards_positive_recent_trend(isolated_db: Path) -> None:
    from learning_app.services.progress import _build_probability_stat

    declining = _build_probability_stat(label="Lesen", module="lesen", scores=[58.0, 60.0, 64.0, 69.0])
    improving = _build_probability_stat(label="Lesen", module="lesen", scores=[69.0, 64.0, 60.0, 58.0])

    assert declining.probability_percent is not None
    assert improving.probability_percent is not None
    assert improving.probability_percent > declining.probability_percent


def test_roadmap_generation_includes_exam_simulation_focus(isolated_db: Path) -> None:
    roadmap = generate_roadmap(
        RoadmapGenerateRequest(current_level="B1", target_level="B2", target_exam="goethe_b2", weeks=8)
    )

    assert roadmap.title.startswith("Lernplan B1")
    assert roadmap.summary.startswith("Dieser Lernplan führt")
    assert roadmap.weekly_plan
    assert any("Simulation" in " ".join(week.tasks) or "Gesamtprüfung" in " ".join(week.tasks) for week in roadmap.weekly_plan)


def test_get_current_roadmap_normalizes_legacy_copy(isolated_db: Path) -> None:
    roadmap = generate_roadmap(
        RoadmapGenerateRequest(current_level="B1", target_level="B2", target_exam="goethe_b2", weeks=4)
    )
    with connection_scope() as conn:
        conn.execute("UPDATE roadmaps SET is_active = 1 WHERE id = ?", (roadmap.roadmap_id,))
        conn.execute(
            "UPDATE roadmaps SET title = ?, summary = ? WHERE id = ?",
            (
                "Roadmap B1 → B2",
                "Diese Roadmap führt von B1 zu B2 mit Fokus auf Goethe-Zertifikat B2. Sie verbindet Grammatik, Wortschatz, produktive Fertigkeiten und prüfungsnahe Simulation.",
                roadmap.roadmap_id,
            ),
        )

    current = get_current_roadmap()

    assert current is not None
    assert current.title == "Lernplan B1 → B2"
    assert current.summary.startswith("Dieser Lernplan führt")


@pytest.mark.parametrize(
    ("level", "module"),
    [
        ("A1", "lesen"),
        ("B2", "schreiben"),
        ("C2", "sprechen"),
    ],
)
def test_goethe_mock_variants_change_with_seed(isolated_db: Path, level: str, module: str) -> None:
    first = generate_exam(ExamGenerateRequest(level=level, scope="module", module=module, variant_seed="variant-alpha"))
    second = generate_exam(ExamGenerateRequest(level=level, scope="module", module=module, variant_seed="variant-beta"))

    first_support = [item.support_text or item.prompt for item in first.items]
    second_support = [item.support_text or item.prompt for item in second.items]

    assert first_support != second_support


@pytest.mark.parametrize("level", sorted(GOETHE_OFFICIAL_EXAMS))
def test_goethe_exam_generation_matches_official_blueprint(isolated_db: Path, level: str) -> None:
    official = GOETHE_OFFICIAL_EXAMS[level]
    module_order = list(official["modules"])

    for module_key, module_def in official["modules"].items():
        payload = generate_exam(ExamGenerateRequest(level=level, scope="module", module=module_key))

        assert payload.duration_minutes == module_def["duration_minutes"] + module_def["prep_minutes"]
        assert [part.key for part in payload.parts] == [part["key"] for part in module_def["parts"]]
        assert sum(int(part.points or 0) for part in payload.parts) == int(module_def["scoring"]["max_points"])

        expected_item_count = 0
        for part in module_def["parts"]:
            slots = int(part.get("item_count") or 1)
            expected_item_count += slots if module_key in {"lesen", "hoeren"} else 1
        assert len(payload.items) == expected_item_count
        assert all(item.section == module_key for item in payload.items)
        assert payload.items[0].section_title == module_def["parts"][0]["title"]
        assert payload.items[0].prompt

    full_payload = generate_exam(ExamGenerateRequest(level=level, scope="full", module="lesen"))
    expected_duration = sum(
        module["duration_minutes"] + module["prep_minutes"] for module in official["modules"].values()
    )
    seen_sections: list[str] = []
    for item in full_payload.items:
        if not seen_sections or seen_sections[-1] != item.section:
            seen_sections.append(item.section or "")

    assert full_payload.duration_minutes == expected_duration
    assert seen_sections == module_order
    official_payload = get_official_exam(OfficialExamRequest(level=level, scope="module", module="lesen"))
    assert sum(int(part.points or 0) for part in official_payload.modules[0].parts) == int(official["modules"]["lesen"]["scoring"]["max_points"])
    assert official_payload.official_page_url == official_payload.page_url
    assert official_payload.practice_page_url
    assert official_payload.practice_sets
    assert official_payload.mock_calibration
    assert all(resource.official for resource in official_payload.practice_sets[0].resources)
    assert any(resource.resource_type in {"pdf", "digital"} for resource in official_payload.practice_sets[0].resources)


def test_goethe_part_blueprint_derives_generation_constraints() -> None:
    part = GOETHE_OFFICIAL_EXAMS["B2"]["modules"]["lesen"]["parts"][0]
    blueprint = build_part_blueprint("B2", "lesen", part)

    assert blueprint["blueprint_version"] == GOETHE_BLUEPRINT_VERSION
    assert blueprint["part_key"] == "b2_lesen_1"
    assert blueprint["source_type"]
    assert blueprint["register"]
    assert blueprint["lexical_band"]
    assert blueprint["validation_constraints"]["require_single_correct_answer"] is True
    assert blueprint["item_count"] == 9


def test_goethe_mock_generation_is_seed_stable_without_llm(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))

    first = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="lesen", variant_seed="seed-b2-lesen"))
    second = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="lesen", variant_seed="seed-b2-lesen"))

    first_signature = [(item.prompt, item.support_text, tuple(item.options), item.answer, item.points) for item in first.items]
    second_signature = [(item.prompt, item.support_text, tuple(item.options), item.answer, item.points) for item in second.items]

    assert first_signature == second_signature
    assert first.variant_seed == second.variant_seed == "seed-b2-lesen"
    assert first.generation_mode == "deterministic_blueprint"
    assert first.fallback_used is True


def test_goethe_mock_generation_has_valid_answers_and_metadata(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))

    exam = generate_exam(ExamGenerateRequest(level="C1", scope="module", module="hoeren", variant_seed="seed-c1-hoeren"))
    official = get_official_exam(OfficialExamRequest(level="C1", scope="module", module="hoeren"))
    expected_counts = {part.title: int(part.item_count or 1) for part in official.modules[0].parts}
    actual_counts: dict[str, int] = {}

    assert exam.source_framework
    assert exam.generator_version
    assert exam.calibration_notes
    assert exam.validation_notes
    assert exam.mock_media_pack

    for item in exam.items:
        actual_counts[item.section_title or ""] = actual_counts.get(item.section_title or "", 0) + 1
        assert item.prompt
        assert item.support_text
        if item.item_type == "open":
            assert len(item.keywords) >= 3
        else:
            assert item.answer in item.options
            assert len(item.options) >= 2

    for segment in exam.mock_media_pack:
        assert segment.module == "hoeren"
        assert segment.part_key
        assert segment.part_title
        assert segment.source_title
        assert segment.script_text
        assert segment.audio_plays >= 1
        assert segment.duration_hint_seconds > 0
        assert segment.audio_provider in {"none", "local_windows_tts"}

    assert actual_counts == expected_counts


def test_goethe_full_mock_uses_fast_budgeted_llm_calls(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    call_log: list[dict[str, object]] = []

    def _fake_llm(prompt: str, *, seed_key: str, max_tokens: int = 1400, timeout_sec: int | None = None) -> tuple[dict | None, str | None]:
        call_log.append({"seed_key": seed_key, "max_tokens": max_tokens, "timeout_sec": timeout_sec})
        return None, None

    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", _fake_llm)

    payload = generate_exam(ExamGenerateRequest(level="B2", scope="full", module="lesen", variant_seed="full-fast-budget"))

    assert payload.scope == "full"
    assert len(call_log) == 6
    assert all((entry["timeout_sec"] or 0) <= 6 for entry in call_log)
    assert any(str(entry["seed_key"]).endswith("lesen:module-brief") for entry in call_log)
    assert any(str(entry["seed_key"]).endswith("hoeren:module-brief") for entry in call_log)
    assert not any("schreiben:module-brief" in str(entry["seed_key"]) for entry in call_log)
    assert not any("sprechen:module-brief" in str(entry["seed_key"]) for entry in call_log)
    assert any("Schnellprofil aktiv" in note for note in payload.calibration_notes)


def test_submit_exam_reports_goethe_aligned_evaluation(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="schreiben", variant_seed="aligned-writing"))

    evaluation = submit_exam(
        ExamSubmitRequest(
            exercise_id=exam.exercise_id,
            answers={exam.items[0].id: "Ich schreibe einen klar aufgebauten Text mit allen Leitpunkten und einer passenden Schlussformel."},
        )
    )

    assert "Goethe-aligned" in evaluation.summary
    assert "Goethe-aligned" in evaluation.official_alignment
    assert any("Goethe-aligned" in result.feedback for result in evaluation.results)


def test_submit_exam_blank_submission_scores_zero(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="schreiben", variant_seed="blank-writing"))

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={}))

    assert evaluation.score == 0
    assert evaluation.percent == 0
    assert evaluation.summary.startswith("Leere Abgabe erkannt")
    assert all(result.score == 0 for result in evaluation.results)
    assert any("leer" in result.feedback.lower() or "keine verwertbare antwort" in result.feedback.lower() for result in evaluation.results)


def test_submit_exam_nonanswer_open_response_gets_zero(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="sprechen", variant_seed="nonanswer-speaking"))

    evaluation = submit_exam(
        ExamSubmitRequest(
            exercise_id=exam.exercise_id,
            answers={item.id: "Ich weiss nicht." for item in exam.items},
        )
    )

    assert all(result.score == 0 for result in evaluation.results)
    assert any("keine verwertbare antwort" in result.feedback.lower() for result in evaluation.results)


def test_submit_exam_strict_objective_matching_no_partial_credit(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="C2", scope="module", module="hoeren", variant_seed="strict-objective"))

    first = exam.items[0]
    second = exam.items[1]
    evaluation = submit_exam(
        ExamSubmitRequest(
            exercise_id=exam.exercise_id,
            answers={
                first.id: first.answer[:1],
                second.id: second.answer,
            },
        )
    )

    result_map = {item.item_id: item for item in evaluation.results}
    assert result_map[first.id].score == 0
    assert result_map[second.id].score == second.points


def test_submit_exam_reasonable_open_response_scores_meaningfully(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="schreiben", variant_seed="good-writing"))
    item = exam.items[0]
    keywords = item.keywords or ["Thema", "Problem", "Loesung"]
    answer = " ".join(
        [
            f"Meiner Meinung nach ist {keywords[0]} im Zusammenhang mit {keywords[min(1, len(keywords) - 1)]} besonders wichtig.",
            f"Zuerst muss man das Problem {keywords[min(2, len(keywords) - 1)]} offen ansprechen und die Situation realistisch beschreiben.",
            f"Danach sollte das Ziel {keywords[0]} klar formuliert und mit einem passenden Beispiel begruendet werden.",
            f"Aus meiner Sicht braucht man ausserdem einen konkreten Vorschlag, damit {keywords[min(1, len(keywords) - 1)]} im Alltag funktioniert.",
            f"Ein gutes Beispiel zeigt, dass {keywords[min(2, len(keywords) - 1)]} und {keywords[0]} nicht getrennt betrachtet werden koennen.",
            "Deshalb sollte man Schritt fuer Schritt handeln und auch moegliche Schwierigkeiten ehrlich nennen.",
            "Gleichzeitig kann man Vorteile hervorheben, wenn der Plan fuer alle Beteiligten nachvollziehbar bleibt.",
            "Ich finde, dass eine ruhige und klare Argumentation im Goethe-Rahmen besonders ueberzeugend wirkt.",
            "Am Ende sollte der Beitrag einen realistischen Ausblick und eine passende Schlussidee enthalten.",
            "Abschliessend bin ich ueberzeugt, dass diese Loesung sinnvoll ist und zu einer besseren Situation fuehrt.",
        ]
    )

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={item.id: answer}))

    assert evaluation.results[0].score >= evaluation.results[0].max_score * 0.45


def test_submit_exam_short_offtopic_open_response_stays_very_low(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="schreiben", variant_seed="weak-writing"))
    item = exam.items[0]

    evaluation = submit_exam(
        ExamSubmitRequest(
            exercise_id=exam.exercise_id,
            answers={item.id: "Das Thema ist schwierig. Ich finde das interessant, aber mehr weiss ich nicht."},
        )
    )

    assert evaluation.results[0].score <= evaluation.results[0].max_score * 0.12
    assert evaluation.results[0].status in {"weak", "partial"}


def test_submit_full_exam_requires_all_sections_in_target_range(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="full", module="lesen", variant_seed="full-fail"))

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={}))

    assert evaluation.passed is False
    assert evaluation.failed_sections
    assert "Nicht bestanden in" not in evaluation.summary or evaluation.summary.startswith("Leere Abgabe erkannt")


def test_submit_exam_c1_formal_message_requires_formal_register(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="C1", scope="module", module="schreiben", variant_seed="c1-formal-register"))
    item = exam.items[1]
    keywords = item.keywords or ["Thema", "Problem", "Loesung"]
    answer = " ".join(
        [
            f"Ich finde, dass {keywords[0]} im beruflichen Alltag ernst genommen werden muss.",
            f"Zuerst moechte ich das Problem {keywords[min(1, len(keywords) - 1)]} klar beschreiben und seine Folgen benennen.",
            f"Danach erklaere ich, warum {keywords[min(2, len(keywords) - 1)]} aus meiner Sicht die sinnvollste Richtung ist.",
            "Ein Beispiel aus dem Arbeitsalltag zeigt, dass schlechte Absprachen schnell zu Missverstaendnissen und Verzoegerungen fuehren.",
            "Deshalb sollte man die Situation ruhig analysieren, Verantwortung uebernehmen und einen konkreten Schritt zur Verbesserung vorschlagen.",
            "Am Ende ist fuer mich entscheidend, dass die Loesung praktikabel bleibt und kuenftige Probleme moeglichst verhindert werden.",
        ]
    )

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={item.id: answer}))

    assert evaluation.results[1].score <= evaluation.results[1].max_score * 0.55
    assert "register" in {error.tag for error in evaluation.results[1].error_tags}


def test_submit_exam_b2_discussion_requires_visible_interaction(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="B2", scope="module", module="sprechen", variant_seed="b2-discussion-interaction"))
    item = exam.items[1]
    keywords = item.keywords or ["Thema", "Problem", "Loesung"]
    answer = " ".join(
        [
            f"Meiner Meinung nach ist {keywords[0]} ein wichtiges Thema und man sollte sachlich darueber sprechen.",
            f"Zuerst nenne ich das Problem {keywords[min(1, len(keywords) - 1)]} und erklaere, warum es viele Menschen betrifft.",
            f"Danach beschreibe ich {keywords[min(2, len(keywords) - 1)]} als moegliche Loesung und begruende das mit einem Beispiel.",
            "Aus meiner Sicht braucht man ausserdem einen realistischen Plan, damit die vorgeschlagenen Schritte spaeter auch funktionieren.",
            "Am Ende halte ich eine klare Entscheidung fuer sinnvoll, weil unklare Absprachen meistens nur zu neuen Problemen fuehren.",
        ]
    )

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={item.id: answer}))

    assert evaluation.results[1].score <= evaluation.results[1].max_score * 0.55
    assert any(error.tag == "interaktion" for error in evaluation.results[1].error_tags)


def test_submit_exam_c2_extended_text_needs_full_coverage_for_excellent(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="C2", scope="module", module="schreiben", variant_seed="c2-extended-coverage"))
    item = exam.items[1]
    keywords = item.keywords or ["Thema", "Ziel", "Problem"]
    answer = " ".join(
        [
            f"Ich moechte zunaechst das Thema {keywords[0]} historisch und gesellschaftlich einordnen.",
            f"Erstens zeigt sich, dass {keywords[2]} nicht nur eine Randfrage ist, sondern die Legitimation politischer Entscheidungen unmittelbar beruehrt.",
            f"Zweitens darf {keywords[1]} nicht als abstrakte Formel stehen bleiben, sondern muss anhand nachvollziehbarer Kriterien konkretisiert werden.",
            "Darueber hinaus sollte man zwischen symbolischer Anerkennung, rechtlicher Ausgestaltung und alltaeglicher Umsetzung unterscheiden.",
            "Allerdings waere es zu einfach, nur moralisch zu argumentieren, denn auch institutionelle Folgen, Machtasymmetrien und Nebenwirkungen muessen bedacht werden.",
            "Deshalb plaediere ich dafuer, die Positionen nicht zu dramatisieren, sondern ihre Voraussetzungen, Reichweite und Grenzen sauber offenzulegen.",
            "Ferner spricht viel dafuer, Erfahrungen aus vergleichbaren Kontexten einzubeziehen, damit die Debatte nicht bei Schlagwoertern stehen bleibt.",
            "Gleichzeitig sollte man klar benennen, wo bestehende Leitbilder an gesellschaftlicher Wirklichkeit vorbeigehen und dadurch neue Ausgrenzung erzeugen.",
            "Ein ueberzeugender Vorschlag verbindet deshalb Teilhabe, institutionelle Verbindlichkeit und transparente Kommunikation.",
            "Zugleich muss jede Loesung pruefbar bleiben, damit politische Verantwortung nicht hinter wohlklingenden Formeln verschwindet.",
            "Hinzu kommt, dass unterschiedliche Gruppen den Begriff der Gerechtigkeit nicht identisch verstehen und deshalb verschiedene Erwartungen an Sprachpolitik richten.",
            "Wer nur auf nationale Einheit setzt, unterschaetzt oft die produktive Rolle sprachlicher Vielfalt fuer Bildung, Verwaltung und kulturelle Selbstverstaendigung.",
            "Wer umgekehrt nur Pluralitaet feiert, blendet leicht aus, dass gemeinsame Regeln und gemeinsame Verfahren weiterhin notwendig bleiben.",
            "Eine ausgewogene Position sollte deshalb weder nostalgische Einsprachigkeit noch folgenlose Symbolpolitik reproduzieren.",
            "Vielmehr braucht es abgestufte Modelle, die Zugehoerigkeit sichern und zugleich reale Teilhabe ermoeglichen.",
            "Insgesamt ueberzeugt mich ein Ansatz, der unterschiedliche Ebenen des Problems trennt und dennoch zu einem praktikablen Gesamtvorschlag fuehrt.",
            "Abschliessend halte ich eine Loesung fuer tragfaehig, wenn sie politische Klarheit, soziale Sensibilitaet und institutionelle Umsetzbarkeit miteinander verbindet.",
            "Nur dann gewinnt die Debatte an Glaubwuerdigkeit und bleibt fuer unterschiedliche Adressaten nachvollziehbar.",
            "Gerade bei konflikthaften Themen ist es wichtig, Begriffe sorgfaeltig zu definieren, damit die Diskussion nicht in symbolischen Gegensaetzen stecken bleibt.",
            "Ebenso entscheidend ist, dass politische Institutionen ihre Entscheidungen begruenden, evaluieren und gegebenenfalls korrigieren.",
            "So entsteht ein Rahmen, in dem Vielfalt nicht als Stoerung erscheint, sondern als reale Voraussetzung moderner Gesellschaften verstanden wird.",
            "Am Ende ueberzeugt mich ein Modell, das Einheit nicht gegen Pluralitaet ausspielt, sondern beides institutionell vermittelt.",
        ]
    )

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={item.id: answer}))

    assert evaluation.results[1].status == "strong"
    assert evaluation.results[1].score >= evaluation.results[1].max_score * 0.7
    assert evaluation.results[1].score < evaluation.results[1].max_score * 0.95
    assert any(error.tag == "aufgabenbezug" for error in evaluation.results[1].error_tags)


def test_submit_exam_c2_discussion_reserves_top_band_for_more_than_competent_interaction(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))
    exam = generate_exam(ExamGenerateRequest(level="C2", scope="module", module="sprechen", variant_seed="c2-discussion-top-band"))
    item = exam.items[1]
    keywords = item.keywords or ["Thema", "Position", "Problem"]
    answer = " ".join(
        [
            f"Ich moechte zunaechst das Thema {keywords[0]} kurz einordnen und den Anlass praezise benennen.",
            f"Erstens sehe ich {keywords[2]} als Kernproblem, weil daraus unmittelbare praktische Folgen entstehen und weil unterschiedliche Gruppen davon betroffen sind.",
            f"Zweitens halte ich {keywords[1]} nur dann fuer tragfaehig, wenn man die Gegenargumente offen anspricht und die Folgen ehrlich abwaegt.",
            "Allerdings verstehe ich den Einwand, dass eine schnelle Entscheidung neue Probleme schaffen kann und dass man deshalb genauer priorisieren muss.",
            "Darauf wuerde ich antworten, dass man klare Kriterien, pruefbare Schritte und eine transparente Kommunikation braucht.",
            "Wenn Sie diesen Punkt anders sehen, koennten wir zuerst die Prioritaeten klaeren und dann ueber die Umsetzung sprechen.",
            "Darueber hinaus sollte man Beispiele aus der Praxis nennen, damit die Position nicht abstrakt bleibt und Rueckfragen leichter beantwortet werden koennen.",
            "Abschliessend bin ich dafuer, die Position differenziert zu vertreten, Gegenargumente ernst zu nehmen und zugleich Raum fuer Rueckfragen zu lassen.",
        ]
    )

    evaluation = submit_exam(ExamSubmitRequest(exercise_id=exam.exercise_id, answers={item.id: answer}))

    assert evaluation.results[1].status == "strong"
    assert evaluation.results[1].score >= evaluation.results[1].max_score * 0.75
    assert evaluation.results[1].score < evaluation.results[1].max_score * 0.95
    assert any(error.tag == "interaktion" for error in evaluation.results[1].error_tags)


def test_mock_generation_health_persists_and_summarizes_runs(isolated_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exam_mock_generation_module, "generate_structured_exam_part", lambda *args, **kwargs: (None, None))

    generate_exam(ExamGenerateRequest(level="B2", scope="module", module="hoeren", variant_seed="telemetry-hoeren-1"))
    generate_exam(ExamGenerateRequest(level="B2", scope="module", module="hoeren", variant_seed="telemetry-hoeren-2"))
    generate_exam(ExamGenerateRequest(level="B1", scope="module", module="lesen", variant_seed="telemetry-lesen-1"))

    health = get_mock_generation_health()
    validated = MockGenerationHealthPayload.model_validate_json(health.model_dump_json())

    assert validated.window_runs >= 3
    assert len(validated.recent_runs) >= 3
    assert any(run.module == "hoeren" for run in validated.recent_runs)
    hoeren_aggregate = next(item for item in validated.aggregates if item.level == "B2" and item.module == "hoeren")
    assert hoeren_aggregate.total_runs >= 2
    assert 0.0 <= hoeren_aggregate.fallback_ratio <= 1.0
    assert hoeren_aggregate.average_elapsed_ms >= 0
