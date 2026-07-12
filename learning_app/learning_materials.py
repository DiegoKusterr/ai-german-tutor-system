from __future__ import annotations

from typing import Any


TOPIC_ALIASES = {
    "airport": "airport",
    "flughafen": "airport",
    "reisen": "reisen",
    "reise": "reisen",
    "bewerbung": "bewerbung",
    "bewerbungsgespraech": "bewerbung",
    "bewerbungsgespräch": "bewerbung",
    "arbeit": "arbeit",
    "gesundheit": "gesundheit",
    "arzt": "gesundheit",
    "wohnung": "wohnung",
    "wohnen": "wohnung",
    "umwelt": "umwelt",
    "studium": "studium",
    "universität": "studium",
    "universitaet": "studium",
    "technik": "technik",
    "einkaufen": "einkaufen",
    "verbos irregulares": "unregelmaessige_verben",
    "unregelmäßige verben": "unregelmaessige_verben",
    "unregelmaessige verben": "unregelmaessige_verben",
}


TOPIC_SCENARIOS = {
    "airport": {
        "title": "Am Flughafen",
        "setting": "am Flughafen in Frankfurt",
        "person": "Laura",
        "goal": "den Koffer aufgeben und pünktlich einchecken",
        "issue": "ihr Ausweis steckt noch in der Jacke im Handgepäck",
        "time": "06:45 Uhr",
        "solution": "Sie findet den Ausweis rechtzeitig und geht direkt zum Gate.",
        "keywords": ["Flug", "Check-in", "Gate", "Ausweis", "Koffer"],
    },
    "reisen": {
        "title": "Eine Reise planen",
        "setting": "im Reisezentrum am Bahnhof",
        "person": "Mateo",
        "goal": "ein günstiges Ticket nach Berlin kaufen",
        "issue": "er weiß nicht, ob sich eine Reservierung lohnt",
        "time": "17:20 Uhr",
        "solution": "Er nimmt ein Sparpreis-Ticket mit Sitzplatzreservierung.",
        "keywords": ["Zug", "Ticket", "Reservierung", "Bahn", "Reise"],
    },
    "bewerbung": {
        "title": "Vor dem Bewerbungsgespräch",
        "setting": "im Büro einer Marketingfirma",
        "person": "Sofía",
        "goal": "sich überzeugend für ein Praktikum vorstellen",
        "issue": "sie ist sehr früh da und möchte professionell wirken",
        "time": "09:10 Uhr",
        "solution": "Sie stellt kluge Fragen zur Stelle und verweist auf passende Studienprojekte.",
        "keywords": ["Bewerbung", "Motivation", "Erfahrung", "Vorstellungsgespräch", "Praktikum"],
    },
    "arbeit": {
        "title": "Im Büro",
        "setting": "in einem kleinen Team-Meeting",
        "person": "Daniel",
        "goal": "ein Projekt realistisch planen",
        "issue": "das Team hat zu wenig Zeit für die Präsentation",
        "time": "11:30 Uhr",
        "solution": "Das Team priorisiert Aufgaben neu und verschiebt die Abgabe um zwei Tage.",
        "keywords": ["Projekt", "Team", "Termin", "Präsentation", "Aufgabe"],
    },
    "gesundheit": {
        "title": "Beim Arzt",
        "setting": "in einer Hausarztpraxis",
        "person": "Carmen",
        "goal": "wegen starker Halsschmerzen Hilfe bekommen",
        "issue": "sie hat seit drei Tagen Fieber und kaum geschlafen",
        "time": "08:25 Uhr",
        "solution": "Der Arzt empfiehlt Ruhe, Tee und zwei Tage Erholung.",
        "keywords": ["Arzt", "Termin", "Schmerzen", "Medikament", "Krankmeldung"],
    },
    "wohnung": {
        "title": "Wohnungssuche",
        "setting": "bei einer Wohnungsbesichtigung",
        "person": "Javier",
        "goal": "eine ruhige Wohnung in Uninähe finden",
        "issue": "die Miete ist höher als erwartet",
        "time": "18:00 Uhr",
        "solution": "Er fragt nach Nebenkosten und vergleicht noch eine zweite Option.",
        "keywords": ["Wohnung", "Miete", "Besichtigung", "Nebenkosten", "Vertrag"],
    },
}


