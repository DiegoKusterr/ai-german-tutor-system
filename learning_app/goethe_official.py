from __future__ import annotations


def _resource(label: str, url: str, resource_type: str, official: bool = True) -> dict[str, object]:
    return {"label": label, "url": url, "resource_type": resource_type, "official": official}


def _practice_set(
    key: str,
    label: str,
    audience: str,
    description: str,
    default_resource_type: str,
    resources: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "audience": audience,
        "description": description,
        "default_resource_type": default_resource_type,
        "resources": resources,
    }


def _scoring(
    *,
    max_points: int,
    pass_points: int,
    raters: str,
    criteria: list[str],
    notes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "max_points": max_points,
        "pass_points": pass_points,
        "raters": raters,
        "criteria": criteria,
        "notes": notes or [],
    }


def _part(
    *,
    key: str,
    title: str,
    instructions: str,
    task_types: list[str],
    recommended_minutes: int,
    item_count: int | None = None,
    points: int | None = None,
    response_format: str | None = None,
    audio_plays: int | None = None,
    min_words: int | None = None,
    notes: list[str] | None = None,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "key": key,
        "title": title,
        "instructions": instructions,
        "task_types": task_types,
        "recommended_minutes": recommended_minutes,
        "item_count": item_count,
        "points": points,
        "response_format": response_format,
        "audio_plays": audio_plays,
        "min_words": min_words,
        "notes": notes or [],
    }
    payload.update(extra)
    return payload


def _module(
    *,
    key: str,
    label: str,
    duration_minutes: int,
    prep_minutes: int,
    structure: list[str],
    parts: list[dict[str, object]],
    scoring: dict[str, object],
) -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "duration_minutes": duration_minutes,
        "prep_minutes": prep_minutes,
        "structure": structure,
        "parts": parts,
        "scoring": scoring,
    }


