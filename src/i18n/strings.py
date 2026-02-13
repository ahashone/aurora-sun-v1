"""
Translation Strings for Aurora Sun V1.

This module contains all user-facing strings for:
- Onboarding (language selection, name, working style, consent)
- Segment display names (translated)
- Common responses
- Error messages
- Module-specific strings

Structure: {language: {module: {key: value}}}

Reference: CLAUDE.md - International Audience
"""

from __future__ import annotations

from typing import Any

from src.i18n import DEFAULT_LANGUAGE, LanguageCode


# Translation strings organized by language -> module -> key
TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        # Segment display names (user-facing)
        "segments": {
            "AD": "ADHD",
            "AU": "Autism",
            "AH": "AuDHD",
            "NT": "Neurotypical",
            "CU": "Custom",
        },
        # Onboarding module
        "onboarding": {
            # Welcome
            "welcome_title": "Welcome to Aurora Sun",
            "welcome_subtitle": "Your AI coaching companion for neurodivergent people",
            "welcome_intro": "I'm Aurora, your personal coach. I'll help you stay organized, manage your energy, and achieve your goals - in a way that works for your brain.",

            # Language selection
            "language_title": "First, let's choose your language",
            "language_button": "Select Language",

            # Name
            "name_title": "What should I call you?",
            "name_placeholder": "Your name",
            "name_button": "Continue",

            # Working style (segment)
            "working_style_title": "How does your brain work best?",
            "working_style_subtitle": "This helps me adapt to your needs",
            "working_style_AD": "I work in bursts of energy and need novelty",
            "working_style_AU": "I need structure, routine, and predictability",
            "working_style_AH": "I need flexibility but also some structure",
            "working_style_NT": "I work in a fairly standard way",
            "working_style_CU": "I have my own custom setup",
            "working_style_button": "Continue",
            "working_style_skip": "Not sure? Skip for now",

            # Energy check
            "energy_title": "How are you feeling right now?",
            "energy_low": "Low energy / burnt out",
            "energy_medium": "Medium energy",
            "energy_high": "High energy / motivated",
            "energy_button": "Continue",

            # Consent
            "consent_title": "Privacy & Consent",
            "consent_intro": "Before we continue, I need to explain how I handle your data:",
            "consent_point_1": "Your conversations are encrypted and stored securely",
            "consent_point_2": "You can delete your data at any time",
            "consent_point_3": "I never share your personal data with third parties",
            "consent_agree": "I agree to the privacy policy",
            "consent_button": "Get Started",

            # Completion
            "onboarding_complete": "You're all set, {name}!",
            "onboarding_complete_subtitle": "Let's start with your first task.",
        },
        # Common responses
        "common": {
            "loading": "Let me think...",
            "error": "Something went wrong. Let me try again.",
            "retry": "Would you like to try again?",
            "yes": "Yes",
            "no": "No",
            "ok": "OK",
            "cancel": "Cancel",
            "continue_btn": "Continue",
            "back": "Go back",
            "done": "Done",
            "help": "How can I help?",
            "goodbye": "Take care!",
        },
        # Planning module
        "planning": {
            "no_tasks": "You don't have any tasks yet.",
            "add_task": "Add a task",
            "task_added": "Task added: {task}",
            "task_completed": "Great job! Task completed.",
            "priorities_title": "Your priorities for today",
            "priorities_empty": "No priorities set. What would you like to focus on?",
        },
        # Money module
        "money": {
            "title": "Money Tracking",
            "income_prompt": "How much did you receive?",
            "expense_prompt": "How much did you spend?",
            "category_prompt": "What category?",
            "balance": "Current balance: {amount}",
        },
        # Review module
        "review": {
            "title": "Daily Review",
            "completed": "What did you complete today?",
            "learned": "What did you learn?",
            "challenges": "What was challenging?",
            "tomorrow": "What do you want to focus on tomorrow?",
            # Additional review module strings
            "welcome_with_tasks": "You completed {count} tasks today:",
            "welcome_no_tasks": "Today you didn't mark any tasks as complete. That's okay - let's reflect on your day.",
            "accomplishments_prompt": "What did you accomplish today? What are you proud of?",
            "challenges_intro": "Thanks for sharing! Now let's think about what was hard.",
            "challenges_prompt": "What was difficult today? What could have gone better?",
            "energy_intro": "I appreciate you sharing that.",
            "energy_prompt": "On a scale of 1-5, how's your energy right now?",
            "energy_quick_response": "Got it. Let's wrap up.",
            "reflection_intro": "Thank you for being so open.",
            "reflection_prompt": "Any other thoughts about today? What's one thing you learned?",
            "forward_intro": "Almost done!",
            "forward_prompt": "What's one thing you want to focus on or do tomorrow?",
            "complete": "Your review is complete. Tomorrow's focus: {intention}. Great work today!",
            "evening_trigger": "It's evening. How was your day? Ready for a quick review?",
        },
    },
    "de": {
        "segments": {
            "AD": "ADHS",
            "AU": "Autismus",
            "AH": "AuDHD",
            "NT": "Neurotypisch",
            "CU": "Benutzerdefiniert",
        },
        "onboarding": {
            "welcome_title": "Willkommen bei Aurora Sun",
            "welcome_subtitle": "Dein KI-Coach fuer neurodivergente Menschen",
            "welcome_intro": "Ich bin Aurora, dein persoenlicher Coach. Ich helfe dir, organisiert zu bleiben, deine Energie zu managen und deine Ziele zu erreichen - auf eine Weise, die zu deinem Gehirn passt.",

            "language_title": "Waehlen wir zuerst deine Sprache",
            "language_button": "Sprache auswaehlen",

            "name_title": "Wie soll ich dich nennen?",
            "name_placeholder": "Dein Name",
            "name_button": "Weiter",

            "working_style_title": "Wie funktioniert dein Gehirn am besten?",
            "working_style_subtitle": "Damit kann ich mich an deine Beduerfnisse anpassen",
            "working_style_AD": "Ich arbeite in Energie-Boosts und brauche Abwechslung",
            "working_style_AU": "Ich brauche Struktur, Routine und Vorhersagbarkeit",
            "working_style_AH": "Ich brauche Flexibilheit, aber auch etwas Struktur",
            "working_style_NT": "Ich arbeite auf eine recht normale Weise",
            "working_style_CU": "Ich habe meine eigene benutzerdefinierte Einstellung",
            "working_style_button": "Weiter",
            "working_style_skip": "Nicht sicher? Erstmal ueberspringen",

            "energy_title": "Wie fuehlst du dich gerade?",
            "energy_low": "Wenig Energie / ausgebrannt",
            "energy_medium": "Mittlere Energie",
            "energy_high": "Viel Energie / motiviert",
            "energy_button": "Weiter",

            "consent_title": "Datenschutz & Einwilligung",
            "consent_intro": "Bevor wir fortfahren, muss ich erklaeren, wie ich mit deinen Daten umgehe:",
            "consent_point_1": "Deine Gespraeche werden verschluesselt und sicher gespeichert",
            "consent_point_2": "Du kannst deine Daten jederzeit loeschen",
            "consent_point_3": "Ich teile deine persoenlichen Daten nie mit Dritten",
            "consent_agree": "Ich stimme der Datenschutzrichtlinie zu",
            "consent_button": "Los geht's",

            "onboarding_complete": "Du bist bereit, {name}!",
            "onboarding_complete_subtitle": "Lass uns mit deiner ersten Aufgabe beginnen.",
        },
        "common": {
            "loading": "Lass mich nachdenken...",
            "error": "Etwas ist schief gelaufen. Lass mich es nochmal versuchen.",
            "retry": "Moechtest du es nochmal versuchen?",
            "yes": "Ja",
            "no": "Nein",
            "ok": "OK",
            "cancel": "Abbrechen",
            "continue_btn": "Weiter",
            "back": "Zurueck",
            "done": "Fertig",
            "help": "Wie kann ich helfen?",
            "goodbye": "Pass auf dich auf!",
        },
        "planning": {
            "no_tasks": "Du hast noch keine Aufgaben.",
            "add_task": "Aufgabe hinzufuegen",
            "task_added": "Aufgabe hinzugefuegt: {task}",
            "task_completed": "Super! Aufgabe erledigt.",
            "priorities_title": "Deine Prioritaeten heute",
            "priorities_empty": "Keine Prioritaeten gesetzt. Woran moechtest du arbeiten?",
        },
        "money": {
            "title": "Geldverfolgung",
            "income_prompt": "Wie viel hast du erhalten?",
            "expense_prompt": "Wie viel hast du ausgegeben?",
            "category_prompt": "Welche Kategorie?",
            "balance": "Aktueller Kontostand: {amount}",
        },
        "review": {
            "title": "Taegliche Reflexion",
            "completed": "Was hast du heute erledigt?",
            "learned": "Was hast du gelernt?",
            "challenges": "Was war schwierig?",
            "tomorrow": "Woran moechtest du morgen arbeiten?",
            # Additional review module strings
            "welcome_with_tasks": "Du hast heute {count} Aufgaben erledigt:",
            "welcome_no_tasks": "Heute hast du keine Aufgaben als erledigt markiert. Das ist okay - lass uns ueber deinen Tag nachdenken.",
            "accomplishments_prompt": "Was hast du heute erreicht? Woran bist du stolz?",
            "challenges_intro": "Danke fuer das Teilen! Jetzt lass uns darueber nachdenken, was schwer war.",
            "challenges_prompt": "Was war heute schwierig? Was haette besser laufen koennen?",
            "energy_intro": "Ich schaetze das.",
            "energy_prompt": "Auf einer Skala von 1-5, wie ist deine Energie gerade?",
            "energy_quick_response": "Verstanden. Lass uns abschliessen.",
            "reflection_intro": "Danke, dass du so offen warst.",
            "reflection_prompt": "Noch andere Gedanken ueber heute? Was hast du gelernt?",
            "forward_intro": "Fast fertig!",
            "forward_prompt": "Woran moechtest du morgen arbeiten oder was moechtest du morgen tun?",
            "complete": "Deine Reflexion ist abgeschlossen. Fokus fuer morgen: {intention}. Gute Arbeit heute!",
            "evening_trigger": "Es ist Abend. Wie war dein Tag? Bereit fuer eine kurze Reflexion?",
        },
    },
    "sr": {
        "segments": {
            "AD": "ADHD",
            "AU": "Autizam",
            "AH": "AuDHD",
            "NT": "Neurotipican",
            "CU": "Prilagodljivo",
        },
        "onboarding": {
            "welcome_title": "Dobrodosli u Aurora Sun",
            "welcome_subtitle": "Vas AI trener za neurodivergentne osobe",
            "welcome_intro": "Ja sam Aurora, vas licni trener. Pomoci cu vam da ostanete organizovani, upravljate energijom i postignete svoje ciljeve - na nacin koji odgovara vasem mozgu.",

            "language_title": "Prvo, hajde da izaberemo vas jezik",
            "language_button": "Izaberi jezik",

            "name_title": "Kako da vas zovem?",
            "name_placeholder": "Vase ime",
            "name_button": "Nastavi",

            "working_style_title": "Kako vas mozak najbolje radi?",
            "working_style_subtitle": "Ovo mi pomaze da se prilagodim vasim potrebama",
            "working_style_AD": "Radim u bljeskovima energije i treba mi nesto novo",
            "working_style_AU": "Treba mi struktura, rutina i predvidljivost",
            "working_style_AH": "Treba mi fleksibilnost, ali i nesto strukture",
            "working_style_NT": "Radim na prilicno standardan nacin",
            "working_style_CU": "Imam svoju prilagodjenu podesavanja",
            "working_style_button": "Nastavi",
            "working_style_skip": "Niste sigurni? Preskocite za sada",

            "energy_title": "Kako se sada osecate?",
            "energy_low": "Niska energija / iscrpljenost",
            "energy_medium": "Srednja energija",
            "energy_high": "Visoka energija / motivacija",
            "energy_button": "Nastavi",

            "consent_title": "Privatnost i saglasnost",
            "consent_intro": "Pre nego sto nastavimo, moram da objasnim kako radim sa vasim podacima:",
            "consent_point_1": "Vasi razgovori su sifrovani i bezbedno cuvani",
            "consent_point_2": "Mozete obrisati svoje podatke u bilo kom trenutku",
            "consent_point_3": "Nikada ne delim vase licne podatke sa trecim stranama",
            "consent_agree": "Saglasan sam sa politikom privatnosti",
            "consent_button": "Kreni",

            "onboarding_complete": "Sve je spremno, {name}!",
            "onboarding_complete_subtitle": "Hajde da pocnemo sa vasim prvim zadatkom.",
        },
        "common": {
            "loading": "Razmislicu...",
            "error": "Nesto je poslo naopako. Pokusacu ponovo.",
            "retry": "Zelite li da probate ponovo?",
            "yes": "Da",
            "no": "Ne",
            "ok": "U redu",
            "cancel": "Otkazi",
            "continue_btn": "Nastavi",
            "back": "Nazad",
            "done": "Zavrseno",
            "help": "Kako mogu pomoci?",
            "goodbye": "Pazite se!",
        },
        "planning": {
            "no_tasks": "Nemate zadatke za sada.",
            "add_task": "Dodaj zadatak",
            "task_added": "Zadatak dodat: {task}",
            "task_completed": "Odlicno! Zadatak zavrsen.",
            "priorities_title": "Vasi prioriteti za danas",
            "priorities_empty": "Nema postavljenih prioriteta. Na cemu zelite da radite?",
        },
        "money": {
            "title": " pracenje novca",
            "income_prompt": "Koliko ste primili?",
            "expense_prompt": "Koliko ste potrosili?",
            "category_prompt": "Koja kategorija?",
            "balance": "Trenutno stanje: {amount}",
        },
        "review": {
            "title": "Dnevna revizija",
            "completed": "Sta ste danas zavrsili?",
            "learned": "Sta ste naucili?",
            "challenges": "Sta je bilo tesko?",
            "tomorrow": "Na cemu zelite da se fokusirate sutra?",
            # Additional review module strings
            "welcome_with_tasks": "Zavrsili ste {count} zadataka danas:",
            "welcome_no_tasks": "Danas niste oznacili nijedan zadatak kao zavrsen. Nije problem - hajde da razmislimo o vasem danu.",
            "accomplishments_prompt": "Sta ste danas postigli? Cime ste ponosni?",
            "challenges_intro": "Hvala sto ste podelili! Sada hajde da razmislimo sta je bilo tesko.",
            "challenges_prompt": "Sta je bilo tesko danas? Sta je moglo ici bolje?",
            "energy_intro": "Cenim to.",
            "energy_prompt": "Na skali od 1-5, kolika je vasa energija sada?",
            "energy_quick_response": "Razumem. Hajde da završimo.",
            "reflection_intro": "Hvala vam sto ste bili toliko otvoreni.",
            "reflection_prompt": "Jos neke misli o danasnjem danu? Sta ste naucili?",
            "forward_intro": "Skoro gotovo!",
            "forward_prompt": "Na cemu zelite da se fokusirate ili sta zelite da uradite sutra?",
            "complete": "Vasa revizija je zavrsena. Fokus za sutra: {intention}. Odlican posao danas!",
            "evening_trigger": "Vece je. Kako je prosao dan? Spremni za kratku reviziju?",
        },
    },
    "el": {
        "segments": {
            "AD": "ADHD",
            "AU": "Αυτισμός",
            "AH": "AuDHD",
            "NT": "Νευροτυπικό",
            "CU": "Προσαρμοσμένο",
        },
        "onboarding": {
            "welcome_title": "Καλώς ήρθες στο Aurora Sun",
            "welcome_subtitle": "Ο AI προπονητής σου για νευροδιαφορετικά άτομα",
            "welcome_intro": "Είμαι η Aurora, ο προσωπικός σου προπονητής. Θα σε βοηθήσω να παραμείνεις οργανωμένος/η, να διαχειρίζεσαι την ενέργειά σου και να επιτυγχάνεις τους στόχους σου - με τρόπο που ταιριάζει στον εγκέφαλό σου.",

            "language_title": "Πρώτα, ας επιλέξουμε τη γλώσσα σου",
            "language_button": "Επιλογή Γλώσσας",

            "name_title": "Πώς να σε αποκαλώ;",
            "name_placeholder": "Το όνομά σου",
            "name_button": "Συνέχεια",

            "working_style_title": "Πώς λειτουργεί καλύτερα ο εγκέφαλός σου;",
            "working_style_subtitle": "Αυτό με βοηθά να προσαρμοστώ στις ανάγκες σου",
            "working_style_AD": "Δουλεύω σε εξάρσεις ενέργειας και χρειάζομαι νεοτερισμούς",
            "working_style_AU": "Χρειάζομαι δομή, ρουτίνα και προβλεψιμότητα",
            "working_style_AH": "Χρειάζομαι ευελιξία αλλά και κάποια δομή",
            "working_style_NT": "Δουλεύω με αρκετά τυπικό τρόπο",
            "working_style_CU": "Έχω τη δική μου προσαρμοσμένη ρύθμιση",
            "working_style_button": "Συνέχεια",
            "working_style_skip": "Δεν είσαι σίγουρος/η; Παράλειψε για τώρα",

            "energy_title": "Πώς αισθάνεσαι τώρα;",
            "energy_low": "Χαμηλή ενέργεια / εξουθενωμένος/η",
            "energy_medium": "Μέτρια ενέργεια",
            "energy_high": "Υψηλή ενέργεια / κινητοποιημένος/η",
            "energy_button": "Συνέχεια",

            "consent_title": "Απόρρητο & Συναίνεση",
            "consent_intro": "Πριν συνεχίσουμε, πρέπει να εξηγήσω πώς χειρίζομαι τα δεδομένα σου:",
            "consent_point_1": "Οι συνομιλίες σου είναι κρυπτογραφημένες και αποθηκεύονται με ασφάλεια",
            "consent_point_2": "Μπορείς να διαγράψεις τα δεδομένα σου ανά πάσα στιγμή",
            "consent_point_3": "Ποτέ δεν μοιράζω τα προσωπικά σου δεδομένα με τρίτους",
            "consent_agree": "Συμφωνώ με την πολιτική απορρήτου",
            "consent_button": "Ξεκίνα",

            "onboarding_complete": "Είσαι έτοιμος/η, {name}!",
            "onboarding_complete_subtitle": "Ας ξεκινήσουμε με την πρώτη σου εργασία.",
        },
        "common": {
            "loading": "Άσε με να σκεφτώ...",
            "error": "Κάτι πήγε στραβά. Άσε με να δοκιμάσω ξανά.",
            "retry": "Θέλεις να δοκιμάσεις ξανά;",
            "yes": "Ναι",
            "no": "Όχι",
            "ok": "Εντάξει",
            "cancel": "Ακύρωση",
            "continue_btn": "Συνέχεια",
            "back": "Πίσω",
            "done": "Έτοιμο",
            "help": "Πώς μπορώ να βοηθήσω;",
            "goodbye": "Πρόσεχε!",
        },
        "planning": {
            "no_tasks": "Δεν έχεις εργασίες ακόμα.",
            "add_task": "Προσθήκη εργασίας",
            "task_added": "Εργασία προστέθηκε: {task}",
            "task_completed": "Μπράβο! Εργασία ολοκληρώθηκε.",
            "priorities_title": "Οι προτεραιότητές σου για σήμερα",
            "priorities_empty": "Δεν υπάρχουν προτεραιότητες. Σε τι θέλεις να εστιάσεις;",
        },
        "money": {
            "title": "Παρακολούθηση Χρημάτων",
            "income_prompt": "Πόσο έλαβες;",
            "expense_prompt": "Πόσο ξόδεψες;",
            "category_prompt": "Τι κατηγορία;",
            "balance": "Τρέχον υπόλοιπο: {amount}",
        },
        "review": {
            "title": "Ημερήσια Ανασκόπηση",
            "completed": "Τι ολοκλήρωσες σήμερα;",
            "learned": "Τι έμαθες;",
            "challenges": "Τι ήταν δύσκολο;",
            "tomorrow": "Σε τι θέλεις να εστιάσεις αύριο;",
            # Additional review module strings
            "welcome_with_tasks": "Ολοκλήρωσες {count} εργασίες σήμερα:",
            "welcome_no_tasks": "Σήμερα δεν σημείωσες καμία εργασία ως ολοκληρωμένη. Εντάξει - ας σκεφτούμε τη μέρα σου.",
            "accomplishments_prompt": "Τι πέτυχες σήμερα; Για τι είσαι περήφανος/η;",
            "challenges_intro": "Ευχαριστώ που μοιράστηκες! Τώρα ας σκεφτούμε τι ήταν δύσκολο.",
            "challenges_prompt": "Τι ήταν δύσκολο σήμερα; Τι θα μπορούσε να πάει καλύτερα;",
            "energy_intro": "Το εκτιμώ.",
            "energy_prompt": "Σε κλίμακα 1-5, πώς είναι η ενέργειά σου τώρα;",
            "energy_quick_response": "Κατάλαβα. Ας τελειώσουμε.",
            "reflection_intro": "Ευχαριστώ που ήσουν τόσο ανοιχτός/ή.",
            "reflection_prompt": "Άλλες σκέψεις για σήμερα; Τι έμαθες;",
            "forward_intro": "Σχεδόν τελειώσαμε!",
            "forward_prompt": "Σε τι θέλεις να εστιάσεις ή τι θέλεις να κάνεις αύριο;",
            "complete": "Η ανασκόπησή σου είναι ολοκληρωμένη. Εστίαση για αύριο: {intention}. Καλή δουλειά σήμερα!",
            "evening_trigger": "Είναι βράδυ. Πώς πήγε η μέρα σου; Έτοιμος/η για μια γρήγορη ανασκόπηση;",
        },
    },
}