WRITING_TASKS = {
    "email_formal": {
        "title": "Formelle E-Mail",
        "instruction": "Schreiben Sie eine formelle E-Mail. Reagieren Sie vollständig, höflich und klar auf alle Leitpunkte.",
        "rubric": ["Aufgabenbezug", "Kommunikative Gestaltung", "Textaufbau", "Sprachrichtigkeit"],
        "openers": ["Sehr geehrte Damen und Herren,", "Guten Tag,"],
    },
    "email_informal": {
        "title": "Informelle Nachricht",
        "instruction": "Schreiben Sie eine persönliche Nachricht in natürlichem, passendem Register.",
        "rubric": ["Aufgabenbezug", "Kohärenz", "Grammatik", "Wortschatz"],
        "openers": ["Hallo Anna,", "Liebe Lara,"],
    },
    "opinion": {
        "title": "Meinungsäußerung",
        "instruction": "Nehmen Sie Stellung, begründen Sie Ihre Meinung und nennen Sie Beispiele oder Konsequenzen.",
        "rubric": ["Argumentation", "Struktur", "Sprachrichtigkeit", "Wortschatz"],
        "openers": ["Meiner Meinung nach", "Ich bin der Ansicht, dass"],
    },
    "complaint": {
        "title": "Beschwerde",
        "instruction": "Beschreiben Sie das Problem sachlich und fordern Sie eine konkrete Lösung.",
        "rubric": ["Klarheit des Problems", "Struktur", "Register", "Sprachrichtigkeit"],
        "openers": ["Hiermit möchte ich mich beschweren,", "Ich schreibe Ihnen, weil"],
    },
    "application": {
        "title": "Bewerbungstext",
        "instruction": "Stellen Sie sich passend vor, nennen Sie relevante Erfahrung und Ihre Motivation.",
        "rubric": ["Aufgabenbezug", "Selbstpräsentation", "Register", "Sprachrichtigkeit"],
        "openers": ["mit großem Interesse habe ich", "hiermit bewerbe ich mich"],
    },
}


SPEAKING_SCENARIOS = {
    "roleplay": {
        "title": "Rollenspiel Alltag",
        "steps": [
            "Begrüßen Sie die andere Person und nennen Sie Ihr Anliegen.",
            "Reagieren Sie auf Rückfragen und machen Sie einen konkreten Vorschlag.",
            "Schließen Sie das Gespräch höflich und lösungsorientiert ab.",
        ],
    },
    "goethe_sprechen": {
        "title": "Goethe Sprechen",
        "steps": [
            "Stellen Sie sich kurz vor und reagieren Sie auf die Aufgabe.",
            "Entwickeln Sie eine begründete Position mit Beispiel.",
            "Interagieren Sie und machen Sie einen Vorschlag oder eine Empfehlung.",
        ],
    },
    "daily_conversation": {
        "title": "Alltagskonversation",
        "steps": [
            "Antworten Sie klar und natürlich.",
            "Fügen Sie ein persönliches Detail oder Beispiel hinzu.",
            "Stellen Sie eine passende Rückfrage.",
        ],
    },
}


EXAM_CRITERIA = {
    "lesen": ["Textverständnis", "Detailerkennung", "Schlussfolgerung"],
    "hoeren": ["Globalverstehen", "Detailverstehen", "Absicht und Kontext"],
    "schreiben": ["Aufgabenbezug", "Kommunikative Gestaltung", "Textaufbau", "Sprachrichtigkeit"],
    "sprechen": ["Aufgabenerfüllung", "Interaktion", "Ausdruck", "Sprachrichtigkeit", "Verständlichkeit"],
}