GOETHE_OFFICIAL_EXAMS = {
    "A1": {
        "title": "Goethe-Zertifikat A1: Start Deutsch 1",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzsd1.html",
        "is_modular": False,
        "official_version": "DFB 2025-09-01 · Modellsatz 2024-02",
        "pass_rule": "Examen no modular. Aprobado oficial con 60/100; el certificado informa 75 puntos en bloque escrito y 25 en Sprechen.",
        "official_note": "A1 oficial: Hören 20, Lesen 25, Schreiben 20 y Sprechen 15 minutos. La app reproduce la estructura exacta, pero los textos son originales.",
        "notes": [
            "Fuentes oficiales: página del examen, DFB, modellsatz y página de resultados de Goethe.",
            "La prueba real no es modular; la app permite entrenar cada sección por separado sin alterar tiempos ni tipos de tarea.",
        ],
        "resources": [
            _resource("Página oficial A1", "https://www.goethe.de/ins/de/en/prf/prf/gzsd1.html", "page"),
            _resource("Resultados oficiales A1", "https://www.goethe.de/en/spr/prf/pes/pas1.html", "page"),
            _resource("Practice materials A1", "https://www.goethe.de/ins/de/en/prf/prf/gzsd1/ueb.html", "page"),
            _resource("DFB A1 01-09-2025", "https://www.goethe.de/pro/relaunch/prf/en/Durchfuehrungsbestimmungen_A1_Start_Deutsch_1.pdf", "pdf"),
            _resource("Modellsatz A1", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_sd1/sd_1_modellsatz.pdf", "pdf"),
            _resource("Wortliste A1", "https://www.goethe.de/pro/relaunch/prf/de/A1_SD1_Wortliste_02.pdf", "pdf"),
            _resource("Manual A1", "https://www.goethe.de/pro/relaunch/prf/en/Pruefungsziele_Testbeschreibung_A1_SD1.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=25,
                prep_minutes=0,
                structure=[
                    "Teil 1: zwei kurze Texte, 5 Aussagen, Richtig/Falsch",
                    "Teil 2: Informationen/Hinweise zuordnen, 5 Aufgaben",
                    "Teil 3: kurze Alltagstexte, 5 Aussagen, Richtig/Falsch",
                ],
                parts=[
                    _part(key="a1_lesen_1", title="Teil 1 · Kurze Texte", instructions="Lesen Sie zwei kurze Texte und entscheiden Sie zu fünf Aussagen: Richtig oder Falsch.", task_types=["true_false"], recommended_minutes=8, item_count=5, response_format="Richtig/Falsch", item_kind="true_false"),
                    _part(key="a1_lesen_2", title="Teil 2 · Informationen finden", instructions="Lesen Sie kurze Hinweise und ordnen Sie die passende Information zu.", task_types=["matching"], recommended_minutes=8, item_count=5, response_format="Zuordnung", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f"]),
                    _part(key="a1_lesen_3", title="Teil 3 · Alltagstexte", instructions="Lesen Sie kurze Alltagstexte und entscheiden Sie zu fünf Aussagen: Richtig oder Falsch.", task_types=["true_false"], recommended_minutes=9, item_count=5, response_format="Richtig/Falsch", item_kind="true_false"),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Lösungsschlüssel Goethe", criteria=["Textverständnis", "Alltagsinformationen", "Detailerkennung"], notes=["Offiziell ist A1 nicht modular; 15/25 ist hier nur der Trainingsrichtwert für diese Teilsektion."]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=20,
                prep_minutes=0,
                structure=[
                    "Teil 1: kurze Gespräche/Ansagen, 6 MC-Aufgaben, zweimal hören",
                    "Teil 2: Mitteilungen/Ansagen, 4 Richtig/Falsch-Aufgaben",
                    "Teil 3: kurze Gespräche/Nachrichten, 5 MC-Aufgaben, zweimal hören",
                ],
                parts=[
                    _part(key="a1_hoeren_1", title="Teil 1 · Kurze Gespräche", instructions="Sie hören kurze Gespräche oder Ansagen. Wählen Sie bei jeder Aufgabe a, b oder c.", task_types=["multiple_choice"], recommended_minutes=7, item_count=6, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                    _part(key="a1_hoeren_2", title="Teil 2 · Mitteilungen", instructions="Sie hören kurze Mitteilungen oder Ansagen und entscheiden: Richtig oder Falsch.", task_types=["true_false"], recommended_minutes=6, item_count=4, response_format="Richtig/Falsch", audio_plays=1, item_kind="true_false"),
                    _part(key="a1_hoeren_3", title="Teil 3 · Kurze Nachrichten", instructions="Sie hören kurze Dialoge oder Nachrichten. Wählen Sie bei jeder Aufgabe a, b oder c.", task_types=["multiple_choice"], recommended_minutes=7, item_count=5, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Lösungsschlüssel Goethe", criteria=["Globalverstehen", "Detailverstehen", "Alltagskontext"], notes=["Offiziell ist A1 nicht modular; 15/25 ist hier nur el umbral de entrenamiento."]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=20,
                prep_minutes=0,
                structure=["Teil 1: Formular ausfüllen", "Teil 2: kurze persönliche Mitteilung schreiben"],
                parts=[
                    _part(key="a1_schreiben_1", title="Teil 1 · Formular", instructions="Tragen Sie persönliche Informationen passend in ein Formular ein.", task_types=["form"], recommended_minutes=7, item_count=1, response_format="Formular", item_kind="open_form", expected_words=20),
                    _part(key="a1_schreiben_2", title="Teil 2 · Kurze Mitteilung", instructions="Schreiben Sie eine kurze persönliche Mitteilung zu einer Alltagssituation.", task_types=["message"], recommended_minutes=13, item_count=1, response_format="Freier Kurztext", min_words=30, item_kind="open_message", expected_words=30),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Goethe-Bewertungsbogen", criteria=["Aufgabenbezug", "Verständlichkeit", "Sprachrichtigkeit"], notes=["Offiziell ist A1 nicht modular; la parte escrita cuenta dentro del bloque global de 75 puntos."]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=15,
                prep_minutes=0,
                structure=["Teil 1: sich vorstellen", "Teil 2: Fragen stellen und beantworten", "Teil 3: bitten und reagieren"],
                parts=[
                    _part(key="a1_sprechen_1", title="Teil 1 · Sich vorstellen", instructions="Stellen Sie sich mit einfachen Angaben zu Ihrer Person vor.", task_types=["open_answer"], recommended_minutes=4, item_count=1, response_format="Kurzvorstellung", item_kind="open_speaking", expected_words=25),
                    _part(key="a1_sprechen_2", title="Teil 2 · Fragen und Antworten", instructions="Stellen Sie einfache Fragen und beantworten Sie Fragen zu einem Alltagsthema.", task_types=["interaction"], recommended_minutes=5, item_count=1, response_format="Frage/Antwort", item_kind="open_speaking", expected_words=35),
                    _part(key="a1_sprechen_3", title="Teil 3 · Bitten und reagieren", instructions="Formulieren Sie eine Bitte und reagieren Sie passend auf eine andere Bitte.", task_types=["interaction"], recommended_minutes=6, item_count=1, response_format="Interaktion", item_kind="open_speaking", expected_words=35),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Zwei Prüfende", criteria=["Aufgabenbezug", "Interaktion", "Verständlichkeit"], notes=["A1 mündlich ist Teil der Gesamtprüfung und wird offiziell nicht separat zertifiziert."]),
            ),
        },
    },
    "A2": {
        "title": "Goethe-Zertifikat A2",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzsd2.html",
        "is_modular": False,
        "official_version": "DFB 2025-09-01 · Modellsatz Erwachsene aktuell verlinkt 2026",
        "pass_rule": "Examen no modular. Aprobado oficial con 60/100; mínimo 45/75 en el bloque escrito y 15/25 en Sprechen.",
        "official_note": "A2 oficial: Lesen 30, Hören 30, Schreiben 30 y Sprechen 15 minutos. La app usa exactamente esa estructura y esos tipos de tarea.",
        "notes": [
            "La página oficial y el Modellsatz confirman la misma estructura de partes y tiempos.",
            "El DFB indica que la variante adulta A2 y A2 Fit in Deutsch comparten el mismo formato básico.",
        ],
        "resources": [
            _resource("Página oficial A2", "https://www.goethe.de/ins/de/en/prf/prf/gzsd2.html", "page"),
            _resource("DFB A2 01-09-2025", "https://www.goethe.de/pro/relaunch/prf/en/Durchfuehrungsbestimmungen_A2.pdf", "pdf"),
            _resource("Modellsatz A2 Erwachsene", "https://www.goethe.de/pro/relaunch/prf/materialien/A2/A2_Modellsatz_Erwachsene.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=30,
                prep_minutes=0,
                structure=[
                    "Teil 1: Zeitungstext, 5 MC-Aufgaben",
                    "Teil 2: Informationstafel/Orientierung, 5 Zuordnungen",
                    "Teil 3: E-Mail, 5 MC-Aufgaben",
                    "Teil 4: Anzeigen zuordnen, 5 Aufgaben",
                ],
                parts=[
                    _part(key="a2_lesen_1", title="Teil 1 · Zeitungstext", instructions="Lesen Sie einen kurzen Zeitungstext und wählen Sie bei fünf Aufgaben a, b oder c.", task_types=["multiple_choice"], recommended_minutes=8, item_count=5, response_format="a/b/c", item_kind="mcq3"),
                    _part(key="a2_lesen_2", title="Teil 2 · Informationstafel", instructions="Lesen Sie eine Informationstafel und ordnen Sie die passende Information zu.", task_types=["matching"], recommended_minutes=7, item_count=5, response_format="Zuordnung", item_kind="matching_locations", choice_options=["Erdgeschoss", "1. Stock", "2. Stock", "3. Stock", "4. Stock"]),
                    _part(key="a2_lesen_3", title="Teil 3 · E-Mail", instructions="Lesen Sie eine E-Mail und wählen Sie bei fünf Aufgaben a, b oder c.", task_types=["multiple_choice"], recommended_minutes=8, item_count=5, response_format="a/b/c", item_kind="mcq3"),
                    _part(key="a2_lesen_4", title="Teil 4 · Anzeigen", instructions="Lesen Sie Anzeigen und ordnen Sie sie passenden Personen zu.", task_types=["matching"], recommended_minutes=7, item_count=5, response_format="Anzeige a-f", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f"]),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Lösungsschlüssel Goethe", criteria=["Textverständnis", "Orientierungslesen", "Detailerkennung"], notes=["Die Gesamtprüfung ist nicht modular; offiziell zählt Lesen in den 75 schriftlichen Punkten."]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=30,
                prep_minutes=0,
                structure=[
                    "Teil 1: 5 kurze Texte, MC, zweimal hören",
                    "Teil 2: 1 Gespräch, Bilder zuordnen",
                    "Teil 3: 5 kurze Gespräche, MC",
                    "Teil 4: 1 Interview, Ja/Nein",
                ],
                parts=[
                    _part(key="a2_hoeren_1", title="Teil 1 · Kurze Texte", instructions="Sie hören fünf kurze Texte. Wählen Sie jeweils a, b oder c.", task_types=["multiple_choice"], recommended_minutes=7, item_count=5, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                    _part(key="a2_hoeren_2", title="Teil 2 · Gespräch mit Bildauswahl", instructions="Sie hören ein Gespräch und ordnen fünf Aussagen das passende Bild zu.", task_types=["matching"], recommended_minutes=8, item_count=5, response_format="Bild a-i", audio_plays=1, item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h", "i"]),
                    _part(key="a2_hoeren_3", title="Teil 3 · Kurze Gespräche", instructions="Sie hören fünf kurze Gespräche und wählen jeweils a, b oder c.", task_types=["multiple_choice"], recommended_minutes=7, item_count=5, response_format="a/b/c", audio_plays=1, item_kind="mcq3"),
                    _part(key="a2_hoeren_4", title="Teil 4 · Interview", instructions="Sie hören ein Interview und entscheiden bei fünf Aussagen: Ja oder Nein.", task_types=["true_false"], recommended_minutes=8, item_count=5, response_format="Ja/Nein", audio_plays=2, item_kind="yes_no"),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Lösungsschlüssel Goethe", criteria=["Globalverstehen", "Detailverstehen", "Alltagssituationen"], notes=["Die Gesamtprüfung ist nicht modular; offiziell zählt Hören in den 75 schriftlichen Punkten."]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=30,
                prep_minutes=0,
                structure=["Teil 1: persönliche Mitteilung zur Kontaktpflege", "Teil 2: halb offizielle Mitteilung zur Handlungsregulierung"],
                parts=[
                    _part(key="a2_schreiben_1", title="Teil 1 · Persönliche Mitteilung", instructions="Schreiben Sie eine persönliche Nachricht, um Kontakt zu halten oder auf eine Alltagssituation zu reagieren.", task_types=["message"], recommended_minutes=15, item_count=1, response_format="Freier Kurztext", min_words=30, item_kind="open_message", expected_words=35),
                    _part(key="a2_schreiben_2", title="Teil 2 · Halb offizielle Mitteilung", instructions="Schreiben Sie eine halb offizielle Mitteilung und bearbeiten Sie alle Leitpunkte.", task_types=["message"], recommended_minutes=15, item_count=1, response_format="Freier Kurztext", min_words=30, item_kind="open_message", expected_words=35),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Goethe-Bewertungsbogen", criteria=["Aufgabenbezug", "Verständlichkeit", "sprachliche Richtigkeit"], notes=["Offiziell muss der gesamte schriftliche Block mindestens 45/75 erreichen."]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=15,
                prep_minutes=0,
                structure=["Teil 1: Fragen stellen und beantworten", "Teil 2: über ein Alltagsthema sprechen", "Teil 3: gemeinsam etwas planen"],
                parts=[
                    _part(key="a2_sprechen_1", title="Teil 1 · Fragen stellen", instructions="Stellen Sie Fragen zu Kartenimpulsen und beantworten Sie die Fragen Ihres Partners/Ihrer Partnerin.", task_types=["interaction"], recommended_minutes=5, item_count=1, response_format="Frage/Antwort", item_kind="open_speaking", expected_words=40),
                    _part(key="a2_sprechen_2", title="Teil 2 · Etwas erzählen", instructions="Sprechen Sie über ein Thema aus Ihrem Alltag und entwickeln Sie Ihren Beitrag verständlich weiter.", task_types=["open_answer"], recommended_minutes=5, item_count=1, response_format="Kurzvortrag", item_kind="open_speaking", expected_words=50),
                    _part(key="a2_sprechen_3", title="Teil 3 · Gemeinsam planen", instructions="Planen oder vereinbaren Sie gemeinsam etwas und reagieren Sie auf Vorschläge.", task_types=["interaction"], recommended_minutes=5, item_count=1, response_format="Interaktion", item_kind="open_speaking", expected_words=50),
                ],
                scoring=_scoring(max_points=25, pass_points=15, raters="Zwei Prüfende", criteria=["Aufgabenbezug", "Interaktion", "Verständlichkeit"]),
            ),
        },
    },
    "B1": {
        "title": "Goethe-Zertifikat B1",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzb1.html",
        "is_modular": True,
        "official_version": "DFB 2023-09-01 · Modellsatz Erwachsene offiziell enlazado en 2026",
        "pass_rule": "Examen modular. Cada módulo se aprueba por separado con 60/100.",
        "official_note": "B1 oficial modular: Lesen 65, Hören 40, Schreiben 60 y Sprechen 15 minutos con 15 minutos de preparación.",
        "notes": [
            "Las cuatro competencias pueden presentarse por separado o en conjunto.",
            "La app respeta el número oficial de partes y de tareas por módulo; las preguntas son originales.",
        ],
        "resources": [
            _resource("Página oficial B1", "https://www.goethe.de/ins/de/en/prf/prf/gzb1.html", "page"),
            _resource("Resultados oficiales B1", "https://www.goethe.de/en/spr/prf/pes/pab1.html", "page"),
            _resource("DFB B1", "https://www.goethe.de/resources/files/pdf315/durchfuehrungsbestimmungen-goethe-zertifikat-b1-erwachsene-und-jugendliche.pdf", "pdf"),
            _resource("Modellsatz B1 Erwachsene", "https://www.goethe.de/pro/relaunch/prf/materialien/B1/b1_modellsatz_erwachsene.pdf", "pdf"),
            _resource("Wortliste B1", "https://www.goethe.de/pro/relaunch/prf/de/Goethe-Zertifikat_B1_Wortliste.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=65,
                prep_minutes=0,
                structure=[
                    "Teil 1: Korrespondenz lesen, 6 Richtig/Falsch-Aufgaben",
                    "Teil 2: Presse-/Sachtext, 3 MC-Aufgaben",
                    "Teil 3: Zur Orientierung lesen, 7 Zuordnungen",
                    "Teil 4: Kommentare/Meinungen, 7 Ja/Nein-Aufgaben",
                    "Teil 5: schriftliche Anweisung verstehen, 4 MC-Aufgaben",
                ],
                parts=[
                    _part(key="b1_lesen_1", title="Teil 1 · Korrespondenz", instructions="Lesen Sie einen Text und entscheiden Sie bei sechs Aussagen: Richtig oder Falsch.", task_types=["true_false"], recommended_minutes=10, item_count=6, response_format="Richtig/Falsch", item_kind="true_false"),
                    _part(key="b1_lesen_2", title="Teil 2 · Presseartikel", instructions="Lesen Sie einen Pressetext und wählen Sie bei drei Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=20, item_count=3, response_format="a/b/c", item_kind="mcq3"),
                    _part(key="b1_lesen_3", title="Teil 3 · Orientierung", instructions="Ordnen Sie Situationen passenden Anzeigen oder Angeboten zu.", task_types=["matching"], recommended_minutes=10, item_count=7, response_format="Anzeige A-J", item_kind="matching_letters", choice_options=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "0"]),
                    _part(key="b1_lesen_4", title="Teil 4 · Meinungen", instructions="Lesen Sie Kommentare und entscheiden Sie bei sieben Personen: Ja oder Nein.", task_types=["true_false"], recommended_minutes=15, item_count=7, response_format="Ja/Nein", item_kind="yes_no"),
                    _part(key="b1_lesen_5", title="Teil 5 · Anweisung", instructions="Lesen Sie die Aufgaben und den Text dazu. Wählen Sie bei vier Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=10, item_count=4, response_format="a/b/c", item_kind="mcq3"),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Textverständnis", "Schlussfolgern", "Orientierungslesen"]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=40,
                prep_minutes=0,
                structure=[
                    "Teil 1: 5 kurze Texte, je 2 Aufgaben, zweimal hören",
                    "Teil 2: 1 Text, 5 MC-Aufgaben",
                    "Teil 3: 1 Gespräch, 7 Richtig/Falsch-Aufgaben",
                    "Teil 4: 1 Diskussion, 8 Zuordnungen, zweimal hören",
                ],
                parts=[
                    _part(key="b1_hoeren_1", title="Teil 1 · Kurze Texte", instructions="Sie hören fünf kurze Texte. Zu jedem Text lösen Sie zwei Aufgaben.", task_types=["multiple_choice"], recommended_minutes=8, item_count=10, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                    _part(key="b1_hoeren_2", title="Teil 2 · Ein Text", instructions="Sie hören einen Text einmal und wählen bei fünf Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=10, item_count=5, response_format="a/b/c", audio_plays=1, item_kind="mcq3"),
                    _part(key="b1_hoeren_3", title="Teil 3 · Gespräch", instructions="Sie hören ein Gespräch einmal und entscheiden bei sieben Aussagen: Richtig oder Falsch.", task_types=["true_false"], recommended_minutes=10, item_count=7, response_format="Richtig/Falsch", audio_plays=1, item_kind="true_false"),
                    _part(key="b1_hoeren_4", title="Teil 4 · Diskussion", instructions="Sie hören eine Diskussion zweimal und ordnen acht Aussagen Sprecherinnen und Sprechern zu.", task_types=["matching"], recommended_minutes=12, item_count=8, response_format="Zuordnung", audio_plays=2, item_kind="matching_speakers", choice_options=["A", "B", "C", "D"]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Globalverstehen", "Detailverstehen", "Sprecherzuordnung"]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=60,
                prep_minutes=0,
                structure=["Teil 1: E-Mail / persönliche Mitteilung", "Teil 2: Diskussionsbeitrag", "Teil 3: E-Mail / funktionale Mitteilung"],
                parts=[
                    _part(key="b1_schreiben_1", title="Teil 1 · E-Mail", instructions="Schreiben Sie eine persönliche Mitteilung oder E-Mail und bearbeiten Sie alle Leitpunkte.", task_types=["message"], recommended_minutes=20, item_count=1, response_format="Freier Text", item_kind="open_message", expected_words=80),
                    _part(key="b1_schreiben_2", title="Teil 2 · Diskussionsbeitrag", instructions="Schreiben Sie einen Diskussionsbeitrag und begründen Sie Ihre Meinung mit Beispielen.", task_types=["forum_post"], recommended_minutes=20, item_count=1, response_format="Freier Text", item_kind="open_message", expected_words=100),
                    _part(key="b1_schreiben_3", title="Teil 3 · Funktionale Mitteilung", instructions="Schreiben Sie eine zweite E-Mail oder Mitteilung in klarem, situationspassendem Register.", task_types=["message"], recommended_minutes=20, item_count=1, response_format="Freier Text", item_kind="open_message", expected_words=80),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei geschulte Bewertende", criteria=["Aufgabenbezug", "Textaufbau", "Wortschatz", "Sprachrichtigkeit"]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=15,
                prep_minutes=15,
                structure=["Teil 1: gemeinsam etwas planen, circa 3 Minuten", "Teil 2: Thema präsentieren, circa 3 Minuten", "Teil 3: über beide Themen sprechen, circa 2 Minuten"],
                parts=[
                    _part(key="b1_sprechen_1", title="Teil 1 · Gemeinsam planen", instructions="Planen Sie gemeinsam mit Ihrer Gesprächspartnerin/Ihrem Gesprächspartner etwas und beziehen Sie sich auf Leitpunkte.", task_types=["interaction"], recommended_minutes=3, item_count=1, response_format="Interaktion", item_kind="open_speaking", expected_words=60),
                    _part(key="b1_sprechen_2", title="Teil 2 · Präsentation", instructions="Präsentieren Sie ein Thema strukturiert und verständlich.", task_types=["presentation"], recommended_minutes=3, item_count=1, response_format="Kurzpräsentation", item_kind="open_speaking", expected_words=90),
                    _part(key="b1_sprechen_3", title="Teil 3 · Nachfragen und reagieren", instructions="Sprechen Sie über Ihr Thema und das Thema Ihres Partners/Ihrer Partnerin und reagieren Sie auf Rückfragen.", task_types=["interaction"], recommended_minutes=2, item_count=1, response_format="Interaktion", item_kind="open_speaking", expected_words=60),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei Prüfende", criteria=["Aufgabenbezug", "Interaktion", "Verständlichkeit", "sprachliche Mittel"]),
            ),
        },
    },
    "B2": {
        "title": "Goethe-Zertifikat B2",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzb2.html",
        "is_modular": True,
        "official_version": "DFB 2025-09-01 · Modellsatz Erwachsene 2025-08",
        "pass_rule": "Examen modular. Cada módulo se aprueba por separado con 60/100.",
        "official_note": "B2 oficial modular: Lesen 65, Hören 40, Schreiben 75 y Sprechen 15 minutos con 15 minutos de preparación.",
        "notes": [
            "La documentación oficial 2025 mantiene B2 como examen modular.",
            "La app usa el reparto oficial de partes, tiempos y formatos; los textos y audios son originales.",
        ],
        "resources": [
            _resource("Página oficial B2", "https://www.goethe.de/ins/de/en/prf/prf/gzb2.html", "page"),
            _resource("Resultados oficiales B2", "https://www.goethe.de/en/spr/prf/pes/pab2.html", "page"),
            _resource("DFB B2 01-09-2025", "https://www.goethe.de/pro/relaunch/prf/en/Durchfuehrungsbestimmungen_B2.pdf", "pdf"),
            _resource("Modellsatz B2 Erwachsene", "https://www.goethe.de/pro/relaunch/prf/materialien/B2/b2_modellsatz_erwachsene.pdf", "pdf"),
            _resource("Beschreibung der Prüfung B2", "https://www.goethe.de/pro/relaunch/prf/en/Pruefungsziele_Testbeschreibung_B2.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=65,
                prep_minutes=0,
                structure=[
                    "Teil 1: Forum / Standpunkte, 9 Zuordnungen",
                    "Teil 2: Sätze in Lücken einsetzen, 6 Aufgaben",
                    "Teil 3: Sachtext / Artikel, 6 MC-Aufgaben",
                    "Teil 4: Meinungsäußerungen Überschriften zuordnen, 6 Aufgaben",
                    "Teil 5: Studienordnung/Inhaltsverzeichnis, 3 Zuordnungen",
                ],
                parts=[
                    _part(key="b2_lesen_1", title="Teil 1 · Standpunkte verstehen", instructions="Ordnen Sie Aussagen den passenden Personen zu. Personen können mehrfach gewählt werden.", task_types=["matching"], recommended_minutes=18, item_count=9, response_format="Person a-d", item_kind="matching_letters", choice_options=["a", "b", "c", "d"]),
                    _part(key="b2_lesen_2", title="Teil 2 · Lückentext", instructions="Setzen Sie passende Sätze in die Lücken eines Artikels ein.", task_types=["matching"], recommended_minutes=12, item_count=6, response_format="Satz a-h", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h"]),
                    _part(key="b2_lesen_3", title="Teil 3 · Artikel", instructions="Lesen Sie einen Zeitungs- oder Zeitschriftenartikel und wählen Sie die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=12, item_count=6, response_format="a/b/c", item_kind="mcq3"),
                    _part(key="b2_lesen_4", title="Teil 4 · Überschriften zuordnen", instructions="Ordnen Sie Meinungsäußerungen passenden Überschriften zu.", task_types=["matching"], recommended_minutes=12, item_count=6, response_format="Zuordnung", item_kind="matching_headings", choice_options=["A", "B", "C", "D", "E", "F", "0"]),
                    _part(key="b2_lesen_5", title="Teil 5 · Ordnung und Struktur", instructions="Ordnen Sie Überschriften Abschnitten oder Paragraphen zu.", task_types=["matching"], recommended_minutes=6, item_count=3, response_format="Zuordnung", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h"]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Textverständnis", "Standpunkte erkennen", "Informationsstruktur"]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=40,
                prep_minutes=0,
                structure=[
                    "Teil 1: 5 Gespräche/Äußerungen, je 2 Aufgaben",
                    "Teil 2: Radiointerview, 6 MC-Aufgaben",
                    "Teil 3: Radiogespräch mit mehreren Personen, 6 Sprecherzuordnungen",
                    "Teil 4: Vortrag, 8 MC-Aufgaben",
                ],
                parts=[
                    _part(key="b2_hoeren_1", title="Teil 1 · Kurze Gespräche und Äußerungen", instructions="Sie hören fünf Gespräche oder Äußerungen. Zu jedem Text lösen Sie zwei Aufgaben.", task_types=["multiple_choice"], recommended_minutes=8, item_count=10, response_format="a/b/c", audio_plays=1, item_kind="mcq3"),
                    _part(key="b2_hoeren_2", title="Teil 2 · Radiointerview", instructions="Sie hören ein Interview mit einer Persönlichkeit aus Wissenschaft oder Öffentlichkeit und wählen die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=10, item_count=6, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                    _part(key="b2_hoeren_3", title="Teil 3 · Gespräch mit mehreren Personen", instructions="Sie hören ein Gespräch mit mehreren Personen und ordnen Aussagen den Sprechenden zu.", task_types=["matching"], recommended_minutes=10, item_count=6, response_format="Zuordnung", audio_plays=1, item_kind="matching_speakers", choice_options=["a", "b", "c", "d"]),
                    _part(key="b2_hoeren_4", title="Teil 4 · Vortrag", instructions="Sie hören einen kurzen Vortrag und wählen die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=12, item_count=8, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Globalverstehen", "Detailverstehen", "Sprecherintention"]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=75,
                prep_minutes=0,
                structure=["Teil 1: Forumsbeitrag, circa 150 Wörter", "Teil 2: Nachricht in beruflichem Kontext, circa 100 Wörter"],
                parts=[
                    _part(key="b2_schreiben_1", title="Teil 1 · Forumsbeitrag", instructions="Schreiben Sie einen Forumsbeitrag mit Einleitung, Schluss und vollständiger Bearbeitung aller Leitpunkte.", task_types=["forum_post"], recommended_minutes=50, item_count=1, response_format="Freier Text", min_words=150, item_kind="open_message", expected_words=150, notes=["Offizielle Wortvorgabe im Modellsatz: circa 150 Wörter."]),
                    _part(key="b2_schreiben_2", title="Teil 2 · Nachricht", instructions="Schreiben Sie eine adressatenorientierte Nachricht im beruflichen oder halb formellen Kontext.", task_types=["message"], recommended_minutes=25, item_count=1, response_format="Freier Text", min_words=100, item_kind="open_message", expected_words=100, notes=["Offizielle Wortvorgabe im Modellsatz: circa 100 Wörter."]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei geschulte Bewertende", criteria=["Aufgabenerfüllung", "kommunikative Gestaltung", "Korrektheit", "Wortschatz"]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=15,
                prep_minutes=15,
                structure=["Teil 1: kurzer Vortrag plus Nachfragen, circa 4 Minuten", "Teil 2: Diskussion, circa 5 Minuten"],
                parts=[
                    _part(key="b2_sprechen_1", title="Teil 1 · Vortrag", instructions="Halten Sie einen kurzen Vortrag zu einem gewählten Thema und sprechen Sie anschließend mit Ihrer Gesprächspartnerin/Ihrem Gesprächspartner darüber.", task_types=["presentation"], recommended_minutes=4, item_count=1, response_format="Kurzvortrag", item_kind="open_speaking", expected_words=110),
                    _part(key="b2_sprechen_2", title="Teil 2 · Diskussion", instructions="Tauschen Sie in einer Diskussion Standpunkte aus, reagieren Sie auf Argumente und vertreten Sie Ihre Meinung.", task_types=["discussion"], recommended_minutes=5, item_count=1, response_format="Diskussion", item_kind="open_speaking", expected_words=120),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei Prüfende", criteria=["Aufgabenerfüllung", "Interaktion", "Verständlichkeit", "sprachliche Gestaltung"]),
            ),
        },
    },
    "C1": {
        "title": "Goethe-Zertifikat C1",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzc1.html",
        "is_modular": True,
        "official_version": "Modellsatz modular desde 2024-01-01 · DFB 2025-09-01",
        "pass_rule": "Examen modular. Cada módulo se aprueba por separado con 60/100.",
        "official_note": "C1 oficial actual: examen modular con Lesen 65, Hören 40, Schreiben 75 y Sprechen 20 minutos con 20 minutos de preparación.",
        "notes": [
            "La versión actual es modular. La documentación oficial de 2025 cerró la transición desde el formato no modular anterior.",
            "La escala oficial de resultados del módulo usa también medias notas: 89,5-80, 79,5-70, etc.",
        ],
        "resources": [
            _resource("Página oficial C1", "https://www.goethe.de/ins/de/en/prf/prf/gzc1.html", "page"),
            _resource("Resultados oficiales C1", "https://www.goethe.de/en/spr/prf/pes/pac1.html", "page"),
            _resource("DFB C1 01-09-2025", "https://www.goethe.de/pro/relaunch/prf/cn/Durchfuehrungsbestimmungen_C1.pdf", "pdf"),
            _resource("Modellsatz C1 modular", "https://www.goethe.de/pro/relaunch/prf/materialien/C1_modular/c1-modular_modellsatz.pdf", "pdf"),
            _resource("Handbuch C1", "https://www.goethe.de/pro/relaunch/prf/en/Handbuch_Pruefungsziele_Testbeschreibung_C1.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=65,
                prep_minutes=0,
                structure=[
                    "Teil 1: Lückentext / Ausdruckswahl, 8 Aufgaben",
                    "Teil 2: Sachtext, 7 MC-Aufgaben",
                    "Teil 3: Sätze in Lücken einsetzen, 8 Aufgaben",
                    "Teil 4: Fachbeiträge / Positionen zuordnen, 7 Aufgaben",
                ],
                parts=[
                    _part(key="c1_lesen_1", title="Teil 1 · Lückentext", instructions="Lesen Sie einen Artikel und wählen Sie für jede Lücke die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=10, item_count=8, response_format="a/b/c/d", item_kind="mcq4"),
                    _part(key="c1_lesen_2", title="Teil 2 · Artikel", instructions="Lesen Sie einen komplexeren Artikel und wählen Sie bei sieben Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=20, item_count=7, response_format="a/b/c/d", item_kind="mcq4"),
                    _part(key="c1_lesen_3", title="Teil 3 · Lücken mit Sätzen", instructions="Setzen Sie passende Sätze in die Lücken eines Kommentars ein. Zwei Sätze passen nicht.", task_types=["matching"], recommended_minutes=20, item_count=8, response_format="Satz a-j", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]),
                    _part(key="c1_lesen_4", title="Teil 4 · Positionen zuordnen", instructions="Lesen Sie Fachbeiträge und ordnen Sie Aussagen den Autorinnen und Autoren zu. Zwei Aussagen passen nicht.", task_types=["matching"], recommended_minutes=15, item_count=7, response_format="Autor a-d", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "0"]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Argumentationsstruktur", "Nuancen", "Detailverstehen"]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=40,
                prep_minutes=0,
                structure=[
                    "Teil 1: Podcast / Zuordnung, 6 Aufgaben",
                    "Teil 2: Radiointerview, 9 MC-Aufgaben",
                    "Teil 3: Gespräch in vier Abschnitten, 8 MC-Aufgaben",
                    "Teil 4: Vortrag, 7 MC-Aufgaben",
                ],
                parts=[
                    _part(key="c1_hoeren_1", title="Teil 1 · Podcast", instructions="Sie hören einen Podcast und ordnen Aussagen passenden Themen oder Büchern zu.", task_types=["matching"], recommended_minutes=7, item_count=6, response_format="Zuordnung", audio_plays=1, item_kind="matching_letters", choice_options=["A", "B", "C", "D", "E", "F"]),
                    _part(key="c1_hoeren_2", title="Teil 2 · Radiointerview", instructions="Sie hören ein Radiointerview zweimal und wählen bei neun Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=11, item_count=9, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                    _part(key="c1_hoeren_3", title="Teil 3 · Gespräch in Abschnitten", instructions="Sie hören ein Gespräch in vier Abschnitten jeweils einmal und wählen die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=10, item_count=8, response_format="a/b/c", audio_plays=1, item_kind="mcq3"),
                    _part(key="c1_hoeren_4", title="Teil 4 · Vortrag", instructions="Sie hören einen Vortrag zweimal und wählen bei sieben Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=12, item_count=7, response_format="a/b/c", audio_plays=2, item_kind="mcq3"),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Implikationen", "Detailverstehen", "Struktur des Hörtexts"]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=75,
                prep_minutes=0,
                structure=["Teil 1: Diskussionsbeitrag fürs Forum, circa 230 Wörter", "Teil 2: Nachricht/Beschwerde, circa 120 Wörter"],
                parts=[
                    _part(key="c1_schreiben_1", title="Teil 1 · Diskussionsbeitrag", instructions="Schreiben Sie einen Diskussionsbeitrag für ein Forum und bearbeiten Sie alle vier Leitpunkte in klarer Struktur.", task_types=["forum_post"], recommended_minutes=50, item_count=1, response_format="Freier Text", min_words=230, item_kind="open_message", expected_words=230, notes=["Offizielle Wortvorgabe im Modellsatz: circa 230 Wörter."]),
                    _part(key="c1_schreiben_2", title="Teil 2 · Nachricht / Beschwerde", instructions="Schreiben Sie eine formelle oder halb formelle Nachricht und reagieren Sie angemessen auf alle Leitpunkte.", task_types=["message"], recommended_minutes=25, item_count=1, response_format="Freier Text", min_words=120, item_kind="open_message", expected_words=120, notes=["Offizielle Wortvorgabe im Modellsatz: circa 120 Wörter."]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei geschulte Bewertende", criteria=["Aufgabengerechtheit", "Textaufbau", "Ausdruck", "Korrektheit"]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=20,
                prep_minutes=20,
                structure=["Teil 1: kurzer Vortrag plus Fragen, circa 7 Minuten", "Teil 2: Diskussion zu zweit, circa 5 Minuten"],
                parts=[
                    _part(key="c1_sprechen_1", title="Teil 1 · Vortrag", instructions="Wählen Sie eines von zwei Themen, halten Sie einen strukturierten Vortrag von circa 5 Minuten und beantworten Sie anschließend Fragen.", task_types=["presentation"], recommended_minutes=7, item_count=1, response_format="Vortrag + Nachfragen", item_kind="open_speaking", expected_words=180),
                    _part(key="c1_sprechen_2", title="Teil 2 · Diskussion", instructions="Führen Sie zu zweit eine Diskussion und reagieren Sie differenziert auf Argumente.", task_types=["discussion"], recommended_minutes=5, item_count=1, response_format="Diskussion", item_kind="open_speaking", expected_words=180),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei Prüfende", criteria=["Aufgabenrealisierung", "Interaktion", "Ausdruck", "Sprachrichtigkeit", "Verständlichkeit"]),
            ),
        },
    },
    "C2": {
        "title": "Goethe-Zertifikat C2: Großes Deutsches Sprachdiplom",
        "page_url": "https://www.goethe.de/ins/de/en/prf/prf/gzc2.html",
        "is_modular": True,
        "official_version": "Modellsatz 2025-09 · Modul Schreiben mit Kriterien ab 2026-01-01",
        "pass_rule": "Examen modular. Cada módulo se aprueba por separado con 60/100.",
        "official_note": "C2 oficial modular: Hören 35, Lesen 80, Schreiben 80 y Sprechen 15 minutos con 15 minutos de preparación.",
        "notes": [
            "Schreiben Teil 2 ofrece cuatro temas: dos generales y dos literarios vinculados a la lista oficial del año en curso.",
            "La app replica esa estructura de elección, pero no reutiliza textos oficiales protegidos.",
        ],
        "resources": [
            _resource("Página oficial C2", "https://www.goethe.de/ins/de/en/prf/prf/gzc2.html", "page"),
            _resource("Resultados oficiales C2", "https://www.goethe.de/en/spr/prf/pes/pac2.html", "page"),
            _resource("DFB C2", "https://www.goethe.de/pro/relaunch/prf/en/Durchfuehrungsbestimmungen_C2_neu.pdf", "pdf"),
            _resource("Modellsatz C2", "https://www.goethe.de/pro/relaunch/prf/materialien/C2/c2_modellsatz.pdf", "pdf"),
            _resource("Literaturliste C2", "https://www.goethe.de/pro/relaunch/prf/Literaturliste_C2/Goethe_Zertifikat_C2_Literaturliste.pdf", "pdf"),
            _resource("Manual C2", "https://www.goethe.de/pro/relaunch/prf/en/Pruefungsziele_Testbeschreibung_C2.pdf", "pdf"),
        ],
        "modules": {
            "lesen": _module(
                key="lesen",
                label="Lesen",
                duration_minutes=80,
                prep_minutes=0,
                structure=[
                    "Teil 1: Kommentar, 10 MC-Aufgaben",
                    "Teil 2: Aussagen Abschnitten zuordnen, 6 Aufgaben",
                    "Teil 3: Text mit entfernten Abschnitten, 6 Aufgaben",
                    "Teil 4: Anzeigen/Angebote zuordnen, 8 Aufgaben",
                ],
                parts=[
                    _part(key="c2_lesen_1", title="Teil 1 · Kommentar", instructions="Lesen Sie einen Kommentar und wählen Sie bei zehn Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=25, item_count=10, response_format="a/b/c/d", item_kind="mcq4"),
                    _part(key="c2_lesen_2", title="Teil 2 · Aussagen zuordnen", instructions="Ordnen Sie Aussagen den passenden Textabschnitten zu. Zwei Aussagen passen nicht.", task_types=["matching"], recommended_minutes=20, item_count=6, response_format="Abschnitt a-h", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h"]),
                    _part(key="c2_lesen_3", title="Teil 3 · Textrekonstruktion", instructions="Setzen Sie passende Textabschnitte in die Lücken einer Reportage ein.", task_types=["matching"], recommended_minutes=25, item_count=6, response_format="Abschnitt a-h", item_kind="matching_letters", choice_options=["a", "b", "c", "d", "e", "f", "g", "h"]),
                    _part(key="c2_lesen_4", title="Teil 4 · Angebote vergleichen", instructions="Ordnen Sie Aussagen passenden Anzeigen oder Angeboten zu.", task_types=["matching"], recommended_minutes=10, item_count=8, response_format="Anzeige a-d", item_kind="matching_letters", choice_options=["a", "b", "c", "d"]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Textanalyse", "implizite Bedeutung", "Informationsordnung"]),
            ),
            "hoeren": _module(
                key="hoeren",
                label="Hören",
                duration_minutes=35,
                prep_minutes=0,
                structure=[
                    "Teil 1: 5 Radioausschnitte, je 3 Ja/Nein-Aufgaben",
                    "Teil 2: Gespräch, 5 Sprecherzuordnungen",
                    "Teil 3: Interview, 10 MC-Aufgaben",
                ],
                parts=[
                    _part(key="c2_hoeren_1", title="Teil 1 · Radiosendungen", instructions="Sie hören fünf Ausschnitte aus Radiosendungen. Zu jedem Ausschnitt gibt es drei Aussagen: Ja oder Nein.", task_types=["true_false"], recommended_minutes=12, item_count=15, response_format="Ja/Nein", audio_plays=1, item_kind="yes_no"),
                    _part(key="c2_hoeren_2", title="Teil 2 · Gespräch", instructions="Sie hören ein Gespräch und entscheiden, ob eine Meinungsäußerung von Person 1, Person 2 oder beiden stammt.", task_types=["matching"], recommended_minutes=5, item_count=5, response_format="Person 1 / Person 2 / beide", audio_plays=1, item_kind="matching_words", choice_options=["Person 1", "Person 2", "beide"]),
                    _part(key="c2_hoeren_3", title="Teil 3 · Interview", instructions="Sie hören ein Interview und wählen bei zehn Aufgaben die richtige Lösung.", task_types=["multiple_choice"], recommended_minutes=18, item_count=10, response_format="a/b/c", audio_plays=1, item_kind="mcq3"),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Lösungsschlüssel Goethe", criteria=["Feinverstehen", "Meinungsnuancen", "Haltung und Intention"]),
            ),
            "schreiben": _module(
                key="schreiben",
                label="Schreiben",
                duration_minutes=80,
                prep_minutes=0,
                structure=["Teil 1: Kurzreferat sprachlich überarbeiten, 20 Minuten", "Teil 2: 1 Thema aus 4 wählen, circa 350 Wörter, 60 Minuten"],
                parts=[
                    _part(key="c2_schreiben_1", title="Teil 1 · Kurzreferat überarbeiten", instructions="Formulieren Sie markierte Passagen eines Kurzreferats mit vorgegebenen Wörtern neu.", task_types=["transformation"], recommended_minutes=20, item_count=1, response_format="Umformung", item_kind="open_rewrite", expected_words=120),
                    _part(key="c2_schreiben_2", title="Teil 2 · Ausführlicher Text", instructions="Wählen Sie eines von vier Themen und schreiben Sie einen ausführlichen Leserbrief, eine E-Mail oder eine Buchbesprechung. Zwei Themen sind allgemein, zwei literaturbezogen.", task_types=["essay", "letter", "review"], recommended_minutes=60, item_count=1, response_format="Ausführlicher Text", min_words=350, item_kind="open_message", expected_words=350, notes=["Offizielle Wortvorgabe im Modellsatz: circa 350 Wörter.", "Im Original: zwei allgemeine und zwei literaturbezogene Themen."]),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei geschulte Bewertende", criteria=["Aufgabenbewältigung", "Textorganisation", "Sprachliche Präzision", "Stil"]),
            ),
            "sprechen": _module(
                key="sprechen",
                label="Sprechen",
                duration_minutes=15,
                prep_minutes=15,
                structure=["Teil 1: Produktion, circa 10 Minuten insgesamt", "Teil 2: Interaktion, circa 5 Minuten"],
                parts=[
                    _part(key="c2_sprechen_1", title="Teil 1 · Produktion", instructions="Wählen Sie eines von zwei Themen, halten Sie einen fünfminütigen Vortrag, wägen Sie Standpunkte ab und beantworten Sie Fragen.", task_types=["presentation"], recommended_minutes=10, item_count=1, response_format="Vortrag + Fragen", item_kind="open_speaking", expected_words=220),
                    _part(key="c2_sprechen_2", title="Teil 2 · Interaktion", instructions="Führen Sie eine Diskussion, vertreten Sie eine Position, reagieren Sie auf Gegenargumente und versuchen Sie zu überzeugen.", task_types=["discussion"], recommended_minutes=5, item_count=1, response_format="Diskussion", item_kind="open_speaking", expected_words=180),
                ],
                scoring=_scoring(max_points=100, pass_points=60, raters="Zwei Prüfende", criteria=["Argumentationsqualität", "Interaktion", "sprachliche Präzision", "Verständlichkeit"]),
            ),
        },
    },
}


OFFICIAL_PRACTICE_LIBRARY = {
    "A1": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pa1.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe exam training with PDF, listening media and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_sd1/sd_1_modellsatz.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp477/pruefungstraining_1_hoeren_a1_erwachsene-v2.mp4", "video"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/a1_sd1/", "digital"),
                ],
            ),
            _practice_set(
                "set_2",
                "Exam training 2",
                "Adults",
                "Second official A1 practice set from the Goethe exam training page.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_sd1/sd_1_uebungssatz01.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp475/pruefungstraining_2_hoeren_a1_erwachsene-v2.mp4", "video"),
                ],
            ),
            _practice_set(
                "set_3",
                "Exam training 3",
                "Adults",
                "Third official A1 practice set from the Goethe exam training page.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_sd1/sd_1_uebungssatz02.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_3_hoeren_a1_erwachsene.mp4", "video"),
                ],
            ),
            _practice_set(
                "fit_set_1",
                "Exam training 1",
                "Young people",
                "Official Goethe A1 Fit practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_fit/fit1_uebungssatz_01.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp475/pruefungstraining_1_hoeren_a1_jugendliche-v1.mp4", "video"),
                ],
            ),
            _practice_set(
                "fit_set_2",
                "Exam training 2",
                "Young people",
                "Second official Goethe A1 Fit practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A1_fit/fit1_uebungssatz_02.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp475/pruefungstraining_2_hoeren_a1_jugendliche-v1.mp4", "video"),
                ],
            ),
        ],
    },
    "A2": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pa2.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe A2 exam training with PDF, listening media and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A2/A2_Modellsatz_Erwachsene.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp475/pruefungstraining_1_hoeren_a2_erwachsene-v2.mp4", "video"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/a2_mod_2MX5/", "digital"),
                ],
            ),
            _practice_set(
                "set_2",
                "Exam training 2",
                "Adults",
                "Second official A2 practice set from the Goethe exam training page.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A2/A2_Uebungssatz_Erwachsene.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp310/pruefungstraining_2_hoeren_a2_erwachsene-v7.mp3", "audio"),
                ],
            ),
            _practice_set(
                "fit_set_1",
                "Exam training 1",
                "Young people",
                "Official Goethe A2 Fit practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A2_fit/A2_Modellsatz_Jugendliche.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_1_hoeren_a2_jugendliche-v1.mp4", "video"),
                ],
            ),
            _practice_set(
                "fit_set_2",
                "Exam training 2",
                "Young people",
                "Second official Goethe A2 Fit practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/A2_fit/A2_Uebungssatz_Jugendliche.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp310/pruefungstraining_2_hoeren_a2_jugendliche-v2.mp3", "audio"),
                ],
            ),
        ],
    },
    "B1": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pb1.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe B1 adults training set with PDF, listening media and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B1/b1_modellsatz_erwachsene.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_1_hoeren_b1_erwachsene-v1.mp4", "video"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/b1_mod/index.php", "digital"),
                ],
            ),
            _practice_set(
                "set_2",
                "Exam training 2",
                "Adults",
                "Second official B1 adults practice set from the Goethe exam training page.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B1/B1_Uebungssatz_Erwachsene.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_2_hoeren_b1_erwachsene-v1.mp4", "video"),
                ],
            ),
            _practice_set(
                "jugend_set_1",
                "Exam training 1",
                "Young people",
                "Official Goethe B1 practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B1/b1_modellsatz_jugend.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_1_hoeren_b1_jugendliche.mp4", "video"),
                ],
            ),
            _practice_set(
                "jugend_set_2",
                "Exam training 2",
                "Young people",
                "Second official Goethe B1 practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B1/B1_Uebungssatz_Jugendliche.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp310/pruefungstraining_2_hoeren_b1_jugendliche-v1.mp3", "audio"),
                ],
            ),
        ],
    },
    "B2": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pb2.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe B2 adults training set with PDF, listening media and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B2/b2_modellsatz_erwachsene.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp477/b2_modellsatz_rahmen_erwachsene-v15.mp4", "video"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/b2_mod_2MX6/index.php", "digital"),
                ],
            ),
            _practice_set(
                "jugend_set_1",
                "Exam training 1",
                "Young people",
                "Official Goethe B2 practice set for young people.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/B2/b2_modellsatz_jugendliche.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp310/pruefungstraining_1_hoeren_b2_jugendliche-v3.mp3", "audio"),
                ],
            ),
        ],
    },
    "C1": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pc1.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe C1 training set with PDF, listening audio and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/C1_modular/c1-modular_modellsatz.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp310/pruefungstraining_1_hoeren_c1-v1.mp3", "audio"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/c1mod/", "digital"),
                ],
            ),
        ],
    },
    "C2": {
        "practice_page_url": "https://www.goethe.de/ins/us/en/spr/prf/ueb/pc2.html",
        "practice_sets": [
            _practice_set(
                "set_1",
                "Exam training 1",
                "Adults",
                "Official Goethe C2 training set with PDF, listening media and accessible digital version.",
                "digital",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/C2/c2_modellsatz.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_1_hoeren_c2-v1.mp4", "video"),
                    _resource("Accessible digital training", "https://bfu.goethe.de/c2_mod/lesen.php", "digital"),
                ],
            ),
            _practice_set(
                "set_2",
                "Exam training 2",
                "Adults",
                "Second official C2 practice set from the Goethe exam training page.",
                "pdf",
                [
                    _resource("Official PDF", "https://www.goethe.de/pro/relaunch/prf/materialien/C2/c2-uebungssatz.pdf", "pdf"),
                    _resource("Official listening media", "https://goethemp4s.akamaized.net/resources/files/mp473/pruefungstraining_2_hoeren_c2-v1.mp4", "video"),
                ],
            ),
        ],
    },
}


