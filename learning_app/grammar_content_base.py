from __future__ import annotations

from typing import Any


def _refs(*extra: str) -> list[str]:
    base = [
        "Duden. Die Grammatik",
        "Canoonet Grammatik",
        "IDS Grammis",
        "Hammer's German Grammar and Usage",
    ]
    return base + list(extra)


def _topic(
    *,
    label: str,
    level: str,
    category: str,
    summary: str,
    when_to_study: str,
    core_rules: list[str],
    deep_dive: list[str],
    exceptions: list[str],
    examples: list[str],
    common_mistakes: list[str],
    memory_hook: str,
    related_topics: list[str],
) -> dict[str, Any]:
    return {
        "label": label,
        "level": level,
        "category": category,
        "summary": summary,
        "when_to_study": when_to_study,
        "core_rules": core_rules,
        "deep_dive": deep_dive,
        "exceptions": exceptions,
        "examples": examples,
        "common_mistakes": common_mistakes,
        "memory_hook": memory_hook,
        "related_topics": related_topics,
        "references": _refs(),
    }


GRAMMAR_CURRICULUM_BASE: dict[str, dict[str, Any]] = {
    "aussprache_und_alphabet": _topic(
        label="Aussprache und Alphabet",
        level="A1",
        category="Aussprache & Schrift",
        summary="Grundlage für Laut-Buchstaben-Zuordnung, Wortakzent und zentrale Klangmuster des Deutschen.",
        when_to_study="Direkt am Anfang und später bei jeder Unsicherheit in Aussprache oder Diktat.",
        core_rules=[
            "Lautgruppen wie `sch`, `sp`, `st`, `ie`, `ei`, `eu`, `äu` lernst du als Einheit.",
            "Vokallänge ist bedeutungsrelevant.",
            "Wortakzent und Satzmelodie sind Teil der Verständlichkeit.",
        ],
        deep_dive=[
            "Deutsch wird nicht einfach buchstabengetreu gelesen; Mustererkennung ist viel wichtiger als Einzellauttraining.",
            "Besonders wichtig sind `ich`- und `ach`-Laut, die Unterscheidung von langen und kurzen Vokalen sowie die Aussprache von `r` im Standarddeutschen.",
            "Lautes Lesen mit kurzen Modellphrasen verbessert gleichzeitig Aussprache, Orthografie und Hörverstehen.",
        ],
        exceptions=[
            "Eigennamen und Fremdwörter können vom typischen Lautbild abweichen.",
            "Die Aussprache des `r` variiert regional.",
        ],
        examples=[
            "ich, ach, Schule, sprechen, mein, heute",
            "Wie heißt du und wie schreibt man deinen Namen?",
            "Die Schule beginnt heute um acht Uhr.",
        ],
        common_mistakes=[
            "`ie` als zwei Silben zu sprechen.",
            "`sp` und `st` am Wortanfang spanisch auszusprechen.",
            "`ü` mit `u` zu verwechseln.",
        ],
        memory_hook="Lerne Klangpakete, nicht Einzelbuchstaben.",
        related_topics=["umlaute_und_ss", "fragewoerter_und_fragesaetze"],
    ),
    "umlaute_und_ss": _topic(
        label="Umlaute, ß und Rechtschreibung",
        level="A1",
        category="Aussprache & Schrift",
        summary="Ä, Ö, Ü und ß tragen im Deutschen Bedeutung, Lautwert und orthografische Information.",
        when_to_study="Ab Tag eins, besonders bei Schreiben am Laptop oder Handy.",
        core_rules=[
            "`ä`, `ö`, `ü` sind eigene Buchstaben.",
            "`ß` steht meist nach langem Vokal oder Diphthong.",
            "Nomen werden großgeschrieben.",
        ],
        deep_dive=[
            "Umlaute verändern oft Wortfamilien und Pluralformen: `Mutter` zu `Mütter`, `fahren` zu `fährt`.",
            "Die Unterscheidung von `Masse` und `Maße` oder `schon` und `schön` ist semantisch relevant.",
            "Technische Umschriften wie `ae`, `oe`, `ue` sind nur Hilfslösungen; aktive Lerntexte sollten korrekt geschrieben werden.",
        ],
        exceptions=[
            "In der Schweiz wird meist `ss` statt `ß` verwendet.",
            "Eigennamen folgen nicht immer der Standardschreibung.",
        ],
        examples=[
            "für, schön, Grüße, Straße, heißen",
            "Ich möchte fünf Brötchen und ein Getränk.",
            "Viele Grüße aus Köln!",
        ],
        common_mistakes=[
            "`für` ohne Umlaut zu schreiben.",
            "`ss` überall zu verwenden.",
            "Substantive kleinzuschreiben.",
        ],
        memory_hook="Umlaut ändert Wörter, ß folgt meist auf langen Laut.",
        related_topics=["aussprache_und_alphabet", "artikel_genus_und_plural"],
    ),
    "artikel_genus_und_plural": _topic(
        label="Artikel, Genus und Plural",
        level="A1",
        category="Nomen & Artikel",
        summary="Ein deutsches Nomen lernst du vollständig: Artikel, Singular und Plural.",
        when_to_study="Bei jedem neuen Wortschatzfeld.",
        core_rules=[
            "Nomen immer mit Artikel speichern.",
            "Pluralformen sind nicht frei vorhersagbar.",
            "Genus beeinflusst später Kasus, Pronomen und Adjektivendungen.",
        ],
        deep_dive=[
            "Ohne Artikel ist ein Nomen grammatisch unvollständig gespeichert.",
            "Pluralbildung folgt verschiedenen Mustern: `-e`, `-er`, `-en`, `-s`, Nullplural und Umlaut.",
            "Genusmuster helfen, ersetzen aber nie das gezielte Lernen häufiger Wörter.",
        ],
        exceptions=[
            "Einige Nomen ändern mit dem Genus ihre Bedeutung.",
            "Einige Nomen kommen fast nur im Singular oder fast nur im Plural vor.",
        ],
        examples=[
            "der Beruf - die Berufe",
            "die Bewerbung - die Bewerbungen",
            "das Gespräch - die Gespräche",
        ],
        common_mistakes=[
            "Nur die Übersetzung ohne Artikel zu lernen.",
            "Alle Plurale auf `-en` zu reduzieren.",
            "Umlaut im Plural zu vergessen.",
        ],
        memory_hook="Nomen komplett lernen: Artikel + Singular + Plural.",
        related_topics=["bestimmter_und_unbestimmter_artikel", "nominativ_und_akkusativ"],
    ),
    "bestimmter_und_unbestimmter_artikel": _topic(
        label="Bestimmter und unbestimmter Artikel",
        level="A1",
        category="Nomen & Artikel",
        summary="Artikel markieren Referenz: etwas Neues, etwas Bekanntes oder einen allgemeinen Begriff.",
        when_to_study="Sobald du einfache Nomengruppen baust.",
        core_rules=[
            "`ein/eine` führt meist neue oder unspezifische Information ein.",
            "`der/die/das` verweist meist auf bekannte oder eindeutige Referenz.",
            "Im Plural gibt es keinen unbestimmten Artikel.",
        ],
        deep_dive=[
            "Artikelwahl ist im Deutschen eng mit Informationsstruktur verbunden.",
            "Nullartikel ist ein eigenes Muster, besonders bei Berufen, Sprachen und allgemeinen Aussagen.",
            "Wer Artikel bewusst wahrnimmt, versteht Texte strukturierter und produziert natürlicher.",
        ],
        exceptions=[
            "Eigennamen stehen meist ohne Artikel.",
            "Einige Ländernamen und Regionen stehen mit Artikel.",
        ],
        examples=[
            "Ich suche eine Wohnung. Die Wohnung soll ruhig sein.",
            "Sie ist Ärztin.",
            "Wir lernen Deutsch.",
        ],
        common_mistakes=[
            "Im Plural einen unbestimmten Artikel zu erzwingen.",
            "Immer den bestimmten Artikel zu wählen.",
            "Nullartikel als Fehler zu behandeln.",
        ],
        memory_hook="`ein` führt ein, `der/die/das` greift wieder auf.",
        related_topics=["artikel_genus_und_plural", "personal_und_possessivpronomen"],
    ),
    "nominativ_und_akkusativ": _topic(
        label="Nominativ und Akkusativ",
        level="A1",
        category="Kasus",
        summary="Der erste Kasuskontrast: Wer handelt, und wen oder was betrifft die Handlung direkt?",
        when_to_study="Sobald du Sätze mit Subjekt und direktem Objekt bildest.",
        core_rules=[
            "Nominativ markiert typischerweise das Subjekt.",
            "Akkusativ markiert typischerweise das direkte Objekt.",
            "Im Maskulinum ist der Unterschied besonders sichtbar: `der` versus `den`.",
        ],
        deep_dive=[
            "Kasus organisiert im Deutschen Rollen im Satz und ist nicht bloß Endungswissen.",
            "Gerade bei flexiblem Satzanfang bleibt über den Kasus klar, wer handelt und wer betroffen ist.",
            "Pronomen sind ein guter Trainingsbereich: `ich/mich`, `er/ihn`.",
        ],
        exceptions=[
            "Nicht jedes Verb verhält sich genauso wie im Spanischen.",
            "Im Femininum und Neutrum ist der sichtbare Unterschied im Singular kleiner.",
        ],
        examples=[
            "Der Student liest den Text.",
            "Ich sehe einen Freund.",
            "Wen suchst du?",
        ],
        common_mistakes=[
            "Im Maskulinum `der` statt `den` zu setzen.",
            "Subjekt und Objekt nur über Wortstellung zu interpretieren.",
            "Pronomen im falschen Fall zu wählen.",
        ],
        memory_hook="Nominativ handelt, Akkusativ wird direkt betroffen.",
        related_topics=["dativ_grundlagen", "satzbau_verbzweitstellung"],
    ),
    "dativ_grundlagen": _topic(
        label="Dativ: Grundfunktionen",
        level="A2",
        category="Kasus",
        summary="Der Dativ zeigt oft Empfänger, Bezugsperson oder vom Verb bzw. von der Präposition geforderte Ergänzungen.",
        when_to_study="Nach Nominativ und Akkusativ sowie mit ersten Dativverben.",
        core_rules=[
            "Viele Verben fordern Dativ: `helfen`, `danken`, `gefallen`.",
            "Mehrere Präpositionen regieren fest den Dativ: `mit`, `bei`, `nach`, `seit`, `von`, `zu`.",
            "Im Dativ Plural erhält das Nomen oft zusätzlich `-n`.",
        ],
        deep_dive=[
            "Dativ ist im Alltag extrem häufig und sollte immer mit dem Verb oder der Präposition zusammen gelernt werden.",
            "Viele Fehler entstehen durch automatischen Rückgriff auf den Akkusativ.",
            "Dativwissen hilft später direkt bei Adjektivdeklination und Präpositionalmustern.",
        ],
        exceptions=[
            "Im gesprochenen Deutsch ersetzt `von + Dativ` oft den Genitiv.",
            "Manche Verben schwanken je nach Bedeutung zwischen Dativ und Akkusativ.",
        ],
        examples=[
            "Ich helfe dem Kollegen.",
            "Der Film gefällt mir.",
            "Wir fahren mit dem Zug.",
        ],
        common_mistakes=[
            "Nach Dativverben Akkusativ zu benutzen.",
            "Das `-n` im Dativ Plural zu vergessen.",
            "Präpositionen ohne Kasus zu lernen.",
        ],
        memory_hook="Dativ immer mit Verb oder Präposition als Einheit speichern.",
        related_topics=["nominativ_und_akkusativ", "praepositionen_grundlagen", "wechselpraepositionen"],
    ),
    "personal_und_possessivpronomen": _topic(
        label="Personal- und Possessivpronomen",
        level="A1",
        category="Pronomen",
        summary="Pronomen machen Texte flüssig und vermeiden Wiederholungen.",
        when_to_study="Ab den ersten Dialogen und Personenbeschreibungen.",
        core_rules=[
            "Personalpronomen ändern sich nach Person, Numerus und Kasus.",
            "Possessivpronomen werden wie Begleiter dekliniert.",
            "Der Bezug muss immer klar bleiben.",
        ],
        deep_dive=[
            "Pronomen sind zentrale Kohäsionsmittel im Deutschen.",
            "Besonders wichtig sind Kontrastreihen wie `ich/mich/mir` und `er/ihn/ihm`.",
            "Die Höflichkeitsform `Sie` verlangt besondere Aufmerksamkeit bei Großschreibung und Verbform.",
        ],
        exceptions=[
            "`ihr` kann mehrere grammatische Funktionen haben.",
            "Nicht jeder Bezug klingt mit Pronomen natürlicher; manchmal ist ein Nomen klarer.",
        ],
        examples=[
            "Das ist meine Kollegin. Ich arbeite mit ihr.",
            "Wo ist dein Ticket? Ich sehe es nicht.",
            "Können Sie mir bitte helfen?",
        ],
        common_mistakes=[
            "Possessivformen nicht zu beugen.",
            "Unklare Referenzen mit zu vielen Pronomen zu bauen.",
            "Die Höflichkeitsform kleinzuschreiben.",
        ],
        memory_hook="Gutes Pronomen = klarer Bezug + richtiger Fall.",
        related_topics=["bestimmter_und_unbestimmter_artikel", "nominativ_und_akkusativ"],
    ),
    "fragewoerter_und_fragesaetze": _topic(
        label="Fragewörter und Fragesätze",
        level="A1",
        category="Satzbau",
        summary="Fragen trainieren Wortstellung, Kasus und echte Interaktion gleichzeitig.",
        when_to_study="Ab den ersten Gesprächssituationen.",
        core_rules=[
            "W-Fragen haben das Verb direkt nach dem Fragewort.",
            "Ja/Nein-Fragen beginnen mit dem finiten Verb.",
            "`wo` und `wohin` unterscheiden Ort und Richtung.",
        ],
        deep_dive=[
            "Fragekompetenz verbessert Gespräche besonders schnell, weil sie Reaktion, Höflichkeit und Satzbau bündelt.",
            "Viele Fehler hängen nicht am Vokabular, sondern an unklarer deutscher Fragearchitektur.",
            "Besonders wichtig ist die Verbindung von Fragewort und Kasus: `wer`, `wen`, `wem`.",
        ],
        exceptions=[
            "Indirekte Fragen folgen später anderen Wortstellungsregeln.",
            "In informeller Sprache gibt es Verkürzungen, die für Prüfungen nicht zentral sind.",
        ],
        examples=[
            "Wie heißt du?",
            "Fährst du morgen nach Berlin?",
            "Wohin gehst du am Wochenende?",
        ],
        common_mistakes=[
            "In W-Fragen das Verb zu spät zu setzen.",
            "`wo` und `wohin` zu verwechseln.",
            "Ja/Nein-Fragen mit dem Subjekt zu beginnen.",
        ],
        memory_hook="W-Frage: Fragewort + Verb. Ja/Nein: Verb zuerst.",
        related_topics=["satzbau_verbzweitstellung", "wechselpraepositionen"],
    ),
    "praesens_und_verbkonjugation": _topic(
        label="Präsens und Verbkonjugation",
        level="A1",
        category="Verben",
        summary="Das Präsens trägt einen großen Teil des Alltagsdeutschen und ist die Basis für fast jede Produktion.",
        when_to_study="Vom ersten Tag an.",
        core_rules=[
            "Das finite Verb muss mit Person und Numerus übereinstimmen.",
            "Einige häufige Verben haben Vokalwechsel im Singular.",
            "Präsens kann mit Zeitangaben auch Zukunft ausdrücken.",
        ],
        deep_dive=[
            "Viele Fehler entstehen nicht bei den Endungen allein, sondern in der Verbindung von Konjugation und Wortstellung.",
            "Hochfrequente Verben wie `sein`, `haben`, `werden`, `kommen`, `gehen` müssen sehr früh automatisiert werden.",
            "Kurze, stabile Präsenssätze sind im Lernprozess wertvoller als riskante komplexe Formen.",
        ],
        exceptions=[
            "Einige Verben auf `-eln` oder `-ern` haben kleinere Besonderheiten.",
            "Nicht jede Zukunftsaussage braucht `werden`.",
        ],
        examples=[
            "Ich arbeite heute von zu Hause.",
            "Er fährt morgen nach Berlin.",
            "Wir nehmen den Bus um acht Uhr.",
        ],
        common_mistakes=[
            "Den Infinitiv statt der finiten Form zu benutzen.",
            "Vokalwechsel zu vergessen.",
            "Nur Tabellen statt ganzer Sätze zu lernen.",
        ],
        memory_hook="Ein deutscher Satz braucht ein klares finites Verb.",
        related_topics=["modalverben", "satzbau_verbzweitstellung", "perfekt_und_prateritum"],
    ),
    "modalverben": _topic(
        label="Modalverben",
        level="A1",
        category="Verben",
        summary="Mit Modalverben drückst du Fähigkeit, Erlaubnis, Pflicht, Wunsch und Plan aus.",
        when_to_study="Nach den ersten Präsenssätzen.",
        core_rules=[
            "Das Modalverb steht finit, der Infinitiv am Satzende.",
            "Viele Modalverben sind im Singular unregelmäßig.",
            "`möchten` ist eine besonders wichtige Höflichkeitsform.",
        ],
        deep_dive=[
            "Modalverben sind kommunikativ hochrelevant: bitten, vorschlagen, planen, begrenzen und höflich reagieren.",
            "Sie trainieren früh die Satzklammer und bereiten spätere Strukturen vor.",
            "Bedeutungsunterschiede wie `müssen`, `sollen`, `dürfen` und `können` sollten funktional gelernt werden.",
        ],
        exceptions=[
            "Im Perfekt zeigen Modalverben besondere Muster.",
            "Nicht jede höfliche Bitte wird mit einem echten Modalverb gebildet.",
        ],
        examples=[
            "Ich kann morgen kommen.",
            "Wir müssen das Formular ausfüllen.",
            "Darf ich hier warten?",
        ],
        common_mistakes=[
            "Infinitiv nicht ans Satzende zu stellen.",
            "Vollverb und Modalverb beide zu konjugieren.",
            "`müssen` und `sollen` gleichzusetzen.",
        ],
        memory_hook="Modal finit vorn, Vollverb im Infinitiv hinten.",
        related_topics=["praesens_und_verbkonjugation", "satzbau_verbzweitstellung", "konjunktiv_ii"],
    ),
    "satzbau_verbzweitstellung": _topic(
        label="Hauptsatz, Verbzweitstellung und Satzklammer",
        level="A1",
        category="Satzbau",
        summary="Die Verbzweitstellung ist die tragende Architektur des deutschen Hauptsatzes.",
        when_to_study="Sobald du ganze Sätze bildest.",
        core_rules=[
            "Im Aussagesatz steht das finite Verb an zweiter Stelle.",
            "Vor dem Verb steht genau ein Satzglied oder eine geschlossene Gruppe.",
            "Mit Modalverben, Perfekt und trennbaren Verben entsteht eine Satzklammer.",
        ],
        deep_dive=[
            "Viele Lernende zählen Wörter statt Satzglieder; das führt schnell zu Verb-Dritt-Stellung.",
            "Die Satzklammer ist keine Randerscheinung, sondern eine Kernidee der deutschen Syntax.",
            "Wer die Verbzweitstellung beherrscht, klingt sofort natürlicher, auch mit einfachem Wortschatz.",
        ],
        exceptions=[
            "Ja/Nein-Fragen und Imperative haben Verb-Erststellung.",
            "Nebensätze folgen später der Verbendstellung.",
        ],
        examples=[
            "Heute lerne ich zu Hause.",
            "Morgen kann ich leider nicht kommen.",
            "Den Termin verschiebe ich auf Freitag.",
        ],
        common_mistakes=[
            "Nach einem Adverbial das Verb an dritter Stelle zu lassen.",
            "Die zweite Hälfte der Satzklammer zu vergessen.",
            "Wörter statt Satzglieder zu zählen.",
        ],
        memory_hook="Egal was vorne steht: das finite Verb will Platz 2.",
        related_topics=["fragewoerter_und_fragesaetze", "nebensaetze_basis", "trennbare_und_untrennbare_verben"],
    ),
    "negation_nicht_und_kein": _topic(
        label="Negation mit nicht und kein",
        level="A1",
        category="Satzbau",
        summary="Die deutsche Negation hängt stark davon ab, was genau verneint werden soll.",
        when_to_study="Sobald du sichere Aussagesätze baust.",
        core_rules=[
            "`kein` negiert unbestimmte Nomen oder Nomen ohne Artikel.",
            "`nicht` negiert Verben, Adjektive, Adverbien oder ganze Satzteile.",
            "Die Stellung von `nicht` steuert den Fokus der Verneinung.",
        ],
        deep_dive=[
            "Negation ist im Deutschen nicht einfach `no` plus Satz, sondern ein System aus Fokus und Satzbau.",
            "`kein` ist ein negativer Artikel und wird deshalb dekliniert.",
            "Minimalpaare helfen besonders: `Ich habe kein Auto` versus `Ich fahre heute nicht mit dem Auto`.",
        ],
        exceptions=[
            "Bei Eigennamen verwendet man normalerweise `nicht`.",
            "Einige feste Wendungen müssen als Ganzes gelernt werden.",
        ],
        examples=[
            "Ich habe keine Zeit.",
            "Der Zug kommt heute nicht pünktlich.",
            "Das ist kein Problem.",
        ],
        common_mistakes=[
            "`nicht` statt `kein` bei Nomen zu verwenden.",
            "`nicht` zu früh zu platzieren.",
            "`kein` nicht zu deklinieren.",
        ],
        memory_hook="`kein` negiert Nomen, `nicht` den Rest.",
        related_topics=["bestimmter_und_unbestimmter_artikel", "satzbau_verbzweitstellung"],
    ),
    "perfekt_und_prateritum": _topic(
        label="Perfekt und Präteritum",
        level="A2",
        category="Verben",
        summary="Vergangenheit im Deutschen: Perfekt dominiert im Gespräch, Präteritum bleibt für wichtige Verben und Texte zentral.",
        when_to_study="Wenn du über Erfahrungen, Biografie und vergangene Ereignisse sprichst.",
        core_rules=[
            "Perfekt = `haben/sein` + Partizip II.",
            "Präteritum ist besonders häufig bei `sein`, `haben`, Modalverben und in Erzähltexten.",
            "Das Partizip II steht im Hauptsatz am Ende.",
        ],
        deep_dive=[
            "Produktiv ist Perfekt zuerst wichtiger, rezeptiv muss Präteritum trotzdem früh sicher werden.",
            "Die größte Hürde liegt oft in Satzarchitektur und Hilfsverbwahl, nicht nur in der Partizipbildung.",
            "Starke Verben sollten immer mit drei Formen gespeichert werden.",
        ],
        exceptions=[
            "Einige Bewegungsverben bilden je nach Bedeutung auch mit `haben`.",
            "Regionale Unterschiede beeinflussen die mündliche Verteilung von Perfekt und Präteritum.",
        ],
        examples=[
            "Ich habe gestern lange gelernt.",
            "Wir sind spät angekommen.",
            "Früher war ich oft in Berlin.",
        ],
        common_mistakes=[
            "Falsches Hilfsverb zu wählen.",
            "Partizip II nicht ans Satzende zu setzen.",
            "Unregelmäßige Partizipien zu erfinden.",
        ],
        memory_hook="Gesprochen: oft Perfekt. Gelesen: oft auch Präteritum.",
        related_topics=["starke_und_unregelmaessige_verben", "satzbau_verbzweitstellung"],
    ),
    "wechselpraepositionen": _topic(
        label="Wechselpräpositionen",
        level="A2",
        category="Kasus",
        summary="Dieselben Präpositionen wechseln zwischen Dativ und Akkusativ je nach Ort oder Richtung.",
        when_to_study="Bei Ortsangaben, Bewegung und Bildbeschreibung.",
        core_rules=[
            "`wo?` führt typischerweise zum Dativ.",
            "`wohin?` führt typischerweise zum Akkusativ.",
            "Entscheidend sind Bedeutung und Verb, nicht nur die Präposition.",
        ],
        deep_dive=[
            "Das deutsche System bildet räumliche Perspektive grammatisch ab und ist deshalb viel mehr als ein reines Kasusthema.",
            "Besonders hilfreich sind Verbpaare wie `legen/liegen`, `stellen/stehen`, `setzen/sitzen`.",
            "Wechselpräpositionen sind in Alltagssprache und Prüfungen ständig präsent.",
        ],
        exceptions=[
            "Metaphorische Verwendungen müssen oft als Wortschatz gelernt werden.",
            "Einige feste Verbindungen sind nur teilweise aus der Raumlogik ableitbar.",
        ],
        examples=[
            "Ich hänge das Bild an die Wand.",
            "Das Bild hängt an der Wand.",
            "Wir setzen uns in den Zug.",
        ],
        common_mistakes=[
            "Dativ immer automatisch zu wählen.",
            "`wo` und `wohin` nicht als Kontrollfrage zu nutzen.",
            "Verbpaare wie `legen/liegen` nicht zu unterscheiden.",
        ],
        memory_hook="Richtung öffnet Akkusativ, Ort stabilisiert Dativ.",
        related_topics=["dativ_grundlagen", "fragewoerter_und_fragesaetze", "praepositionen_grundlagen"],
    ),
    "nebensaetze_basis": _topic(
        label="Nebensätze mit weil, dass, wenn, obwohl",
        level="A2",
        category="Satzbau",
        summary="Nebensätze machen deutsches Schreiben und Sprechen begründeter, präziser und flexibler.",
        when_to_study="Wenn die Verbzweitstellung im Hauptsatz einigermaßen stabil ist.",
        core_rules=[
            "Im eingeleiteten Nebensatz steht das finite Verb am Ende.",
            "Nebensätze werden normalerweise durch Komma abgetrennt.",
            "`weil`, `dass`, `wenn`, `obwohl` haben unterschiedliche logische Funktionen.",
        ],
        deep_dive=[
            "Mit Nebensätzen beginnt echte Argumentation und Textentwicklung.",
            "Die Hauptschwierigkeit ist, das Verb bis zum Ende zurückzuhalten und trotzdem klar zu planen.",
            "Sehr wirksam ist das Training im Wechsel: Hauptsatz zuerst und Nebensatz zuerst.",
        ],
        exceptions=[
            "`denn` ist keine unterordnende Konjunktion.",
            "Umgangssprachliche Abweichungen sind nicht das Ziel für Prüfungen.",
        ],
        examples=[
            "Ich bleibe zu Hause, weil ich krank bin.",
            "Ich glaube, dass er morgen kommt.",
            "Wenn ich Zeit habe, melde ich mich.",
        ],
        common_mistakes=[
            "Das finite Verb im Nebensatz an zweiter Stelle zu lassen.",
            "Das Komma zu vergessen.",
            "`weil` und `denn` syntaktisch gleich zu behandeln.",
        ],
        memory_hook="Konjunktion vorn, finites Verb nach hinten.",
        related_topics=["satzbau_verbzweitstellung", "indirekte_fragen", "relativsaetze"],
    ),
}