EXAM_STYLE_GUIDES = {
    "goethe": {
        "lesen": {
            "official_style_note": "Originales In-App-Material nach öffentlich beschriebener Goethe-Struktur; kein offizieller Prüfungsinhalt.",
            "source_framework": "Official Goethe structure + original simulation",
            "cefr_focus": ["Informationen gezielt finden", "Textabsicht erkennen", "Schlüsse aus dem Kontext ziehen"],
            "parts": [
                {"key": "lesen_teil_1", "title": "Teil 1 · Kurze Texte", "instructions": "Lesen Sie Mitteilungen, Hinweise oder Anzeigen und wählen Sie die passende Aussage.", "task_types": ["multiple choice", "true/false"], "recommended_minutes": 12},
                {"key": "lesen_teil_2", "title": "Teil 2 · Sachtext", "instructions": "Lesen Sie den längeren Text und beantworten Sie Detail- und Globalfragen.", "task_types": ["multiple choice", "short answer"], "recommended_minutes": 20},
            ],
        },
        "hoeren": {
            "official_style_note": "Textbasierte Höraufgaben mit Transkript-Hook für spätere Audiointegration.",
            "source_framework": "Official Goethe structure + transcript-based simulation",
            "cefr_focus": ["Kernaussagen erkennen", "relevante Details heraushören", "Sprecherabsicht verstehen"],
            "parts": [
                {"key": "hoeren_teil_1", "title": "Teil 1 · Kurze Gespräche", "instructions": "Lesen Sie das Transkript und beantworten Sie Fragen wie in einer Höraufgabe.", "task_types": ["multiple choice", "true/false"], "recommended_minutes": 15},
                {"key": "hoeren_teil_2", "title": "Teil 2 · Interview / Ansage", "instructions": "Arbeiten Sie Informationen und Sprecherintention aus dem Transkript heraus.", "task_types": ["multiple choice", "short answer"], "recommended_minutes": 20},
            ],
        },
        "schreiben": {
            "official_style_note": "Aufgabenbild nach veröffentlichten Goethe-Beschreibungen; Bewertung an offiziellen Kriterien orientiert.",
            "source_framework": "Published Goethe task descriptions + aligned rubric",
            "cefr_focus": ["Leitpunkte vollständig bearbeiten", "angemessenes Register wählen", "klar strukturiert schreiben"],
            "parts": [{"key": "schreiben_teil_1", "title": "Teil 1 · Schriftliche Aufgabe", "instructions": "Bearbeiten Sie alle Leitpunkte und strukturieren Sie den Text klar.", "task_types": ["open answer"], "recommended_minutes": 75}],
        },
        "sprechen": {
            "official_style_note": "Ablauf und Bewertungsdimensionen an veröffentlichte Goethe-Materialien angelehnt.",
            "source_framework": "Published Goethe speaking structure + aligned rubric",
            "cefr_focus": ["Aufgabe sicher erfüllen", "verständlich und flexibel reagieren", "Argumente entwickeln und interagieren"],
            "parts": [{"key": "sprechen_teil_1", "title": "Teil 1 · Reagieren und darstellen", "instructions": "Antworten Sie in 2-4 Sätzen und entwickeln Sie Ihre Idee weiter.", "task_types": ["open answer"], "recommended_minutes": 15}],
        },
    }
}


def _vocab(
    lemma: str,
    pos: str,
    translation: str,
    *,
    topic: str,
    level: str,
    gender: str | None = None,
    plural: str | None = None,
    example: str,
    collocation: str,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "lemma": lemma,
        "pos": pos,
        "translation": translation,
        "topic": topic,
        "level": level,
        "gender": gender,
        "plural": plural,
        "example": example,
        "collocation": collocation,
        "notes": notes,
    }