MOCK_CALIBRATION_LIBRARY = {
    "A1": [
        "Orientiert sich an den von Goethe veröffentlichten A1-Prüfungstrainings 1 bis 3 für Erwachsene.",
        "Behält sehr kurze Texte, hochfrequenten Wortschatz und konkrete Alltagssituationen bei.",
        "Schreiben bleibt bei Formular und kurzer Mitteilung; Sprechen bleibt stark formelhaft und einfach.",
        "Weder Schlussfolgerungstiefe noch lexikalische Dichte gehen über die offiziellen Trainingssätze hinaus.",
    ],
    "A2": [
        "Orientiert sich an den offiziellen A2-Prüfungstrainings 1 und 2 sowie an der barrierefreien Digitalversion.",
        "Bildet Anzeigen, E-Mails, kurze Gespräche und funktionale Alltagssprache eng am Goethe-Muster nach.",
        "Schriftliche und mündliche Produktion bleiben kurz, klar und stark kontextgestützt.",
        "Die Schwierigkeit entwickelt A2 sicher aus, ohne in Richtung B1 zu kippen.",
    ],
    "B1": [
        "Orientiert sich an den offiziellen B1-Modellsätzen und Übungssätzen für Erwachsene.",
        "Bildet Leseaufgaben nach Teilen, Orientierungsaufgaben, kurze Diskussionen und funktional-opinionierende Texte nach.",
        "Die sprachliche Schwierigkeit bleibt im unabhängigen mittleren Bereich mit noch klar linearen Argumenten.",
        "Zusätzliche Verdichtung oder Abstraktion auf B2-Niveau wird bewusst vermieden.",
    ],
    "B2": [
        "Orientiert sich am offiziellen B2-Korpus für Erwachsene: Modellsatz, Hördatei und barrierefreies Digitaltraining.",
        "Bildet argumentierende Texte, Positionenzuordnung, Lücken mit Satzbausteinen und längere strukturierte Produktionen nach.",
        "Die Schwierigkeit verlangt detailliertes Verstehen, passenden Registergebrauch und tragfähige Argumentation auf B2-Niveau.",
        "Sie bleibt klar über B1, aber unter der Abstraktion und Verdichtung von C1.",
    ],
    "C1": [
        "Orientiert sich am offiziellen modularen C1-Modellsatz, der Hördatei und der barrierefreien Digitalversion.",
        "Bildet komplexe Artikel, feine Formulierungswahl, Debatte und registerkontrolliertes Schreiben nach.",
        "Die Schwierigkeit erhöht Nuancierung, Kohäsion und das Verstehen längerer Argumentationsstrukturen.",
        "Sie erreicht noch nicht die literarische und stilistische Extremdichte von C2.",
    ],
    "C2": [
        "Orientiert sich an den offiziellen C2-Modell- und Übungssätzen, den Hördateien und der von Goethe veröffentlichten Struktur.",
        "Bildet Feinanalysen, Textrekonstruktion, Umformulierungen und hochpräzise lange Produktionen nach.",
        "Die Kalibrierung richtet sich an Nuancen, Positionierung, Stil und fortgeschrittene Textorganisation aus.",
        "Das Niveau wird nicht vereinfacht, aber auch nicht künstlich über das offizielle Muster hinaus verschärft.",
    ],
}