def t(lang: LanguageCode, module: str, key: str, **kwargs: Any) -> str:
    """
    Get a translation string.

    This is the main function for accessing translations.
    Falls back to English if the translation is not found.

    Args:
        lang: Language code (en, de, sr, el)
        module: Module name (e.g., "onboarding", "common", "planning")
        key: Translation key (e.g., "welcome_title", "yes", "task_added")
        **kwargs: Optional format variables (e.g., name="{name}")

    Returns:
        Translated string, or English fallback if not found

    Example:
        >>> t("en", "onboarding", "welcome_title")
        "Welcome to Aurora Sun"

        >>> t("de", "planning", "task_added", task="Buy milk")
        "Aufgabe hinzugefuegt: Buy milk"
    """
    # Try the requested language
    if lang in TRANSLATIONS:
        lang_dict = TRANSLATIONS[lang]
        if module in lang_dict:
            module_dict = lang_dict[module]
            if key in module_dict:
                # Found the translation, apply format variables
                template = module_dict[key]
                if kwargs:
                    try:
                        return template.format(**kwargs)
                    except KeyError:
                        # If format fails, return template as-is
                        return template
                return template

    # Fallback to English
    if lang != "en":
        return t("en", module, key, **kwargs)

    # No translation found at all
    return f"[{module}.{key}]"


def t_segment(lang: LanguageCode, segment_code: str) -> str:
    """
    Get the translated segment display name.

    Args:
        lang: Language code
        segment_code: Internal segment code (AD, AU, AH, NT, CU)

    Returns:
        Translated segment display name

    Example:
        >>> t_segment("de", "AD")
        "ADHS"
        >>> t_segment("en", "AU")
        "Autism"
    """
    return t(lang, "segments", segment_code)


def get_supported_languages() -> list[str]:
    """
    Get list of all supported language codes.

    Returns:
        List of supported language codes
    """
    return list(TRANSLATIONS.keys())


def get_translation_keys(lang: str, module: str) -> list[str]:
    """
    Get all translation keys for a specific language and module.

    Args:
        lang: Language code
        module: Module name

    Returns:
        List of translation keys
    """
    if lang in TRANSLATIONS:
        if module in TRANSLATIONS[lang]:
            return list(TRANSLATIONS[lang][module].keys())
    return []