def _card(front: str, back: str, example: str, note: str = "") -> dict[str, Any]:
    return {"front": front, "back": back, "extra": {"example": example, "note": note}}


VOCAB_BANK = {
    "airport": [
        _vocab("der Ausweis", "N", "documento de identidad", topic="airport", level="A2", gender="der", plural="die Ausweise", example="Bitte zeigen Sie am Check-in Ihren Ausweis.", collocation="den Ausweis vorzeigen"),
        _vocab("das Gate", "N", "puerta de embarque", topic="airport", level="A2", gender="das", plural="die Gates", example="Unser Flug geht von Gate A12.", collocation="zum Gate gehen"),
        _vocab("aufgeben", "V", "facturar / entregar", topic="airport", level="A2", example="Wir geben zuerst den Koffer auf.", collocation="einen Koffer aufgeben", notes="trennbares Verb"),
        _vocab("die Sicherheitskontrolle", "N", "control de seguridad", topic="airport", level="B1", gender="die", plural="die Sicherheitskontrollen", example="Vor dem Gate müssen alle durch die Sicherheitskontrolle.", collocation="durch die Sicherheitskontrolle gehen"),
        _vocab("verspätet", "Adj", "retrasado", topic="airport", level="A2", example="Der Flug ist leider verspätet.", collocation="stark verspätet sein"),
    ],
    "bewerbung": [
        _vocab("die Bewerbung", "N", "solicitud / candidatura", topic="bewerbung", level="B1", gender="die", plural="die Bewerbungen", example="Ich sende meine Bewerbung morgen ab.", collocation="eine Bewerbung schreiben"),
        _vocab("die Berufserfahrung", "N", "experiencia laboral", topic="bewerbung", level="B1", gender="die", plural="die Berufserfahrungen", example="Im Lebenslauf steht meine bisherige Berufserfahrung.", collocation="Berufserfahrung sammeln"),
        _vocab("zuverlässig", "Adj", "fiable", topic="bewerbung", level="B1", example="Ich bin motiviert und zuverlässig.", collocation="als zuverlässig gelten"),
        _vocab("sich bewerben", "V", "presentarse / solicitar", topic="bewerbung", level="B1", example="Ich möchte mich für das Praktikum bewerben.", collocation="sich um eine Stelle bewerben", notes="reflexiv + um + Akk."),
        _vocab("die Stelle", "N", "puesto", topic="bewerbung", level="A2", gender="die", plural="die Stellen", example="Die Stelle passt gut zu meinem Profil.", collocation="eine Stelle anbieten"),
    ],
    "gesundheit": [
        _vocab("die Halsschmerzen", "N", "dolor de garganta", topic="gesundheit", level="A2", gender="die", plural="die Halsschmerzen", example="Ich habe seit gestern starke Halsschmerzen.", collocation="Halsschmerzen haben"),
        _vocab("die Untersuchung", "N", "revisión / exploración", topic="gesundheit", level="B1", gender="die", plural="die Untersuchungen", example="Der Arzt macht zuerst eine kurze Untersuchung.", collocation="eine Untersuchung machen"),
        _vocab("verschreiben", "V", "recetar", topic="gesundheit", level="B1", example="Die Ärztin verschreibt mir ein Medikament.", collocation="ein Medikament verschreiben"),
        _vocab("die Krankmeldung", "N", "baja médica", topic="gesundheit", level="B1", gender="die", plural="die Krankmeldungen", example="Für die Arbeit brauche ich eine Krankmeldung.", collocation="eine Krankmeldung bekommen"),
        _vocab("sich ausruhen", "V", "descansar", topic="gesundheit", level="A2", example="Sie sollten sich zwei Tage ausruhen.", collocation="sich im Bett ausruhen", notes="reflexiv + trennbar"),
    ],
    "unregelmaessige_verben": [
        _vocab("gehen - ging - gegangen", "Expr", "ir - fue - ido", topic="unregelmaessige_verben", level="A2", example="Ich bin gestern früh gegangen.", collocation="früh gehen"),
        _vocab("sehen - sah - gesehen", "Expr", "ver - vio - visto", topic="unregelmaessige_verben", level="A2", example="Hast du den Film schon gesehen?", collocation="etwas klar sehen"),
        _vocab("nehmen - nahm - genommen", "Expr", "coger - cogió - cogido", topic="unregelmaessige_verben", level="A2", example="Wir haben den Zug genommen.", collocation="sich Zeit nehmen"),
        _vocab("sprechen - sprach - gesprochen", "Expr", "hablar - habló - hablado", topic="unregelmaessige_verben", level="B1", example="Wir haben lange darüber gesprochen.", collocation="über etwas sprechen"),
        _vocab("werden - wurde - geworden", "Expr", "llegar a ser - se hizo - llegado a ser", topic="unregelmaessige_verben", level="B1", example="Es ist später kalt geworden.", collocation="nervös werden"),
    ],
}