GERMAN_VISIBLE_EXAM_COPY = {
    "A1": {
        "official_version": "DFB 2025-09-01 · Modellsatz 2024-02",
        "pass_rule": "Nicht modular. Offiziell bestanden mit 60/100 Punkten; das Zertifikat weist 75 Punkte für den schriftlichen Teil und 25 Punkte für Sprechen aus.",
        "official_note": "A1 offiziell: Hören 20, Lesen 25, Schreiben 20 und Sprechen 15 Minuten. Die App übernimmt diese Struktur und die Aufgabentypen exakt; die Inhalte bleiben originär.",
        "notes": [
            "Offizielle Quellen: Prüfungsseite, Durchführungsbestimmungen, Modellsatz und Goethe-Ergebnisseite.",
            "Die reale Prüfung ist nicht modular; die App erlaubt Modultraining, ohne Zeiten oder Aufgabentypen zu verändern.",
        ],
    },
    "A2": {
        "official_version": "DFB 2025-09-01 · aktuell verlinkter Erwachsenensatz 2026",
        "pass_rule": "Nicht modular. Offiziell bestanden mit 60/100 Punkten; mindestens 45/75 im schriftlichen Teil und 15/25 im Sprechen.",
        "official_note": "A2 offiziell: Lesen 30, Hören 30, Schreiben 30 und Sprechen 15 Minuten. Die App folgt genau dieser Struktur und diesen Aufgabentypen.",
        "notes": [
            "Prüfungsseite und Modellsatz bestätigen dieselbe Teile- und Zeitstruktur.",
            "Die Durchführungsbestimmungen nennen für die Erwachsenen- und Jugendvariante denselben Grundaufbau.",
        ],
    },
    "B1": {
        "official_version": "DFB 2023-09-01 · offizieller Erwachsenen-Modellsatz weiterhin verlinkt 2026",
        "pass_rule": "Modulare Prüfung. Jedes Modul wird separat mit mindestens 60/100 Punkten bestanden.",
        "official_note": "B1 offiziell modular: Lesen 65, Hören 40, Schreiben 60 und Sprechen 15 Minuten plus 15 Minuten Vorbereitungszeit.",
        "notes": [
            "Die vier Fertigkeiten können getrennt oder als Gesamtprüfung abgelegt werden.",
            "Die App übernimmt die offizielle Zahl der Teile und Aufgaben pro Modul; die Inhalte bleiben originär.",
        ],
    },
    "B2": {
        "official_version": "DFB 2025-09-01 · Modellsatz Erwachsene 2025-08",
        "pass_rule": "Modulare Prüfung. Jedes Modul wird separat mit mindestens 60/100 Punkten bestanden.",
        "official_note": "B2 offiziell modular: Lesen 65, Hören 40, Schreiben 75 und Sprechen 15 Minuten.",
        "notes": [
            "Die offizielle Struktur bleibt modular; die App spiegelt Reihenfolge, Dauer und Aufgabentypen exakt.",
            "Mocks bleiben klar als App-Material markiert und werden niemals als offizielle Goethe-Sätze ausgegeben.",
        ],
    },
    "C1": {
        "official_version": "DFB 2025-09-01 · modularer Modellsatz seit 2024 weltweit im Einsatz",
        "pass_rule": "Modulare Prüfung. Jedes Modul wird separat mit mindestens 60/100 Punkten bestanden.",
        "official_note": "C1 offiziell modular: Lesen 65, Hören circa 40, Schreiben 75 und Sprechen 20 Minuten.",
        "notes": [
            "Die heute gültige C1-Version ist modular; ältere Hinweise auf nicht modulare Varianten werden nicht mehr für das Training verwendet.",
            "Die App bildet die aktuelle Modulstruktur nach und trennt offizielle Materialien sauber von Mocks.",
        ],
    },
    "C2": {
        "official_version": "DFB 2025-09-01 · Modellsatz 2025-09 · Schreibkriterien seit 2026-01-01",
        "pass_rule": "Modulare Prüfung. Jedes Modul wird separat mit mindestens 60/100 Punkten bestanden.",
        "official_note": "C2 offiziell modular: Hören 35, Lesen 80, Schreiben 80 und Sprechen 15 Minuten.",
        "notes": [
            "Die offizielle C2-Struktur kombiniert hochpräzise Rezeption, Umformung und argumentativ-stilistische Produktion.",
            "Die App spiegelt diese Struktur, ohne offizielles Goethe-Material und eigens erzeugte Mocks zu vermischen.",
        ],
    },
}