STARTER_DECKS = {
    "irregular_verbs": {
        "name": "Starke Verben Kernset",
        "description": "Hochfrequente starke Verben mit Präteritum, Partizip II und Beispielsatz.",
        "level": "A2-B1",
        "tags": ["verben", "stark", "zeiten"],
        "cards": [
            _card("gehen", "ging - ist gegangen", "Ich bin früh gegangen."),
            _card("sehen", "sah - hat gesehen", "Wir haben den Film gesehen."),
            _card("sprechen", "sprach - hat gesprochen", "Er hat mit dem Chef gesprochen."),
            _card("nehmen", "nahm - hat genommen", "Sie hat ein Taxi genommen."),
            _card("finden", "fand - hat gefunden", "Ich habe endlich eine Wohnung gefunden."),
            _card("bleiben", "blieb - ist geblieben", "Wir sind zu Hause geblieben."),
            _card("schreiben", "schrieb - hat geschrieben", "Sie hat eine E-Mail geschrieben."),
            _card("fahren", "fuhr - ist/hat gefahren", "Wir sind nach Köln gefahren.", "Mit Fahrzeug/Bewegung meist `sein`."),
            _card("essen", "aß - hat gegessen", "Er hat schon gegessen."),
            _card("geben", "gab - hat gegeben", "Der Lehrer hat uns Hausaufgaben gegeben."),
            _card("kommen", "kam - ist gekommen", "Meine Schwester ist spät gekommen."),
            _card("werden", "wurde - ist geworden", "Es ist später kalt geworden."),
        ],
    },
    "articles_plural": {
        "name": "Artikel und Plural",
        "description": "Zentrale Nomen mit Genus, Plural und Beispielsatz.",
        "level": "A1-A2",
        "tags": ["nomen", "artikel", "plural"],
        "cards": [
            _card("der Beruf", "die Berufe", "Der Beruf ist interessant."),
            _card("die Bewerbung", "die Bewerbungen", "Die Bewerbung ist fertig."),
            _card("das Gespräch", "die Gespräche", "Das Gespräch war lang."),
            _card("der Ausweis", "die Ausweise", "Bitte zeigen Sie Ihren Ausweis."),
            _card("die Prüfung", "die Prüfungen", "Die Prüfung beginnt um neun."),
            _card("das Formular", "die Formulare", "Bitte füllen Sie das Formular aus."),
            _card("die Wohnung", "die Wohnungen", "Die Wohnung liegt zentral."),
            _card("das Ticket", "die Tickets", "Ich habe das Ticket schon gekauft."),
            _card("der Termin", "die Termine", "Wir haben morgen einen Termin."),
            _card("die Möglichkeit", "die Möglichkeiten", "Es gibt viele Möglichkeiten."),
        ],
    },
    "prepositions_cases": {
        "name": "Präpositionen nach Kasus",
        "description": "Feste Präpositionen mit Kasus und Mini-Beispiel.",
        "level": "A2",
        "tags": ["präpositionen", "kasus"],
        "cards": [
            _card("mit", "Dativ", "mit dem Zug"),
            _card("für", "Akkusativ", "für die Prüfung"),
            _card("ohne", "Akkusativ", "ohne einen Termin"),
            _card("seit", "Dativ", "seit dem Sommer"),
            _card("zu", "Dativ", "zum Bahnhof"),
            _card("nach", "Dativ", "nach Berlin"),
            _card("bei", "Dativ", "bei der Arbeit"),
            _card("durch", "Akkusativ", "durch die Stadt"),
            _card("gegen", "Akkusativ", "gegen den Plan"),
            _card("wegen", "Genitiv", "wegen des Wetters"),
        ],
    },
    "two_way_prepositions": {
        "name": "Wechselpräpositionen",
        "description": "Ort und Richtung mit Dativ oder Akkusativ unterscheiden.",
        "level": "A2-B1",
        "tags": ["wechselpräpositionen", "raum"],
        "cards": [
            _card("an", "wo? Dativ / wohin? Akkusativ", "an der Wand / an die Wand"),
            _card("in", "wo? Dativ / wohin? Akkusativ", "im Zimmer / ins Zimmer"),
            _card("auf", "wo? Dativ / wohin? Akkusativ", "auf dem Tisch / auf den Tisch"),
            _card("unter", "wo? Dativ / wohin? Akkusativ", "unter dem Bett / unter das Bett"),
            _card("über", "wo? Dativ / wohin? Akkusativ", "über dem Sofa / über das Sofa"),
            _card("vor", "wo? Dativ / wohin? Akkusativ", "vor dem Haus / vor das Haus"),
            _card("hinter", "wo? Dativ / wohin? Akkusativ", "hinter der Tür / hinter die Tür"),
            _card("zwischen", "wo? Dativ / wohin? Akkusativ", "zwischen den Stühlen / zwischen die Stühle"),
        ],
    },
    "verbs_with_prepositions": {
        "name": "Verben mit Präposition",
        "description": "Besonders wichtige Verb-Präposition-Pakete für B1 und B2.",
        "level": "B1-B2",
        "tags": ["verben", "präpositionen", "regime"],
        "cards": [
            _card("warten auf", "Akkusativ", "Wir warten auf den Bescheid."),
            _card("teilnehmen an", "Dativ", "Sie nimmt am Kurs teil."),
            _card("sich interessieren für", "Akkusativ", "Ich interessiere mich für Politik."),
            _card("denken an", "Akkusativ", "Denk an den Termin!"),
            _card("sprechen über", "Akkusativ", "Wir sprechen über das Problem."),
            _card("abhängen von", "Dativ", "Das hängt vom Wetter ab."),
            _card("sich freuen auf", "Akkusativ", "Ich freue mich auf den Urlaub."),
            _card("sich erinnern an", "Akkusativ", "Er erinnert sich an das Gespräch."),
            _card("bitten um", "Akkusativ", "Ich bitte um eine kurze Rückmeldung."),
            _card("sich kümmern um", "Akkusativ", "Sie kümmert sich um die Gäste."),
        ],
    },
    "connectors": {
        "name": "Konnektoren B1-B2",
        "description": "Zentrale Verknüpfungen für Ursache, Folge, Gegensatz und Struktur.",
        "level": "B1-B2",
        "tags": ["konnektoren", "writing", "speaking"],
        "cards": [
            _card("außerdem", "además", "Außerdem sparen wir Zeit."),
            _card("deshalb", "por eso", "Es regnet, deshalb bleiben wir zu Hause."),
            _card("trotzdem", "aun así", "Es war spät, trotzdem ging er noch spazieren."),
            _card("einerseits ... andererseits", "por un lado ... por otro lado", "Einerseits ist die Lösung billig, andererseits riskant."),
            _card("obwohl", "aunque", "Obwohl ich müde war, habe ich weitergelernt."),
            _card("denn", "porque", "Ich bleibe zu Hause, denn ich bin krank."),
            _card("während", "mientras que", "Während einige online lernen, bevorzugen andere Präsenzkurse."),
            _card("dennoch", "sin embargo / no obstante", "Die Lage ist schwierig, dennoch bleiben wir optimistisch."),
            _card("zunächst", "en primer lugar", "Zunächst möchte ich die Vorteile nennen."),
            _card("abschließend", "para concluir", "Abschließend möchte ich betonen, dass ..."),
        ],
    },
    "adjective_endings": {
        "name": "Adjektivendungen",
        "description": "Muster mit bestimmtem Artikel, unbestimmtem Artikel und Nullartikel.",
        "level": "B1",
        "tags": ["adjektive", "deklination"],
        "cards": [
            _card("der ... Tag", "der neue Tag", "der neue Vertrag"),
            _card("ein ... Termin", "ein wichtiger Termin", "ein langer Bericht"),
            _card("frisch ... Brot", "frisches Brot", "frisches Obst"),
            _card("mit ein ... Kollegin", "mit einer neuen Kollegin", "mit einem guten Plan"),
            _card("die ... Ergebnisse", "die aktuellen Ergebnisse", "die neuen Regeln"),
            _card("ohne ... Hilfe", "ohne professionelle Hilfe", "ohne klare Struktur"),
            _card("wegen schlecht ... Wetters", "wegen schlechten Wetters", "wegen schlechten Wetters"),
            _card("in neu ... Büros", "in neuen Büros", "in neuen Büros"),
        ],
    },
    "false_friends": {
        "name": "Falsche Freunde",
        "description": "Typische lexikalische Fallen für spanischsprachige Lernende.",
        "level": "B1",
        "tags": ["wortschatz", "fallen", "spanisch"],
        "cards": [
            _card("bekommen", "recibir, no `become`", "Ich habe eine E-Mail bekommen."),
            _card("eventuell", "quizá, no `eventualmente`", "Eventuell komme ich später."),
            _card("Chef", "jefe, no necesariamente cocinero", "Mein Chef arbeitet heute im Homeoffice."),
            _card("also", "o sea / así que", "Also, was machen wir jetzt?"),
            _card("Gymnasium", "instituto académico, no gimnasio", "Er besucht ein Gymnasium in Köln."),
            _card("giftig", "venenoso, no `gifted`", "Diese Pflanze ist giftig."),
            _card("aktuell", "actual / vigente, no `actualmente`", "Das ist ein aktuelles Thema."),
            _card("bald", "pronto, no `bald` inglés", "Ich rufe dich bald an."),
        ],
    },
    "alltag_a2_b1": {
        "name": "Alltag A2-B1",
        "description": "Nützlicher Kernwortschatz für Wohnen, Arbeit, Behörde und Alltag.",
        "level": "A2-B1",
        "tags": ["alltag", "wortschatz"],
        "cards": [
            _card("die Miete", "alquiler", "Die Miete ist zu hoch."),
            _card("der Vertrag", "contrato", "Ich habe den Vertrag unterschrieben."),
            _card("vereinbaren", "acordar / concertar", "Ich möchte einen Termin vereinbaren."),
            _card("pünktlich", "puntual", "Bitte kommen Sie pünktlich."),
            _card("die Unterlagen", "documentación", "Bringen Sie bitte alle Unterlagen mit."),
            _card("sich melden", "ponerse en contacto", "Ich melde mich morgen bei Ihnen."),
            _card("die Rückmeldung", "respuesta / feedback", "Ich warte auf Ihre Rückmeldung."),
            _card("kündigen", "rescindir / dimitir", "Er möchte seine Wohnung kündigen."),
        ],
    },
    "goethe_b2_redemittel": {
        "name": "Goethe B2 Redemittel",
        "description": "Nützliche Wendungen für Schreiben und Sprechen auf Goethe-B2-Niveau.",
        "level": "B2",
        "tags": ["goethe", "b2", "redemittel"],
        "cards": [
            _card("Meiner Ansicht nach ...", "en mi opinión ...", "Meiner Ansicht nach sollte man früher anfangen."),
            _card("Ein wichtiger Aspekt ist, dass ...", "un aspecto importante es que ...", "Ein wichtiger Aspekt ist, dass Zeit fehlt."),
            _card("Ich möchte betonen, dass ...", "quiero subrayar que ...", "Ich möchte betonen, dass Qualität zählt."),
            _card("Daraus ergibt sich, dass ...", "de ello se deduce que ...", "Daraus ergibt sich, dass wir umplanen müssen."),
            _card("Abschließend lässt sich sagen, dass ...", "en conclusión puede decirse que ...", "Abschließend lässt sich sagen, dass die Vorteile überwiegen."),
            _card("Könnten wir vielleicht ...?", "¿podríamos quizá ...?", "Könnten wir vielleicht einen anderen Termin finden?"),
            _card("Ich schlage vor, dass ...", "propongo que ...", "Ich schlage vor, dass wir zuerst die Kosten prüfen."),
            _card("Einerseits ..., andererseits ...", "por un lado ..., por otro lado ...", "Einerseits spart man Zeit, andererseits verliert man Flexibilität."),
        ],
    },
}


ROADMAP_KNOWLEDGE = {
    "A1": ["Alphabet, Aussprache, Umlaute und ß", "Artikel, Genus, Plural und Personalpronomen", "Präsens, Modalverben und Verbzweitstellung", "Alltagswortschatz zu Person, Wohnen, Arbeit, Einkauf und Zeit"],
    "A2": ["Perfekt, reflexive Verben und trennbare Verben", "Dativ, Wechselpräpositionen und Negation", "Nebensätze mit weil, dass, wenn, obwohl", "Wortschatz zu Reisen, Gesundheit, Arbeit und Behörden"],
    "B1": ["Relativsätze, Infinitiv mit zu, Verben mit Präpositionen", "Passiv, Adjektivdeklination und starke Verben", "Argumentation mit Grundkonnektoren und klarer Textstruktur", "Längere Schreibaufgaben und mündliche Interaktion mit Begründung"],
    "B2": ["Konjunktiv II, Nominalisierung und formeller Stil", "Kohäsion, Registerkontrolle und komplexe Konnektoren", "Prüfungsstrategien für Goethe B2 in allen vier Modulen", "Thematischer Wortschatz zu Gesellschaft, Arbeit, Bildung, Medien und Umwelt"],
    "C1": ["Konjunktiv I, indirekte Rede und gehobener Ausdruck", "Wortbildung, Kollokationen und Stilnuancen", "Verdichtung komplexer Inhalte in Schreiben und Sprechen", "Sichere Textanalyse und flexible Argumentation auf hohem Niveau"],
    "C2": ["Feinste Registersteuerung, stilistische Variation und textsortensichere Produktion", "Komplexe Argumentation mit Präzision, Abwägung und überzeugender Interaktion", "Souveräne Textanalyse, Rekonstruktion und Nuancenverstehen auf höchstem Niveau", "Prüfungsstrategien für Goethe C2 in allen vier Modulen inklusive Literaturbezug im Schreiben"],
}


GOAL_EXAM_LABELS = {
    "goethe_a1": "Goethe-Zertifikat A1",
    "goethe_a2": "Goethe-Zertifikat A2",
    "goethe_b1": "Goethe-Zertifikat B1",
    "goethe_b2": "Goethe-Zertifikat B2",
    "goethe_c1": "Goethe-Zertifikat C1",
    "goethe_c2": "Goethe-Zertifikat C2",
    "telc_b2": "telc Deutsch B2",
    "oesd_b2": "ÖSD B2",
    "testdaf": "TestDaF",
}