def _germanize_resource_label(label: str) -> str:
    normalized = label.lower()
    if normalized.startswith("official pdf"):
        return "Offizielles PDF"
    if normalized.startswith("official listening media"):
        return "Offizielle Hördatei"
    if normalized.startswith("accessible digital training"):
        return "Barrierefreies digitales Training"
    if normalized.startswith("practice materials "):
        return f"Offizielle Übungsmaterialien {label.split()[-1]}"
    if normalized.startswith("manual "):
        return f"Handbuch {label.split()[-1]}"
    if normalized.startswith("official results ") or normalized.startswith("resultados oficiales "):
        return f"Offizielle Ergebnisse {label.split()[-1]}"
    if "oficial" in normalized and label.split()[-1] in GOETHE_OFFICIAL_EXAMS:
        return f"Offizielle Prüfungsseite {label.split()[-1]}"
    return label


def _germanize_practice_label(label: str) -> str:
    return label.replace("Exam training", "Prüfungstraining")


def _germanize_audience(label: str) -> str:
    if label == "Adults":
        return "Erwachsene"
    if label == "Young people":
        return "Jugendliche"
    return label


def _germanize_practice_description(level: str, practice_set: dict[str, object]) -> str:
    resources = practice_set.get("resources", [])
    has_digital = any(resource.get("resource_type") == "digital" for resource in resources)
    audience = _germanize_audience(str(practice_set.get("audience") or ""))
    audience_phrase = "für Jugendliche" if audience == "Jugendliche" else "für Erwachsene"
    fit_suffix = "-Fit" if "fit" in str(practice_set.get("key") or "") else ""
    set_number = str(practice_set.get("label") or "").split()[-1]
    ordinal = {"1": "Erster", "2": "Zweiter", "3": "Dritter"}.get(set_number, "Offizieller")
    if has_digital:
        return (
            f"Offizieller Goethe-{level}{fit_suffix}-Trainingssatz {audience_phrase} "
            "mit PDF, Hördatei und barrierefreier Digitalversion."
        )
    if ordinal == "Offizieller":
        return f"Offizieller Goethe-{level}{fit_suffix}-Trainingssatz {audience_phrase}."
    return f"{ordinal} offizieller Goethe-{level}{fit_suffix}-Trainingssatz {audience_phrase} von der Goethe-Prüfungstrainingsseite."


def _germanize_practice_set(level: str, practice_set: dict[str, object]) -> dict[str, object]:
    return {
        **practice_set,
        "label": _germanize_practice_label(str(practice_set["label"])),
        "audience": _germanize_audience(str(practice_set["audience"])),
        "description": _germanize_practice_description(level, practice_set),
        "resources": [
            {**resource, "label": _germanize_resource_label(str(resource["label"]))}
            for resource in practice_set.get("resources", [])
        ],
    }


for _level_key, _practice_payload in OFFICIAL_PRACTICE_LIBRARY.items():
    _visible_copy = GERMAN_VISIBLE_EXAM_COPY[_level_key]
    GOETHE_OFFICIAL_EXAMS[_level_key]["official_version"] = _visible_copy["official_version"]
    GOETHE_OFFICIAL_EXAMS[_level_key]["pass_rule"] = _visible_copy["pass_rule"]
    GOETHE_OFFICIAL_EXAMS[_level_key]["official_note"] = (
        f"{_visible_copy['official_note']} "
        "In der App öffnet das offizielle Goethe-Material direkt als PDF-, Audio- oder Digitalversion."
    )
    GOETHE_OFFICIAL_EXAMS[_level_key]["notes"] = list(_visible_copy["notes"])
    GOETHE_OFFICIAL_EXAMS[_level_key]["resources"] = [
        {**resource, "label": _germanize_resource_label(str(resource["label"]))}
        for resource in GOETHE_OFFICIAL_EXAMS[_level_key]["resources"]
    ]
    GOETHE_OFFICIAL_EXAMS[_level_key]["practice_page_url"] = _practice_payload["practice_page_url"]
    GOETHE_OFFICIAL_EXAMS[_level_key]["practice_sets"] = [
        _germanize_practice_set(_level_key, practice_set)
        for practice_set in _practice_payload["practice_sets"]
    ]
    GOETHE_OFFICIAL_EXAMS[_level_key]["mock_calibration"] = list(MOCK_CALIBRATION_LIBRARY[_level_key])
